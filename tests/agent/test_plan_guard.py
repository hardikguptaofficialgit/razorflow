"""Tests for action policy validation (goal scope, no replanning shortcuts)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.action_policy import validate_planner_chunk  # noqa: E402
from core.protocol import (  # noqa: E402
    ClickElementStep,
    PageContext,
    PageElementSummary,
    PageProductSummary,
    PlannerChunkOutput,
    TypeInElementStep,
)
from core.run_manager import RunSession  # noqa: E402
from core.search_query import extract_search_query  # noqa: E402
from core.shopping_intent import parse_shopping_intent  # noqa: E402
from core.task_intent import parse_task_intent  # noqa: E402


def test_parse_budget_under_6k() -> None:
    intent = parse_shopping_intent("best wireless earbud under 6k")
    assert intent.budget_max == 6000


def test_search_query_strips_budget_suffix() -> None:
    query = extract_search_query("best wireless earbud under 6k")
    assert query == "earbuds"
    assert "6k" not in query.lower()


def test_policy_replans_instead_of_synthesizing_cart_navigation() -> None:
    session = RunSession(
        run_id="guard-2",
        task="add best wireless earbud under 6k to cart",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3001/search?q=wireless+earbud",
            elements=[
                PageElementSummary(
                    index=1,
                    role="link",
                    tag="a",
                    text="Cart",
                    placeholder="",
                    aria_label="Cart, 0 items",
                ),
            ],
            products=[
                PageProductSummary(
                    title="Samsung Galaxy Buds FE",
                    price_text="₹4,999",
                    add_to_cart_element_index=5,
                ),
            ],
        ),
    )
    chunk = PlannerChunkOutput(
        steps=[
            ClickElementStep(
                action="click_element",
                role="link",
                element_index=1,
                match_text="Cart",
            ),
        ],
        terminal="continue",
    )

    guarded = validate_planner_chunk(session, chunk, parse_task_intent(session.task))
    assert not guarded.steps
    assert guarded.terminal == "continue"
    assert "empty" in session.planner_nudge.lower()


def test_policy_allows_type_on_home() -> None:
    session = RunSession(
        run_id="guard-3",
        task="best wireless earbud under 6k",
        latest_page_context=PageContext(
            title="Home",
            url="http://localhost:3001/",
            elements=[],
            products=[],
        ),
    )
    chunk = PlannerChunkOutput(
        steps=[
            TypeInElementStep(
                action="type_in_element",
                role="search",
                text="wireless earbud",
                element_index=2,
            ),
        ],
        terminal="continue",
    )

    guarded = validate_planner_chunk(session, chunk)
    assert guarded.steps[0].action == "type_in_element"
