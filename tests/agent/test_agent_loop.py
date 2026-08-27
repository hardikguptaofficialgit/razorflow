"""Tests for centralized agent loop."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.agent_loop import plan_next_action  # noqa: E402
from core.protocol import PageContext  # noqa: E402
from core.run_manager import RunSession  # noqa: E402


@pytest.mark.asyncio
async def test_search_results_without_progress_still_plans() -> None:
    session = RunSession(
        run_id="loop-1",
        task="search for wireless earbuds",
        latest_page_context=PageContext(
            title="Home",
            url="http://localhost:3001/",
            elements=[],
            products=[],
        ),
    )

    with patch("core.agent_loop.plan_with_llm", new_callable=AsyncMock) as llm:
        chunk = await plan_next_action(session)

    llm.assert_not_called()
    assert chunk.steps[0].action == "navigate_url"
    assert "earbuds" in chunk.steps[0].url.lower()


@pytest.mark.asyncio
async def test_nonsense_task_needs_clarification() -> None:
    session = RunSession(
        run_id="loop-2",
        task="wdwd",
        latest_page_context=PageContext(
            title="Home",
            url="http://localhost:3001/",
            elements=[],
            products=[],
        ),
    )
    with patch("core.agent_loop.plan_with_llm", new_callable=AsyncMock) as llm:
        chunk = await plan_next_action(session)

    llm.assert_not_called()
    assert chunk.terminal == "needs_clarification"
