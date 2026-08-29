"""Real-browser E2E harness: real LLM + real Chrome over CDP + real actions.

Runs the untouched backend (bridge_server -> BrowserUseRunController -> browser_use.Agent)
in-process so provider/browser env can be set without editing any project config, then
verifies the end state out-of-band: the cart is read straight from the page's
localStorage over CDP, independently of anything the agent claims or reports.

Usage:
    python agent-backend/scripts/e2e_real_browser.py "<task>" [start_url]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "agent-backend"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND))

CDP_HOST = "127.0.0.1"
CDP_PORT = 9222
BACKEND_PORT = 8765
STORE_MARKER = "localhost:3001"

# config.py loads .env/.env.test at import; these override for this harness only.
os.environ["BROWSER_USE_CDP_URL"] = f"http://{CDP_HOST}:{CDP_PORT}"

import urllib.request  # noqa: E402

import websockets  # noqa: E402

_LOG_PATTERN = re.compile(r"LLM_CALL|LLM failover|backing off|retry budget|LLM recovered|Browser Use LLM chain")


class ProviderLogCapture(logging.Handler):
    """Collects the resilience layer's own lines so the report is evidence, not guesswork."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            return
        if _LOG_PATTERN.search(message):
            self.lines.append(message)


def _attach_capture() -> ProviderLogCapture:
    capture = ProviderLogCapture()
    for name in ("utils.llm_resilience", "core.llm_failover", "core.llm_factory", "core.planner_llm"):
        logging.getLogger(name).addHandler(capture)
        logging.getLogger(name).setLevel(logging.DEBUG)
    return capture


def _llm_call_rows(lines: list[str]) -> list[dict[str, str]]:
    rows = []
    for line in lines:
        if "LLM_CALL" not in line:
            continue
        body = line[line.index("LLM_CALL"):]
        rows.append(dict(re.findall(r"(\w+)=(\S+)", body)))
    return rows


async def _http_json(path: str) -> Any:
    def fetch() -> Any:
        with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}{path}", timeout=10) as response:
            return json.loads(response.read())

    return await asyncio.to_thread(fetch)


async def cdp_evaluate(expression: str) -> Any:
    """Evaluate JS in the store tab through a second, independent CDP session."""
    targets = await _http_json("/json")
    pages = [t for t in targets if t.get("type") == "page" and STORE_MARKER in t.get("url", "")]
    if not pages:
        return {"__error__": "no localhost:3001 tab found", "tabs": [t.get("url") for t in targets]}
    page = pages[0]
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
        await ws.recv()
        await ws.send(
            json.dumps(
                {
                    "id": 2,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expression, "returnByValue": True, "awaitPromise": True},
                }
            )
        )
        while True:
            reply = json.loads(await ws.recv())
            if reply.get("id") == 2:
                if "error" in reply:
                    return {"__error__": reply["error"].get("message")}
                value = reply.get("result", {}).get("result", {}).get("value")
                return value if value is not None else {"__error__": "empty evaluate result"}


CART_SNAPSHOT_JS = """
(() => {
  const raw = window.localStorage.getItem('rf-market-cart');
  let lines = [];
  try { lines = raw ? JSON.parse(raw) : []; } catch (e) { lines = []; }
  return {
    url: location.href,
    origin: location.origin,
    raw: raw,
    lines: (Array.isArray(lines) ? lines : []).map((l) => ({
      id: l?.id ?? l?.productId ?? null,
      title: l?.title ?? l?.name ?? null,
      price: l?.price ?? null,
      quantity: l?.quantity ?? 1,
    })),
  };
})()
"""


async def read_cart() -> Any:
    return await cdp_evaluate(CART_SNAPSHOT_JS)


async def reset_cart() -> Any:
    return await cdp_evaluate(
        "(() => { window.localStorage.removeItem('rf-market-cart');"
        " window.localStorage.removeItem('razorflow-cart');"
        " return { cleared: true, now: window.localStorage.getItem('rf-market-cart') }; })()"
    )


async def serve_backend() -> Any:
    import uvicorn

    from core.bridge_server import app

    config = uvicorn.Config(app, host="127.0.0.1", port=BACKEND_PORT, log_level="warning", ws="websockets")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    deadline = time.monotonic() + 60
    while not server.started:
        if task.done():
            raise RuntimeError(f"backend failed to start: {task.exception()}")
        if time.monotonic() > deadline:
            raise RuntimeError("backend did not start within 60s")
        await asyncio.sleep(0.2)
    return server, task


async def drive_run(task_text: str, url: str, *, timeout_sec: int) -> dict[str, Any]:
    uri = f"ws://127.0.0.1:{BACKEND_PORT}/ws"
    run_id = f"e2e-{int(time.time())}"
    events: list[dict[str, Any]] = []
    actions: list[str] = []
    started = time.perf_counter()
    outcome = "TIMEOUT"
    detail = ""

    async with websockets.connect(uri, ping_interval=20, ping_timeout=60, max_size=30_000_000) as ws:
        await ws.send(
            json.dumps({"type": "START_RUN", "runId": run_id, "task": task_text, "url": url})
        )
        while time.perf_counter() - started < timeout_sec:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=20)
            except asyncio.TimeoutError:
                events.append({"t": round(time.perf_counter() - started, 1), "type": "_idle"})
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            elapsed = round(time.perf_counter() - started, 1)
            kind = message.get("type")
            summary = message.get("actionSummary")
            if kind == "AGENT_SYNC":
                if summary and (not actions or actions[-1] != summary):
                    actions.append(f"{summary} @ {message.get('url', '')[:60]}")
                events.append({"t": elapsed, "type": kind, "step": message.get("step"), "action": summary, "url": message.get("url")})
                continue
            events.append({"t": elapsed, "type": kind, "message": message})
            if kind == "RUN_COMPLETE":
                outcome = "RUN_COMPLETE"
                detail = str(message.get("message", ""))[:400]
                break
            if kind == "RUN_ERROR":
                outcome = "RUN_ERROR"
                detail = str(message.get("message") or message.get("error") or "")[:600]
                break
            if kind in {"RUN_WAITING_FOR_USER", "RUN_NEEDS_CLARIFICATION"}:
                outcome = kind
                detail = str(message.get("message", ""))[:600]
                break
        else:
            detail = f"no terminal message within {timeout_sec}s"

    return {
        "task": task_text,
        "url": url,
        "outcome": outcome,
        "detail": detail,
        "duration_sec": round(time.perf_counter() - started, 1),
        "actions": actions,
        "events": events,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Real-browser agent E2E with independent cart verification")
    parser.add_argument("task", help="natural-language shopping task")
    parser.add_argument("url", nargs="?", default=f"http://{STORE_MARKER}/")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--expect", default="", help="substring the cart must contain to count as the right product")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    capture = _attach_capture()

    server, server_task = await serve_backend()
    try:
        cleared = await reset_cart()
        print(f"\n[setup] provider chain / browser: {capture.lines[:1]}")
        print(f"[setup] cart cleared -> {cleared}")

        result = await drive_run(args.task, args.url, timeout_sec=args.timeout)
        cart = await read_cart()

        rows = _llm_call_rows(capture.lines)
        result["llm_calls"] = rows
        result["llm_retries"] = sum(int(row.get("retries", 0) or 0) for row in rows)
        result["llm_attempts"] = sum(int(row.get("attempts", 0) or 0) for row in rows)
        result["llm_failed_calls"] = sum(1 for row in rows if row.get("ok") == "False")
        result["providers_used"] = sorted({row.get("provider", "?") for row in rows})
        result["provider_log"] = [line for line in capture.lines if "LLM_CALL" not in line]
        result["cart"] = cart
        lines = cart.get("lines", []) if isinstance(cart, dict) else []
        total_qty = sum(int(line.get("quantity") or 0) for line in lines)
        result["cart_item_count"] = total_qty
        titles = " | ".join(str(line.get("title")) for line in lines)
        if args.expect:
            result["correct_product"] = args.expect.lower() in titles.lower()
        result["cart_titles"] = titles

        print("\n" + "=" * 78)
        print(json.dumps({k: result[k] for k in (
            "task", "outcome", "detail", "duration_sec", "cart_item_count", "cart_titles",
            "correct_product", "llm_calls", "llm_retries", "llm_attempts", "llm_failed_calls",
            "providers_used", "actions",
        ) if k in result}, indent=2)[:4000])
        print("=" * 78)
        print("provider/failover log lines:")
        for line in result["provider_log"][:25]:
            print("   ", line[:200])
        return 0
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=15)
        except Exception:
            server_task.cancel()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
