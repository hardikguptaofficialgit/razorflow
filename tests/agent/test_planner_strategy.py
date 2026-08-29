"""Planner strategy tests for in-app DOM agent."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.planner import plan_next_chunk  # noqa: E402
from core.protocol import (  # noqa: E402
    ClickElementStep,
    PageContext,
    PageElementSummary,
    PageProductSummary,
    PlannerChunkOutput,
)
from core.run_manager import RunSession  # noqa: E402

pytestmark = pytest.mark.legacy


@pytest.mark.asyncio
async def test_dom_agent_uses_llm_when_goal_not_met() -> None:
    session = RunSession(
        run_id="llm-1",
        task="Buy the cheapest shampoo under 500",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3000/search?q=shampoo",
            elements=[
                PageElementSummary(
                    index=1,
                    role="button",
                    tag="button",
                    text="Add to cart",
                    placeholder="",
                    aria_label="",
                ),
            ],
            products=[
                PageProductSummary(
                    title="Sunsilk Thick & Long Shampoo 180ml",
                    price_text="₹289",
                    add_to_cart_element_index=1,
                ),
            ],
        ),
    )

    llm_chunk = PlannerChunkOutput(
        steps=[
            ClickElementStep(
                action="click_element",
                role="button",
                element_index=1,
                match_text="add to cart",
            ),
        ],
        terminal="continue",
    )

    with patch(
        "core.agent_loop.plan_with_llm",
        new_callable=AsyncMock,
        return_value=llm_chunk,
    ) as llm_plan:
        chunk = await plan_next_chunk(session)

    llm_plan.assert_not_called()
    assert chunk.steps[0].action == "click_element"
