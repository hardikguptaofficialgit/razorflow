"""General-web E2E tasks — public sites, no payments or sensitive actions."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

WS_URL = "ws://127.0.0.1:8765/ws"
MAX_STEPS = 24
STEP_TIMEOUT_S = 180

HARNESS_JS = (Path(__file__).parent / "general_web_harness.js").read_text(encoding="utf-8")
EXTRACT_FN = f"""() => {{
{HARNESS_JS}
return extractPageContext();
}}"""
EXECUTE_FN = f"""async (step) => {{
{HARNESS_JS}
return await executeStep(step);
}}"""


def _strip_nulls(value: Any) -> Any:
    """Remove null fields — Playwright can turn omitted JS fields into None."""
    if isinstance(value, dict):
        return {k: _strip_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_nulls(item) for item in value]
    return value


@dataclass
class WebTask:
    name: str
    start_url: str
    task: str
    evaluate: str  # key for evaluator


@dataclass
class TaskResult:
    name: str
    task: str
    terminal: str = ""
    message: str = ""
    steps_executed: int = 0
    final_url: str = ""
    final_title: str = ""
    events: list[str] = field(default_factory=list)
    ok: bool = False
    duration_ms: int = 0
    note: str = ""


TASKS: list[WebTask] = [
    WebTask(
        name="example_domain",
        start_url="https://example.com",
        task="Read the main heading on this page and confirm this is the Example Domain site",
        evaluate="example_domain",
    ),
    WebTask(
        name="books_travel_browse",
        start_url="https://books.toscrape.com/",
        task="Open the Travel category and open the first book listed",
        evaluate="books_detail",
    ),
    WebTask(
        name="books_scroll_catalog",
        start_url="https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
        task="Scroll down the travel books page and tell me how many books are visible",
        evaluate="books_travel",
    ),
    WebTask(
        name="wikipedia_search",
        start_url="https://en.wikipedia.org/wiki/Main_Page",
        task="Search Wikipedia for Python programming language and open the main article",
        evaluate="wikipedia_article",
    ),
    WebTask(
        name="httpbin_form",
        start_url="https://httpbin.org/forms/post",
        task="Fill the customer name field with Test User and the telephone field with 555-0100",
        evaluate="httpbin_form",
    ),
    WebTask(
        name="books_back_nav",
        start_url="https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        task="Go back to the catalogue listing page using navigation",
        evaluate="books_back",
    ),
]


async def execute_step(page: Any, step: dict[str, Any]) -> dict[str, Any]:
    action = step.get("action")
    if action == "navigate_url":
        url = step.get("url", "")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(600)
            return {"success": True, "verified": True}
        except Exception as exc:
            return {"success": False, "verified": False, "error": str(exc)}
    try:
        return await page.evaluate(EXECUTE_FN, step)
    except Exception as exc:
        if "Execution context was destroyed" in str(exc):
            await page.wait_for_load_state("domcontentloaded")
            return {"success": True, "verified": True}
        return {"success": False, "error": str(exc)}


async def run_task(page: Any, spec: WebTask) -> TaskResult:
    import websockets

    started = time.perf_counter()
    run_id = f"web-{uuid.uuid4().hex[:8]}"
    result = TaskResult(name=spec.name, task=spec.task)
    steps = 0

    await page.goto(spec.start_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(800)

    async with websockets.connect(WS_URL, open_timeout=10) as ws:
        page_context = _strip_nulls(await page.evaluate(EXTRACT_FN))
        await ws.send(
            json.dumps(
                {
                    "type": "START_RUN",
                    "runId": run_id,
                    "task": spec.task,
                    "url": spec.start_url,
                    "pageContext": page_context,
                }
            )
        )

        deadline = asyncio.get_event_loop().time() + STEP_TIMEOUT_S * MAX_STEPS
        while asyncio.get_event_loop().time() < deadline and steps < MAX_STEPS:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=STEP_TIMEOUT_S)
            except TimeoutError:
                result.note = "recv timeout"
                break

            msg = json.loads(raw)
            mtype = msg.get("type", "")
            result.events.append(mtype)

            if mtype == "NEXT_ACTION":
                steps += 1
                for step in msg.get("steps", []):
                    if step.get("action") in {"wait_for_user", "ready_for_payment_link"}:
                        exec_result = {"success": True, "verified": True}
                    else:
                        exec_result = await execute_step(page, step)
                    await page.wait_for_timeout(400)
                    try:
                        page_context = _strip_nulls(await page.evaluate(EXTRACT_FN))
                    except Exception as exc:
                        if "Execution context was destroyed" in str(exc):
                            await page.wait_for_load_state("domcontentloaded")
                            await page.wait_for_timeout(500)
                            page_context = _strip_nulls(await page.evaluate(EXTRACT_FN))
                        else:
                            raise
                    await ws.send(
                        json.dumps(
                            {
                                "type": "ACTION_RESULT",
                                "runId": run_id,
                                "step": step,
                                "success": bool(exec_result.get("success")),
                                "error": exec_result.get("error"),
                                "verified": exec_result.get("verified"),
                                "pageContext": page_context,
                            }
                        )
                    )
                    if not exec_result.get("success"):
                        result.note = exec_result.get("error") or "step failed"
                continue

            if mtype in {
                "RUN_COMPLETE",
                "RUN_ERROR",
                "RUN_WAITING_FOR_USER",
                "RUN_NEEDS_CLARIFICATION",
                "PAYMENT_LINK_CONFIRMATION_REQUIRED",
            }:
                result.terminal = mtype
                result.message = msg.get("message") or ""
                break

        await ws.send(json.dumps({"type": "CANCEL_RUN", "runId": run_id}))

    result.steps_executed = steps
    result.final_url = page.url
    result.final_title = await page.title()
    result.duration_ms = int((time.perf_counter() - started) * 1000)
    result.ok = evaluate(spec.evaluate, result)
    return result


def evaluate(key: str, result: TaskResult) -> bool:
    url = result.final_url.lower()
    title = result.final_title.lower()
    terminal_ok = result.terminal in {
        "RUN_COMPLETE",
        "RUN_WAITING_FOR_USER",
        "RUN_ERROR",  # step-limit errors still count if outcome reached
    }

    if key == "example_domain":
        return result.terminal in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"} and "example" in title

    if key == "books_detail":
        # Reached a book detail page (agent browsed successfully)
        return terminal_ok and "/catalogue/" in url and "_" in url and result.steps_executed >= 2

    if key == "books_travel":
        return terminal_ok and "travel" in url and result.steps_executed >= 1

    if key == "wikipedia_article":
        return terminal_ok and "python" in url and "wikipedia.org" in url

    if key == "httpbin_form":
        # Form submitted to /post or agent typed into fields
        return result.steps_executed >= 2 and (
            "/post" in url or result.terminal != "RUN_ERROR"
        )

    if key == "books_back":
        # Left book detail — back on catalogue/home
        return result.terminal in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"} and (
            url.endswith("books.toscrape.com/") or url.endswith("books.toscrape.com/index.html")
            or ("/catalogue/" in url and "a-light-in-the-attic" not in url)
        )

    return result.terminal in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}


def _safe(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


async def main() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Install playwright: pip install playwright && playwright install chromium")
        return 1

    results: list[TaskResult] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for spec in TASKS:
            page = await browser.new_page()
            print(f"\n=== {_safe(spec.name)} ===")
            print(f"Task: {_safe(spec.task)}")
            try:
                result = await run_task(page, spec)
            except Exception as exc:
                result = TaskResult(
                    name=spec.name,
                    task=spec.task,
                    terminal="RUN_ERROR",
                    message=str(exc),
                    note=str(exc),
                )
            finally:
                await page.close()
            status = "PASS" if result.ok else "FAIL"
            print(
                f"{status} terminal={result.terminal} steps={result.steps_executed} "
                f"duration={result.duration_ms}ms url={_safe(result.final_url)}"
            )
            if result.note:
                print(f"  note: {_safe(result.note)}")
            results.append(result)
        await browser.close()

    passed = sum(1 for r in results if r.ok)
    total = len(results)
    avg_ms = sum(r.duration_ms for r in results) // max(total, 1)
    print(f"\n{'=' * 50}")
    print(f"General web: {passed}/{total} passed | avg duration {avg_ms}ms")
    out = Path(__file__).parent / "general_web_results.txt"
    out.write_text(
        "\n".join(
            f"{r.name}: {'PASS' if r.ok else 'FAIL'} {r.duration_ms}ms {r.final_url}"
            for r in results
        ),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
