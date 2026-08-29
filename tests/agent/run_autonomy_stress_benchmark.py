"""Autonomy stress benchmark — non-scripted tasks, real browser + WebSocket runtime."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.agent.ws_harness import run_ws_task

STORE_URL = "http://localhost:3001/demo"
TRACE_LOG = ROOT / "agent-backend" / "logs" / "agent_runtime_v2.jsonl"
FIXTURE_20 = ROOT / "tests" / "agent" / "fixtures" / "target_resolution_page.html"
FIXTURE_DOM = ROOT / "tests" / "agent" / "fixtures" / "dom_recovery.html"
OUT = ROOT / "tests" / "agent" / "autonomy_stress_results.json"


@dataclass
class StressTask:
    id: str
    task: str
    page_url: str
    evaluate: Callable[[dict[str, Any]], tuple[bool, str]]
    setup_js: str | None = None
    max_steps: int = 24


@dataclass
class StressResult:
    task_id: str
    task: str
    success: bool
    reason: str = ""
    terminal: str = ""
    duration_s: float = 0.0
    steps: int = 0
    llm_calls: int = 0
    recovery_count: int = 0
    loop_events: int = 0
    wrong_target: bool = False
    false_completion: bool = False
    false_handoff: bool = False
    unnecessary_actions: int = 0
    actions: list[str] = field(default_factory=list)


def _trace_metrics(run_id: str) -> dict[str, int]:
    if not TRACE_LOG.is_file():
        return {"llm_calls": 0, "recovery_count": 0, "loop_events": 0}
    llm = recovery = loops = 0
    for line in TRACE_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()[-8000:]:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("runId") != run_id:
            continue
        et = ev.get("event", "")
        if et == "PLAN":
            llm += 1
        if et in {"RECOVERY", "PLAN_PARSE_RECOVERY", "LOOP_DETECTED"}:
            recovery += 1
        if et == "LOOP_DETECTED":
            loops += 1
    return {"llm_calls": llm, "recovery_count": recovery, "loop_events": loops}


def _eval_cheapest_smartwatch(ctx: dict[str, Any]) -> tuple[bool, str]:
    url = ctx.get("final_url", "")
    terminal = ctx.get("terminal", "")
    cart = ctx.get("cart_count", 0)
    if cart > 0:
        return False, "incorrectly added to cart"
    if terminal not in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}:
        return False, f"terminal={terminal}"
    if "/search" in url and "smartwatch" in url.lower():
        return True, "search results for smartwatch"
    return False, f"expected search results, got {url}"


def _eval_under_budget_inspect(ctx: dict[str, Any]) -> tuple[bool, str]:
    terminal = ctx.get("terminal", "")
    url = ctx.get("final_url", "")
    cart = ctx.get("cart_count", 0)
    if cart > 0:
        return False, "escalated to cart add"
    if "/checkout" in url:
        return False, "escalated to checkout"
    if terminal not in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}:
        return False, f"terminal={terminal}"
    if "/search" in url:
        return True, "inspect on search results without add"
    return False, f"url={url}"


def _eval_compare_add_best(ctx: dict[str, Any]) -> tuple[bool, str]:
    terminal = ctx.get("terminal", "")
    cart = ctx.get("cart_count", 0)
    if cart > 1:
        return False, f"over-added cart={cart}"
    if terminal not in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}:
        return False, f"terminal={terminal}"
    if cart >= 1:
        return True, f"cart={cart}"
    return False, f"cart={cart}"


def _eval_twenty_button(ctx: dict[str, Any]) -> tuple[bool, str]:
    expected = ctx.get("expected_product")
    clicked = ctx.get("clicked_product")
    terminal = ctx.get("terminal", "")
    if terminal not in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}:
        return False, f"terminal={terminal}"
    if clicked != expected:
        return False, f"clicked={clicked} expected={expected}"
    return True, f"clicked={clicked}"


def _eval_dom_disappear(ctx: dict[str, Any]) -> tuple[bool, str]:
    terminal = ctx.get("terminal", "")
    if terminal == "RUN_COMPLETE":
        return False, "false completion on disappear scenario"
    if ctx.get("steps", 0) >= 1:
        return True, f"recovered/replanned steps={ctx['steps']}"
    return False, "no recovery attempted"


def _eval_scroll_find(ctx: dict[str, Any]) -> tuple[bool, str]:
    scroll_used = ctx.get("scroll_used", False)
    terminal = ctx.get("terminal", "")
    cart = ctx.get("cart_count", 0)
    if cart > 1:
        return False, f"over-added cart={cart}"
    if terminal not in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}:
        return False, f"terminal={terminal}"
    if cart >= 1:
        return True, f"added cart={cart} scroll={scroll_used}"
    return False, f"cart={cart}"


STRESS_TASKS: list[StressTask] = [
    StressTask(
        id="cheapest_smartwatch",
        task="Find the cheapest smartwatch on this site",
        page_url=STORE_URL,
        evaluate=_eval_cheapest_smartwatch,
        max_steps=16,
    ),
    StressTask(
        id="under_200_inspect_best",
        task="Find a snack under ₹200, inspect several results, and choose the best one",
        page_url=STORE_URL,
        evaluate=_eval_under_budget_inspect,
        max_steps=20,
    ),
    StressTask(
        id="compare_earbuds_add_best",
        task="Find wireless earbuds, compare multiple results, then add the best one to my cart",
        page_url=STORE_URL,
        evaluate=_eval_compare_add_best,
        max_steps=24,
    ),
    StressTask(
        id="twenty_button_buds",
        task="add Galaxy Buds FE to my cart",
        page_url=FIXTURE_20.as_uri(),
        evaluate=_eval_twenty_button,
        max_steps=16,
    ),
    StressTask(
        id="twenty_button_butter",
        task="add Amul Butter 100g to my cart",
        page_url=FIXTURE_20.as_uri(),
        evaluate=_eval_twenty_button,
        max_steps=16,
    ),
    StressTask(
        id="dom_disappear_recovery",
        task="click the Submit order button",
        page_url=FIXTURE_DOM.as_uri(),
        setup_js="() => window.__RF_SET_SCENARIO__('disappear')",
        evaluate=_eval_dom_disappear,
        max_steps=12,
    ),
    StressTask(
        id="scroll_add_cooker",
        task="Find a cooker on this page and add one to my cart",
        page_url=STORE_URL,
        evaluate=_eval_scroll_find,
        max_steps=20,
    ),
]

PRODUCT_EXPECTATIONS = {
    "twenty_button_buds": "buds-fe",
    "twenty_button_butter": "butter-amul",
}


async def run_task(spec: StressTask) -> StressResult:
    from playwright.async_api import async_playwright

    result = StressResult(task_id=spec.id, task=spec.task, success=False)
    started = time.perf_counter()
    clicked_product: str | None = None
    scroll_used = False
    cart_count = 0
    action_types: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(spec.page_url, wait_until="domcontentloaded")
        if spec.setup_js:
            await page.evaluate(spec.setup_js)

        async def after_execute(step: dict, exec_result: dict, _turn: int) -> None:
            nonlocal clicked_product, scroll_used, cart_count
            action_types.append(step.get("action", "?"))
            if step.get("action") == "scroll_page":
                scroll_used = True
            cart = await page.evaluate(
                "() => (window.__RF_LAST_CART__?.() || []).length"
            )
            if cart:
                last = await page.evaluate(
                    "() => { const c = window.__RF_LAST_CART__?.(); return c?.[c.length-1] || null; }"
                )
                clicked_product = last
            badge = await page.evaluate(
                """() => {
                  const el = document.querySelector('[data-rf-cart-count]');
                  const m = el?.textContent?.match(/\\d+/);
                  return m ? parseInt(m[0], 10) : 0;
                }"""
            )
            cart_count = max(cart_count, badge or 0)

        ws_result = await run_ws_task(
            page,
            spec.task,
            max_steps=spec.max_steps,
            step_timeout_s=180 if spec.page_url.startswith("file:") else 120,
            after_execute=after_execute,
        )
        final_url = page.url
        await browser.close()

    result.duration_s = time.perf_counter() - started
    result.terminal = ws_result.terminal
    result.steps = ws_result.steps
    metrics = _trace_metrics(ws_result.run_id)
    result.llm_calls = metrics["llm_calls"]
    result.recovery_count = metrics["recovery_count"]
    result.loop_events = metrics["loop_events"]
    result.actions = action_types

    ctx = {
        "task": spec.task,
        "terminal": ws_result.terminal,
        "final_url": final_url,
        "cart_count": cart_count,
        "clicked_product": clicked_product,
        "expected_product": PRODUCT_EXPECTATIONS.get(spec.id),
        "scroll_used": scroll_used,
        "steps": ws_result.steps,
    }
    ok, reason = spec.evaluate(ctx)
    result.success = ok
    result.reason = reason
    result.false_completion = ws_result.terminal == "RUN_COMPLETE" and not ok
    result.false_handoff = (
        ws_result.terminal == "RUN_WAITING_FOR_USER"
        and "checkout" not in spec.task.lower()
        and not ok
    )
    if spec.id.startswith("twenty_button") and clicked_product:
        result.wrong_target = clicked_product != PRODUCT_EXPECTATIONS.get(spec.id)
    if ws_result.steps > 8 and not ok:
        result.unnecessary_actions = ws_result.steps - 8
    return result


async def main() -> None:
    results: list[StressResult] = []
    for spec in STRESS_TASKS:
        print(f"Running: {spec.id} ...", flush=True)
        try:
            r = await run_task(spec)
        except Exception as exc:
            r = StressResult(
                task_id=spec.id,
                task=spec.task,
                success=False,
                reason=str(exc),
            )
        results.append(r)
        status = "PASS" if r.success else "FAIL"
        print(
            f"  [{status}] {spec.id} terminal={r.terminal} steps={r.steps} "
            f"llm={r.llm_calls} recovery={r.recovery_count} {r.duration_s:.1f}s"
        )
        if r.reason:
            print(f"         {r.reason}")

    passed = sum(1 for r in results if r.success)
    summary = {
        "timestamp": time.time(),
        "passed": passed,
        "total": len(results),
        "success_rate": round(passed / len(results), 3) if results else 0,
        "aggregate": {
            "total_steps": sum(r.steps for r in results),
            "total_llm_calls": sum(r.llm_calls for r in results),
            "total_recovery": sum(r.recovery_count for r in results),
            "total_loop_events": sum(r.loop_events for r in results),
            "wrong_target_count": sum(1 for r in results if r.wrong_target),
            "false_completion_count": sum(1 for r in results if r.false_completion),
            "false_handoff_count": sum(1 for r in results if r.false_handoff),
            "avg_latency_s": round(
                sum(r.duration_s for r in results) / len(results), 2
            )
            if results
            else 0,
        },
        "tasks": [r.__dict__ for r in results],
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSTRESS BENCHMARK: {passed}/{len(results)}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
