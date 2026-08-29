"""Final autonomy validation — real browser + WebSocket runtime."""

from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from tests.agent.run_live_e2e_tasks import (  # noqa: E402
    EXECUTE_STEP_JS,
    EXTRACT_PAGE_CONTEXT_JS,
    STORE_URL,
    clear_cart,
    execute_step,
)
from tests.agent.ws_harness import WS_CONNECT_KWARGS, run_ws_task

FIXTURE_DOM = ROOT / "tests" / "agent" / "fixtures" / "dom_recovery.html"
WS_URL = "ws://127.0.0.1:8765/ws"


@dataclass
class ValidationCase:
    id: str
    label: str
    task: str
    page_url: str
    evaluate: Callable[[dict[str, Any]], tuple[bool, str]]
    setup_js: str | None = None
    on_waiting: Callable[[Any, str], Any] | None = None
    max_steps: int = 24


async def _cart_count(page: Any) -> int:
    text = await page.locator("[data-rf-cart-count]").first.text_content()
    if not text:
        return 0
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else 0


async def _run_store_task(
    page: Any,
    task: str,
    *,
    max_steps: int = 24,
    on_waiting: Callable[[Any, str], Any] | None = None,
) -> dict[str, Any]:
    import websockets

    run_id = f"val-{uuid.uuid4().hex[:8]}"
    terminal = ""
    message = ""
    steps = 0
    events: list[str] = []

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

        deadline = asyncio.get_event_loop().time() + 120 * max_steps
        while asyncio.get_event_loop().time() < deadline and steps < max_steps:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
            except TimeoutError:
                terminal = "RECV_TIMEOUT"
                break

            msg = json.loads(raw)
            mtype = msg.get("type", "")
            events.append(mtype)

            if mtype == "NEXT_ACTION" and msg.get("runId") == run_id:
                steps += 1
                for step in msg.get("steps", []):
                    if step.get("action") in {"wait_for_user", "ready_for_payment_link"}:
                        exec_result = {"success": True, "verified": True}
                    else:
                        exec_result = await execute_step(page, step)
                    await page.wait_for_timeout(400)
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

            if mtype == "RUN_WAITING_FOR_USER" and msg.get("runId") == run_id:
                if on_waiting:
                    await on_waiting(page, run_id)
                    page_context = await page.evaluate(EXTRACT_PAGE_CONTEXT_JS)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "RESUME_RUN",
                                "runId": run_id,
                                "pageContext": page_context,
                            }
                        )
                    )
                    continue
                terminal = mtype
                message = msg.get("message") or ""
                break

            if mtype in {
                "RUN_COMPLETE",
                "RUN_ERROR",
                "RUN_NEEDS_CLARIFICATION",
                "PAYMENT_LINK_CONFIRMATION_REQUIRED",
            } and msg.get("runId") == run_id:
                terminal = mtype
                message = msg.get("message") or ""
                break

        try:
            await ws.send(json.dumps({"type": "CANCEL_RUN", "runId": run_id}))
        except Exception:
            pass

    return {
        "run_id": run_id,
        "terminal": terminal,
        "message": message,
        "steps": steps,
        "events": events,
        "final_url": page.url,
        "cart_count": await _cart_count(page),
    }


async def _simulate_checkout_login(page: Any, _run_id: str) -> None:
    """Complete demo-store auth gate so RESUME can reach checkout."""
    await page.evaluate(
        """() => {
          const modal = document.querySelector('[data-rf-auth-modal]');
          if (modal) modal.remove();
          const next = new URLSearchParams(location.search).get('next') || '/demo/checkout';
          if (!location.pathname.includes('checkout')) {
            history.pushState({}, '', next.startsWith('/') ? next : '/demo/checkout');
            window.dispatchEvent(new PopStateEvent('popstate'));
          }
        }"""
    )
    await page.wait_for_timeout(500)


def _eval_multi_item(ctx: dict[str, Any]) -> tuple[bool, str]:
    if ctx["terminal"] != "RUN_COMPLETE":
        return False, f"terminal={ctx['terminal']}"
    if ctx["cart_count"] < 2:
        return False, f"cart={ctx['cart_count']}"
    return True, f"cart={ctx['cart_count']}"


def _eval_two_snacks(ctx: dict[str, Any]) -> tuple[bool, str]:
    if ctx["terminal"] != "RUN_COMPLETE":
        return False, f"terminal={ctx['terminal']}"
    if ctx["cart_count"] < 2:
        return False, f"cart={ctx['cart_count']}"
    return True, f"cart={ctx['cart_count']}"


def _eval_search_inspect_add(ctx: dict[str, Any]) -> tuple[bool, str]:
    url = ctx["final_url"].lower()
    if ctx["terminal"] != "RUN_COMPLETE":
        return False, f"terminal={ctx['terminal']}"
    if ctx["cart_count"] < 1:
        return False, "no cart add"
    if "/search" not in url and ctx["steps"] < 2:
        return False, "expected search then add"
    return True, f"cart={ctx['cart_count']} steps={ctx['steps']}"


def _eval_compare_add(ctx: dict[str, Any]) -> tuple[bool, str]:
    if ctx["terminal"] not in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}:
        return False, f"terminal={ctx['terminal']}"
    if ctx["cart_count"] < 1:
        return False, f"cart={ctx['cart_count']}"
    if ctx["cart_count"] > 1:
        return False, f"over-added cart={ctx['cart_count']}"
    return True, f"cart={ctx['cart_count']}"


def _eval_scroll_find(ctx: dict[str, Any]) -> tuple[bool, str]:
    if ctx["terminal"] != "RUN_COMPLETE":
        return False, f"terminal={ctx['terminal']}"
    if ctx["cart_count"] < 1:
        return False, f"cart={ctx['cart_count']}"
    return True, f"cart={ctx['cart_count']} scroll={ctx.get('scroll_used')}"


def _eval_dom_recovery(ctx: dict[str, Any]) -> tuple[bool, str]:
    if ctx["terminal"] == "RUN_COMPLETE":
        return False, "false completion on adversarial DOM"
    if ctx["steps"] < 1:
        return False, "no recovery attempt"
    clicks = ctx.get("clicks", 0)
    if clicks >= 1:
        return True, f"recovered clicks={clicks} steps={ctx['steps']}"
    return ctx["steps"] >= 2, f"replanned steps={ctx['steps']}"


def _eval_checkout_resume(ctx: dict[str, Any]) -> tuple[bool, str]:
    url = ctx["final_url"].lower()
    if ctx["terminal"] not in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}:
        return False, f"terminal={ctx['terminal']}"
    if ctx["cart_count"] < 1:
        return False, "empty cart"
    if "/checkout" in url or ("auth=login" in url and "checkout" in url):
        return True, "reached checkout gate"
    if ctx.get("resumed"):
        return True, "resumed after handoff"
    return False, f"url={url}"


def _eval_failed_recovery(ctx: dict[str, Any]) -> tuple[bool, str]:
    if ctx["terminal"] == "RUN_COMPLETE":
        return False, "false completion"
    clicks = ctx.get("clicks", 0)
    if clicks >= 1 and ctx["steps"] >= 2:
        return True, f"recovered after failure clicks={clicks}"
    return False, f"steps={ctx['steps']} clicks={clicks}"


CASES: list[ValidationCase] = [
    ValidationCase(
        id="multi_item_add",
        label="multi-item add",
        task="add a watch and earbuds to my cart",
        page_url=STORE_URL,
        evaluate=_eval_multi_item,
    ),
    ValidationCase(
        id="add_two_snacks",
        label='add 2 snacks',
        task="add 2 snacks under ₹200",
        page_url=STORE_URL,
        evaluate=_eval_two_snacks,
    ),
    ValidationCase(
        id="search_inspect_add",
        label="search → inspect → add",
        task="find snacks under ₹200, inspect the results, and add the best one to my cart",
        page_url=STORE_URL,
        evaluate=_eval_search_inspect_add,
        max_steps=28,
    ),
    ValidationCase(
        id="compare_choose_add",
        label="compare → choose → add",
        task="find wireless earbuds, compare multiple results, then add the best one to my cart",
        page_url=STORE_URL,
        evaluate=_eval_compare_add,
        max_steps=28,
    ),
    ValidationCase(
        id="scroll_find_act",
        label="scroll → find → act",
        task="Find a cooker on this page and add one to my cart",
        page_url=STORE_URL,
        evaluate=_eval_scroll_find,
        max_steps=24,
    ),
    ValidationCase(
        id="dom_stale_recovery",
        label="stale/changed DOM recovery",
        task="click the Submit order button",
        page_url=FIXTURE_DOM.as_uri(),
        setup_js="() => window.__RF_SET_SCENARIO__('duplicate')",
        evaluate=_eval_dom_recovery,
        max_steps=12,
    ),
    ValidationCase(
        id="checkout_handoff_resume",
        label="checkout → login handoff → resume",
        task="add snacks under ₹200 and checkout",
        page_url=STORE_URL,
        evaluate=_eval_checkout_resume,
        on_waiting=_simulate_checkout_login,
        max_steps=28,
    ),
    ValidationCase(
        id="failed_recovery_complete",
        label="failed action → recovery → completion",
        task="click the Submit order button",
        page_url=FIXTURE_DOM.as_uri(),
        setup_js="() => window.__RF_SET_SCENARIO__('cookie')",
        evaluate=_eval_failed_recovery,
        max_steps=14,
    ),
]


async def run_case(page: Any, case: ValidationCase) -> tuple[bool, str, dict[str, Any]]:
    if case.page_url.startswith("file:"):
        await page.goto(case.page_url, wait_until="domcontentloaded")
        if case.setup_js:
            await page.evaluate(case.setup_js)
        clicks = 0
        scroll_used = False

        async def after_execute(step: dict, _result: dict, _turn: int) -> None:
            nonlocal clicks, scroll_used
            if step.get("action") == "scroll_page":
                scroll_used = True
            c = await page.evaluate("() => window.__RF_CLICKS__?.() || 0")
            clicks = max(clicks, int(c or 0))

        ws_result = await run_ws_task(
            page,
            case.task,
            max_steps=case.max_steps,
            step_timeout_s=90,
            after_execute=after_execute,
        )
        ctx = {
            "terminal": ws_result.terminal,
            "steps": ws_result.steps,
            "clicks": clicks,
            "scroll_used": scroll_used,
            "final_url": page.url,
            "cart_count": 0,
        }
        ok, reason = case.evaluate(ctx)
        return ok, reason, ctx

    await page.goto(case.page_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(400)
    resumed = False

    async def on_waiting(p: Any, run_id: str) -> None:
        nonlocal resumed
        if case.on_waiting:
            await case.on_waiting(p, run_id)
            resumed = True

    ctx = await _run_store_task(
        page,
        case.task,
        max_steps=case.max_steps,
        on_waiting=on_waiting if case.on_waiting else None,
    )
    ctx["resumed"] = resumed
    ctx["scroll_used"] = "scroll_page" in " ".join(ctx.get("events", []))
    ok, reason = case.evaluate(ctx)
    return ok, reason, ctx


async def main() -> int:
    from playwright.async_api import async_playwright

    results: list[tuple[str, bool, str]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await clear_cart(page)

        for case in CASES:
            if not case.page_url.startswith("file:"):
                await page.goto(STORE_URL, wait_until="domcontentloaded")
                await clear_cart(page)
            ok, reason, _ctx = await run_case(page, case)
            results.append((case.label, ok, reason))
            print(f"[{'PASS' if ok else 'FAIL'}] {case.label}: {reason}")

        await browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\nSUMMARY: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
