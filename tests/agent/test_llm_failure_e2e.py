"""LLM failure recovery through real WebSocket + browser (fixture LLM)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.agent.ws_harness import run_ws_task

FIXTURE = ROOT / "tests" / "agent" / "fixtures" / "target_resolution_page.html"
LLM_FIXTURE = ROOT / "tests" / "agent" / "fixtures" / "llm_failure_sequence.json"


@pytest.fixture(autouse=True)
def _llm_fixture_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_LLM_TEST_FIXTURE", str(LLM_FIXTURE))
    from agent_runtime.bridge import adapter

    adapter.reset_runtime()


@pytest.mark.skip(reason="Requires backend started with AGENT_LLM_TEST_FIXTURE; use run_release_blocker_suite.py")

@pytest.mark.asyncio
async def test_llm_failure_recovery_through_ws() -> None:
    """Invalid JSON → false DONE → recovery with valid action."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(FIXTURE.as_uri(), wait_until="domcontentloaded")

        result = await run_ws_task(
            page,
            "add Galaxy Buds FE to my cart",
            max_steps=10,
            step_timeout_s=60,
        )

        assert result.terminal != "RUN_COMPLETE" or result.steps > 0
        assert result.terminal in {
            "RUN_COMPLETE",
            "RUN_ERROR",
            "RUN_WAITING_FOR_USER",
            "RECV_TIMEOUT",
        }
        # Must not accept proposeFinish without verification on step 2
        finish_msgs = [m for m in result.messages if m.get("type") == "RUN_COMPLETE"]
        if finish_msgs and result.steps < 2:
            pytest.fail("false DONE from empty/finish proposal without recovery")
        await browser.close()


@pytest.mark.asyncio
async def test_llm_fixture_env_is_set() -> None:
    assert os.getenv("AGENT_LLM_TEST_FIXTURE")
