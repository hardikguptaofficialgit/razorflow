"""DOM failure recovery through real WebSocket + browser execution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.agent.ws_harness import run_ws_task

FIXTURE = ROOT / "tests" / "agent" / "fixtures" / "dom_recovery.html"

SCENARIOS = [
    "disappear",
    "move",
    "disabled",
    "duplicate",
    "modal",
    "cookie",
    "delayed",
    "mutate",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS)
async def test_dom_recovery_does_not_false_complete(scenario: str) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(FIXTURE.as_uri(), wait_until="domcontentloaded")
        await page.evaluate(f"() => window.__RF_SET_SCENARIO__({scenario!r})")

        turn = {"n": 0}

        async def before_execute(_step: dict, step_num: int) -> None:
            turn["n"] = step_num
            if step_num == 1:
                await page.evaluate(f"() => window.__RF_SET_SCENARIO__({scenario!r})")

        result = await run_ws_task(
            page,
            "click the Submit order button",
            max_steps=12,
            step_timeout_s=90,
            before_execute=before_execute,
        )

        assert result.terminal != "RUN_COMPLETE", (
            f"scenario={scenario} falsely completed: {result.message}"
        )
        assert result.terminal in {
            "RUN_ERROR",
            "RUN_WAITING_FOR_USER",
            "RECV_TIMEOUT",
            "",
        } or result.steps >= 1
        await browser.close()
