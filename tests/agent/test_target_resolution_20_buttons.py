"""20 identical Add-to-cart buttons — must click the correct product."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.agent.ws_harness import run_ws_task

FIXTURE = ROOT / "tests" / "agent" / "fixtures" / "target_resolution_page.html"

PRODUCT_TASKS = [
    ("add Galaxy Buds FE to my cart", "buds-fe"),
    ("add Amul Butter 100g to my cart", "butter-amul"),
    ("add Pigeon Cooker 3L to my cart", "cooker-pigeon"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("task,expected_id", PRODUCT_TASKS)
async def test_target_resolution_clicks_correct_product(
    task: str,
    expected_id: str,
) -> None:
    from playwright.async_api import async_playwright

    clicked_product: str | None = None
    planner_target = ""
    resolved_id = ""
    report: dict = {"task": task, "expected": expected_id}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(FIXTURE.as_uri(), wait_until="domcontentloaded")

        async def after_execute(step: dict, result: dict, _turn: int) -> None:
            nonlocal clicked_product, planner_target, resolved_id
            planner_target = step.get("matchText") or step.get("role") or ""
            cart = await page.evaluate("() => window.__RF_LAST_CART__?.() || []")
            if cart:
                clicked_product = cart[-1]
            resolved_id = await page.evaluate(
                """(step) => {
                  const idx = step.elementIndex;
                  if (!idx) return '';
                  const cards = document.querySelectorAll('[data-rf-product-card]');
                  const card = cards[idx - 1];
                  return card ? card.getAttribute('data-product-id') : '';
                }""",
                step,
            )
            report.update(
                {
                    "planner_target": planner_target,
                    "resolved_element": resolved_id,
                    "exec_success": result.get("success"),
                    "cart": cart,
                }
            )

        result = await run_ws_task(
            page,
            task,
            max_steps=20,
            step_timeout_s=180,
            after_execute=after_execute,
        )
        report["terminal"] = result.terminal
        await browser.close()

    print(
        f"requested={task!r} planner_target={planner_target!r} "
        f"resolved={resolved_id!r} clicked={clicked_product!r} terminal={result.terminal}"
    )
    assert result.terminal in {"RUN_COMPLETE", "RUN_WAITING_FOR_USER"}, report
    assert clicked_product == expected_id, report
