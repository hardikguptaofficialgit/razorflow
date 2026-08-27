"""Tests for action policy validation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.action_policy import validate_planner_chunk  # noqa: E402
from core.protocol import (  # noqa: E402
    ActionHistoryEntry,
    ClickElementStep,
    PageContext,
    PageProductSummary,
    PlannerChunkOutput,
)
from core.run_manager import RunSession  # noqa: E402
from core.task_intent import parse_task_intent  # noqa: E402


def test_fallback_add_when_llm_returns_empty() -> None:
    session = RunSession(
        run_id="policy-fallback",
        task="add 2 snacks under ₹200",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3001/search?q=snacks",
            elements=[],
            products=[
                PageProductSummary(
                    title="Lay's Chips",
                    price_text="₹20",
                    add_to_cart_element_index=5,
                ),
            ],
        ),
    )
    session.history.append(
        ActionHistoryEntry(
            step=ClickElementStep(
                action="click_element",
                role="button",
                element_index=5,
                match_text="Add to cart",
            ),
            success=True,
            verified=True,
        ),
    )
    intent = parse_task_intent(session.task)
    chunk = PlannerChunkOutput(steps=[], terminal="complete")

    guarded = validate_planner_chunk(session, chunk, intent)

    assert guarded.steps
    assert guarded.steps[0].action == "click_element"


def test_allows_repeat_add_to_cart_until_target_met() -> None:
    session = RunSession(
        run_id="policy-add-2",
        task="add 2 snacks under ₹200",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3001/search?q=snacks",
            elements=[],
            products=[
                PageProductSummary(
                    title="Lay's Chips",
                    price_text="₹20",
                    add_to_cart_element_index=5,
                ),
            ],
        ),
    )
    add_step = ClickElementStep(
        action="click_element",
        role="button",
        element_index=5,
        match_text="Add to cart",
    )
    session.history.append(ActionHistoryEntry(step=add_step, success=True, verified=True))
    intent = parse_task_intent(session.task)
    chunk = PlannerChunkOutput(steps=[add_step], terminal="continue")

    guarded = validate_planner_chunk(session, chunk, intent)

    assert guarded.steps
    assert guarded.steps[0].action == "click_element"
