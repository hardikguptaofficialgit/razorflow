"""Real agent benchmark — 12 user-facing tasks with execution traces."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from tests.agent.ws_harness import WS_CONNECT_KWARGS, WS_URL
from tests.agent.run_live_e2e_tasks import (  # noqa: E402
    EXTRACT_PAGE_CONTEXT_JS,
    STORE_URL,
    clear_cart,
    evaluate_task,
    execute_step,
)

BENCHMARK_TASKS = [
    "search for wireless earbuds",
    "find me good wireless earbuds under ₹6000",
    "add me some good snacks under ₹200",
    "add the best cooker under ₹2000 to my cart",
    "I want to buy a cooker for home, under ₹2000",
    "add amul butter, chips and cooker to my cart",
    "add 2 snacks under ₹200",
    "add good snacks under ₹200 and checkout",
    "buy good snacks under ₹200",
    "show me my cart",
    "remove the headphones from my cart",
    "find the cheapest smartwatch",
]

MAX_STEPS = 24
STEP_TIMEOUT_S = 120


@dataclass
class TraceEntry:
    event: str
    detail: str = ""
    step: int = 0


@dataclass
class BenchmarkResult:
    task: str
    intent: str = ""
    success: bool = False
    time_s: float = 0.0
    llm_calls: int = 0
    actions: int = 0
    failed_actions: int = 0
    recovery_count: int = 0
    unnecessary_actions: int = 0
    terminal: str = ""
    final_url: str = ""
    cart_count: int = 0
    failure_reason: str = ""
    trace: list[TraceEntry] = field(default_factory=list)


def _parse_intent(task: str) -> str:
    from agent_runtime.task.parse import parse_task_spec

    return parse_task_spec(task).intent


async def run_benchmark_task(page: Any, task: str) -> BenchmarkResult:
    import websockets

    from agent_runtime.task.parse import parse_task_spec

    run_id = f"bench-{uuid.uuid4().hex[:8]}"
    result = BenchmarkResult(task=task, intent=parse_task_spec(task).intent)
    started = time.perf_counter()
    steps = 0
    failed = 0

    async with websockets.connect(WS_URL, **WS_CONNECT_KWARGS) as ws:
        page_context = await page.evaluate(EXTRACT_PAGE_CONTEXT_JS)
        await ws.send(
            json.dumps(
                {
                    "type": "START_RUN",
                    "runId": run_id,
                    "task": task,
                    "pageContext": page_context,
                }
            )
        )

        deadline = asyncio.get_event_loop().time() + STEP_TIMEOUT_S * MAX_STEPS
        while asyncio.get_event_loop().time() < deadline and steps < MAX_STEPS:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=STEP_TIMEOUT_S)
            except TimeoutError:
                result.failure_reason = "recv timeout"
                break

            msg = json.loads(raw)
            mtype = msg.get("type", "")
            result.trace.append(
                TraceEntry(event=mtype, detail=(msg.get("message") or "")[:200], step=steps)
            )

            if mtype == "NEXT_ACTION":
                steps += 1
                result.actions += 1
                chat = msg.get("chatMessage") or msg.get("actionSummary") or ""
                if chat:
                    result.trace.append(TraceEntry(event="CHAT", detail=chat[:200], step=steps))
                for step in msg.get("steps", []):
                    exec_result = await execute_step(page, step)
                    if not exec_result.get("success") or exec_result.get("verified") is False:
                        failed += 1
                    await page.wait_for_timeout(500)
                    page_context = await page.evaluate(EXTRACT_PAGE_CONTEXT_JS)
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
                continue

            if mtype in {
                "RUN_COMPLETE",
                "RUN_ERROR",
                "RUN_WAITING_FOR_USER",
                "RUN_NEEDS_CLARIFICATION",
                "PAYMENT_LINK_CONFIRMATION_REQUIRED",
            }:
                result.terminal = mtype
                result.failure_reason = msg.get("message") or ""
                break

        await ws.send(json.dumps({"type": "CANCEL_RUN", "runId": run_id}))

    result.time_s = time.perf_counter() - started
    result.failed_actions = failed
    result.final_url = page.url
    cart_text = await page.locator("[data-rf-cart-count]").first.text_content()
    result.cart_count = (
        int(re.search(r"\d+", cart_text or "0").group(0)) if cart_text else 0
    )

    from tests.agent.run_live_e2e_tasks import TaskResult

    eval_input = TaskResult(
        task=task,
        terminal=result.terminal,
        message=result.failure_reason,
        steps_executed=steps,
        final_url=result.final_url,
        cart_count=result.cart_count,
    )
    evaluated = evaluate_task(task, eval_input)
    result.success = _task_success(task, result, evaluated.ok)
    if not result.success and not result.failure_reason:
        result.failure_reason = f"terminal={result.terminal} cart={result.cart_count}"
    return result


def _task_success(task: str, result: BenchmarkResult, legacy_ok: bool) -> bool:
    t = task.lower()
    url = result.final_url.lower()

    if result.terminal == "RUN_NEEDS_CLARIFICATION":
        return False

    if "search for wireless earbuds" in t:
        return result.terminal == "RUN_COMPLETE" and "/search" in url

    if "wireless earbuds under" in t:
        return result.terminal == "RUN_COMPLETE" and ("/search" in url or result.actions >= 2)

    if t.startswith("add me some good snacks"):
        return result.terminal == "RUN_COMPLETE" and result.cart_count >= 1 and "/checkout" not in url

    if "best cooker under" in t and "cart" in t:
        return result.terminal == "RUN_COMPLETE" and result.cart_count >= 1

    if "want to buy a cooker" in t:
        return result.terminal == "RUN_COMPLETE" and (
            result.cart_count >= 1 or "/search" in url
        )

    if "amul butter" in t:
        return result.terminal == "RUN_COMPLETE" and result.cart_count >= 3

    if t == "add 2 snacks under ₹200":
        return result.terminal == "RUN_COMPLETE" and result.cart_count >= 2

    if "checkout" in t:
        return result.terminal in {
            "RUN_COMPLETE",
            "RUN_WAITING_FOR_USER",
            "PAYMENT_LINK_CONFIRMATION_REQUIRED",
        } and result.cart_count >= 1 and (
            _demo_path_suffix(result.final_url, "/checkout")
            or "auth=login" in url
            or legacy_ok
        )

    if t == "buy good snacks under ₹200":
        return result.terminal == "RUN_COMPLETE" and result.cart_count >= 1 and "/checkout" not in url

    if t == "show me my cart":
        return result.terminal == "RUN_COMPLETE" and _demo_path_suffix(result.final_url, "/cart")

    if "remove the headphones" in t:
        return result.terminal == "RUN_COMPLETE" and _demo_path_suffix(result.final_url, "/cart")

    if "cheapest smartwatch" in t:
        return result.terminal == "RUN_COMPLETE" and ("/search" in url or result.actions >= 2)

    return legacy_ok


def _safe(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def _print_result(result: BenchmarkResult) -> None:
    status = "PASS" if result.success else "FAIL"
    print(f"[{status}] {_safe(result.task)}")
    print(
        f"  intent={result.intent} time={result.time_s:.1f}s "
        f"actions={result.actions} failed={result.failed_actions} "
        f"terminal={result.terminal} cart={result.cart_count}"
    )
    if result.failure_reason:
        print(f"  reason: {result.failure_reason[:160]}")
    print(f"  url: {result.final_url}")
    for entry in result.trace[-10:]:
        print(f"  trace[{entry.step}] {entry.event}: {entry.detail[:120]}")


def _demo_path_suffix(url: str, suffix: str) -> bool:
    from urllib.parse import urlparse

    path = urlparse(url).path.lower()
    return path.endswith(suffix) or f"{suffix}/" in path


async def seed_product(page: Any, query: str) -> None:
    from urllib.parse import quote

    await page.goto(
        f"{STORE_URL}/search?q={quote(query)}",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    await page.wait_for_timeout(600)
    btn = page.locator("[data-rf-add-to-cart]").first
    if await btn.count() > 0:
        await btn.click()
        await page.wait_for_timeout(500)


async def main() -> None:
    from playwright.async_api import async_playwright

    results: list[BenchmarkResult] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)

        print("=" * 80)
        print("RazorFlow Agent Benchmark")
        print("=" * 80)
        for task in BENCHMARK_TASKS:
            await clear_cart(page)
            await page.goto(STORE_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(400)
            if "remove the headphones" in task.lower():
                await seed_product(page, "headphones")
                await page.goto(STORE_URL, wait_until="domcontentloaded")
                await page.wait_for_timeout(400)
            result = await run_benchmark_task(page, task)
            results.append(result)
            _print_result(result)
            print("-" * 80)

        await browser.close()

    passed = sum(1 for r in results if r.success)
    total = len(results)
    avg_time = sum(r.time_s for r in results) / total if total else 0
    avg_actions = sum(r.actions for r in results) / total if total else 0
    print("SUMMARY")
    print(f"  SUCCESS RATE: {passed}/{total} ({100 * passed / total:.0f}%)")
    print(f"  AVERAGE LATENCY: {avg_time:.1f}s")
    print(f"  AVERAGE ACTIONS: {avg_actions:.1f}")
    failed = [r.task for r in results if not r.success]
    if failed:
        print("  FAILED:")
        for task in failed:
            print(f"    - {task}")


if __name__ == "__main__":
    asyncio.run(main())
