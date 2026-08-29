"""Real browser validation through the RazorFlow chat UI (no harness bypass)."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

STORE_URL = "http://localhost:3001/demo"
TASK_TIMEOUT_S = 180

REAL_UI_TASKS = [
    "search for wireless earbuds",
    "find good wireless earbuds under ₹6000",
    "add good snacks under ₹200 to my cart",
    "add the best cooker under ₹2000 to my cart",
    "add butter, chips and cooker to my cart",
    "open my cart",
    "remove the headphones from my cart",
    "add good snacks under ₹200 and checkout",
    "find the cheapest smartwatch",
    "find wireless earbuds and add the best one to my cart",
]

TRACE_INIT_SCRIPT = """
window.__RF_ENABLE_EXECUTION_TRACE__ = true;
window.__RF_EXECUTION_TRACE__ = [];
"""


@dataclass
class RealUiTaskResult:
    task: str
    success: bool = False
    duration_s: float = 0.0
    handoff: bool = False
    error: str = ""
    final_url: str = ""
    cart_count: int = 0
    ws_events: list[str] = field(default_factory=list)
    ws_trace: list[dict[str, Any]] = field(default_factory=list)
    execution_trace: list[dict[str, Any]] = field(default_factory=list)
    cursor_mismatches: int = 0
    verification_failures: int = 0
    subsystem_failure: str = ""


def _cursor_aligned(trace: list[dict[str, Any]]) -> tuple[int, int]:
    """Return (aligned_count, mismatch_count) for cursor vs target rect."""
    aligned = 0
    mismatches = 0
    last_cursor = None
    for entry in trace:
        if entry.get("kind") == "cursor_position" and entry.get("cursor"):
            last_cursor = entry["cursor"]
        if entry.get("kind") == "target_resolved" and entry.get("target"):
            rect = entry["target"]["rect"]
            if not last_cursor:
                continue
            cx = rect["x"] + rect["width"] / 2
            cy = rect["y"] + rect["height"] / 2
            dx = abs(last_cursor["x"] - cx)
            dy = abs(last_cursor["y"] - cy)
            if dx <= 80 and dy <= 80:
                aligned += 1
            else:
                mismatches += 1
    return aligned, mismatches


async def _wait_backend(page: Any, timeout_s: int = 30) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        await page.wait_for_timeout(500)
    return False


async def _open_agent_panel(page: Any) -> None:
    launcher = page.locator("button.rf-agent-launcher")
    await launcher.wait_for(state="visible", timeout=30000)
    expanded = await launcher.get_attribute("aria-expanded")
    if expanded != "true":
        await launcher.click()
    panel = page.locator(".rf-agent-panel")
    try:
        await panel.wait_for(state="visible", timeout=10000)
    except Exception:
        await launcher.click()
        await panel.wait_for(state="visible", timeout=10000)
    for _ in range(60):
        connected = await page.evaluate(
            """() => {
              const root = document.querySelector('[data-rf-agent-root]');
              const input = document.querySelector('.rf-agent-compose input');
              if (!input) return false;
              const placeholder = input.getAttribute('placeholder') || '';
              return !placeholder.toLowerCase().includes('connecting');
            }"""
        )
        if connected:
            break
        await page.wait_for_timeout(500)
    await page.wait_for_timeout(300)


async def _type_controlled_input(page: Any, selector: str, text: str) -> None:
    """Type into a React controlled input (fill() does not update React state)."""
    input_el = page.locator(selector)
    await input_el.click()
    await input_el.fill("")
    await input_el.press_sequentially(text, delay=15)


async def _submit_task_via_ui(page: Any, task: str) -> None:
    await _type_controlled_input(page, ".rf-agent-compose input", task)
    send = page.locator(".rf-agent-compose__send")
    await send.wait_for(state="visible", timeout=5000)
    await page.wait_for_function(
        """() => {
          const btn = document.querySelector('.rf-agent-compose__send');
          return btn && !btn.hasAttribute('disabled');
        }""",
        timeout=10000,
    )
    await send.click()
    # Run must leave idle after submit (planning/acting at minimum).
    await page.wait_for_function(
        """() => {
          const launcher = document.querySelector('button.rf-agent-launcher');
          const phase = launcher?.getAttribute('data-agent-phase') || 'idle';
          return phase !== 'idle';
        }""",
        timeout=30000,
    )


async def _wait_run_complete(page: Any, timeout_s: int = TASK_TIMEOUT_S) -> tuple[str, bool]:
    """Returns (terminal_phase, handoff_seen)."""
    deadline = time.time() + timeout_s
    handoff = False
    while time.time() < deadline:
        phase = await page.locator("button.rf-agent-launcher").get_attribute("data-agent-phase")
        if await page.locator(".rf-agent-handoff").count() > 0:
            handoff = True
        if phase == "complete":
            return "complete", handoff
        if phase == "error":
            return "error", handoff
        if phase == "waiting_for_user":
            return "handoff", True
        await page.wait_for_timeout(500)
    return "timeout", handoff


async def _clear_cart(page: Any) -> None:
    await page.goto(f"{STORE_URL}/cart", wait_until="domcontentloaded", timeout=60000)
    await page.evaluate(
        """() => {
          localStorage.setItem('rf-market-cart', '[]');
          window.dispatchEvent(new Event('storage'));
        }"""
    )
    while True:
        btn = page.locator("[data-rf-remove-item]").first
        if await btn.count() == 0:
            break
        await btn.click()
        await page.wait_for_timeout(250)
    await page.context.clear_cookies()
    await page.reload(wait_until="domcontentloaded")


async def _seed_headphones(page: Any) -> None:
    await page.goto(f"{STORE_URL}/search?q={quote('headphones')}", wait_until="domcontentloaded")
    await page.locator("[data-rf-add-to-cart]").first.click()
    await page.wait_for_timeout(400)


def _evaluate_task(task: str, result: RealUiTaskResult) -> bool:
    url = result.final_url.lower()
    t = task.lower()

    if result.handoff and "checkout" not in t:
        return False
    if result.error and result.subsystem_failure:
        return False

    if "search for wireless earbuds" in t:
        return "/search" in url and not result.handoff
    if "wireless earbuds under" in t and "add" not in t:
        return "/search" in url and "/product" not in url and not result.handoff
    if "add good snacks" in t and "checkout" not in t:
        return result.cart_count >= 1 and "/checkout" not in url
    if "best cooker" in t:
        return result.cart_count >= 1
    if "butter, chips and cooker" in t:
        return result.cart_count >= 3
    if t == "open my cart":
        return "/cart" in url
    if "remove the headphones" in t:
        return "/cart" in url
    if "checkout" in t:
        return result.cart_count >= 1 and (
            "/checkout" in url or "auth=login" in url or result.handoff
        )
    if "cheapest smartwatch" in t:
        return "/search" in url and not result.handoff
    if "add the best one" in t:
        return result.cart_count >= 1
    return False


async def run_real_ui_task(page: Any, task: str, ws_trace: list[dict[str, Any]] | None = None) -> RealUiTaskResult:
    result = RealUiTaskResult(task=task)
    started = time.perf_counter()
    task_ws: list[dict[str, Any]] = []

    def _on_ws(ws: Any) -> None:
        def record(direction: str, payload: str | bytes) -> None:
            raw = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload)
            try:
                parsed = json.loads(raw)
                event_type = parsed.get("type", "unknown")
            except json.JSONDecodeError:
                event_type = "raw"
            entry = {"direction": direction, "type": event_type, "at": time.time()}
            task_ws.append(entry)
            if ws_trace is not None:
                ws_trace.append(entry)

        ws.on("framesent", lambda payload: record("out", payload))
        ws.on("framereceived", lambda payload: record("in", payload))

    page.on("websocket", _on_ws)

    await page.evaluate("() => { window.__RF_EXECUTION_TRACE__ = []; }")
    await _open_agent_panel(page)
    await _submit_task_via_ui(page, task)

    terminal, handoff = await _wait_run_complete(page)
    result.handoff = handoff
    result.duration_s = time.perf_counter() - started
    result.final_url = page.url

    cart_text = await page.locator("[data-rf-cart-count]").first.text_content()
    result.cart_count = int(re.search(r"\d+", cart_text or "0").group(0)) if cart_text else 0

    trace = await page.evaluate("() => window.__RF_EXECUTION_TRACE__ || []")
    result.execution_trace = trace
    result.ws_trace = task_ws
    result.ws_events = [f"{e['direction']}:{e['type']}" for e in task_ws]

    aligned, mismatches = _cursor_aligned(trace)
    result.cursor_mismatches = mismatches
    result.verification_failures = sum(
        1
        for e in trace
        if e.get("kind") == "action_result"
        and e.get("result", {}).get("success")
        and e.get("result", {}).get("verified") is False
    )

    if terminal == "error":
        result.error = await page.locator(".rf-agent-timeline__text").last.text_content() or "error"
        result.subsystem_failure = "RUNTIME"
    elif terminal == "timeout":
        result.error = "timeout"
        result.subsystem_failure = "TRANSPORT"
    elif handoff and "checkout" not in task.lower():
        result.error = "unexpected handoff"
        result.subsystem_failure = "RECOVERY"

    # Prove executor used real DOM — trace must have target_resolved entries when actions ran
    has_real_execution = any(e.get("kind") == "target_resolved" for e in trace) or any(
        e.get("kind") == "action_result" for e in trace
    )
    if terminal == "complete" and not has_real_execution and "search" not in task.lower():
        result.subsystem_failure = "EXECUTOR"
        result.error = "no execution trace — possible bypass"

    result.success = _evaluate_task(task, result) and not result.subsystem_failure
    return result


async def main() -> None:
    from playwright.async_api import async_playwright

    results: list[RealUiTaskResult] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        await page.add_init_script(TRACE_INIT_SCRIPT)

        if not await _wait_backend(page):
            print("FAIL: agent backend not reachable on :8765")
            sys.exit(1)

        await page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

        for task in REAL_UI_TASKS:
            await _clear_cart(page)
            await page.goto(STORE_URL, wait_until="domcontentloaded")
            if "remove the headphones" in task.lower():
                await _seed_headphones(page)
                await page.goto(STORE_URL, wait_until="domcontentloaded")
            result = await run_real_ui_task(page, task)
            results.append(result)
            status = "PASS" if result.success else "FAIL"
            print(f"[{status}] {task}")
            print(f"  time={result.duration_s:.1f}s cart={result.cart_count} handoff={result.handoff}")
            print(f"  url={result.final_url}")
            if result.error:
                print(f"  error={result.error} subsystem={result.subsystem_failure}")
            print(f"  ws_events={result.ws_events[-8:]}")
            print(f"  trace_entries={len(result.execution_trace)} cursor_mismatch={result.cursor_mismatches}")
            for entry in result.execution_trace[-6:]:
                print(f"    {entry.get('kind')}: {json.dumps(entry, default=str)[:200]}")
            print("-" * 72)

        await browser.close()

    passed = sum(1 for r in results if r.success)
    print("REAL UI SCORE:", f"{passed}/{len(results)}")
    out = ROOT / "tests" / "agent" / "real_ui_results.json"
    out.write_text(
        json.dumps([r.__dict__ for r in results], indent=2, default=str),
        encoding="utf-8",
    )
    print("Wrote", out)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    asyncio.run(main())
