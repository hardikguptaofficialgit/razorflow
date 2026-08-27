"""Tests for task goal parsing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.plan_guard_store import apply_store_dom_guard  # noqa: E402
from core.protocol import (  # noqa: E402
    ActionHistoryEntry,
    ClickElementStep,
    PageContext,
    PageElementSummary,
    PageProductSummary,
    PlannerChunkOutput,
)
from core.run_manager import RunSession  # noqa: E402
from core.task_intent import (  # noqa: E402
    goal_allows_checkout,
    is_goal_satisfied,
    parse_task_intent,
)


def test_add_snacks_goal_is_add_to_cart_not_checkout() -> None:
    intent = parse_task_intent("Add me some good snacks under ₹200, please.")
    assert intent.goal == "add_to_cart"
    assert intent.add_target_count == 2
    assert not goal_allows_checkout(intent.goal)


def test_find_snacks_goal_is_search_only() -> None:
    intent = parse_task_intent("Find good snacks under ₹200")
    assert intent.goal == "search"


def test_add_and_checkout_goal() -> None:
    intent = parse_task_intent("Add good snacks under ₹200 and checkout")
    assert intent.goal == "checkout"
    assert intent.add_target_count == 1
    assert len(intent.product_queries) <= 1


def test_buy_snacks_goal_is_purchase() -> None:
    intent = parse_task_intent("Buy good snacks under ₹200")
    assert intent.goal == "purchase"


def test_buy_me_multi_item_list_is_add_to_cart() -> None:
    intent = parse_task_intent("buy me amul butter , chips , cooker")
    assert intent.goal == "add_to_cart"
    assert intent.add_target_count == 3
    assert len(intent.product_queries) == 3
    assert not intent.requires_payment
    assert not intent.requires_checkout


def test_multi_item_watches_and_beauty_bars() -> None:
    intent = parse_task_intent("add watches , beauty bars in my cart")
    assert intent.goal == "add_to_cart"
    assert intent.add_target_count == 2
    assert len(intent.product_queries) == 2
    assert "smartwatch" in intent.product_queries[0] or "watch" in intent.product_queries[0]
    assert "beauty" in intent.product_queries[1]


def test_complex_cart_list_parses_without_all() -> None:
    intent = parse_task_intent(
        "add watches , bars , chcolates , buds and all in my cart and "
        "let me know before placing checkout"
    )
    assert intent.goal == "add_to_cart"
    assert not intent.requires_checkout
    assert "all" not in intent.product_queries
    assert len(intent.product_queries) >= 4


def test_guard_blocks_category_nav_clicks() -> None:
    session = RunSession(
        run_id="goal-cat",
        task="add watches in my cart",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3001/search?category=snacks",
            elements=[
                PageElementSummary(
                    index=2,
                    role="link",
                    tag="a",
                    text="Snacks",
                    placeholder="",
                    aria_label="",
                ),
            ],
            products=[],
        ),
    )
    guarded = apply_store_dom_guard(
        session,
        PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role="link",
                    element_index=2,
                    match_text="Snacks",
                ),
            ],
            terminal="continue",
        ),
    )
    assert guarded.steps
    assert guarded.steps[0].action == "navigate_url"
    assert "smartwatch" in guarded.steps[0].url.lower()


def test_guard_blocks_checkout_for_add_only_task() -> None:
    session = RunSession(
        run_id="goal-1",
        task="Add me some good snacks under ₹200, please.",
        latest_page_context=PageContext(
            title="Cart",
            url="http://localhost:3001/cart",
            elements=[
                PageElementSummary(
                    index=1,
                    role="button",
                    tag="button",
                    text="Proceed to checkout",
                    placeholder="",
                    aria_label="",
                ),
            ],
            products=[],
        ),
    )
    chunk = PlannerChunkOutput(
        steps=[
            ClickElementStep(
                action="click_element",
                role="button",
                element_index=1,
                match_text="Proceed to checkout",
            ),
        ],
        terminal="continue",
    )

    guarded = apply_store_dom_guard(session, chunk)
    assert guarded.terminal == "complete"
    assert guarded.steps == []


def test_guard_searches_second_item_after_first_add() -> None:
    session = RunSession(
        run_id="goal-3",
        task="add watches , beauty bars in my cart",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3001/search?q=watches",
            elements=[],
            products=[
                PageProductSummary(
                    title="Noise ColorFit Pro 5 Smartwatch",
                    price_text="₹2499",
                    add_to_cart_element_index=3,
                ),
            ],
        ),
    )
    session.history.append(
        ActionHistoryEntry(
            step=ClickElementStep(
                action="click_element",
                role="button",
                element_index=3,
                match_text="Add to cart",
            ),
            success=True,
            error=None,
            page_fingerprint="fp",
        )
    )

    guarded = apply_store_dom_guard(
        session,
        PlannerChunkOutput(steps=[], terminal="continue"),
    )
    assert guarded.steps
    assert guarded.steps[0].action == "navigate_url"
    assert "beauty" in guarded.steps[0].url.lower()


def test_guard_completes_after_add_goal_met() -> None:
    session = RunSession(
        run_id="goal-2",
        task="Add me good snacks under ₹200",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3001/search?q=snacks",
            elements=[],
            products=[
                PageProductSummary(
                    title="Lay's Classic Salted Chips 52g",
                    price_text="₹20",
                    add_to_cart_element_index=3,
                ),
            ],
        ),
    )
    session.history.append(
        ActionHistoryEntry(
            step=ClickElementStep(
                action="click_element",
                role="button",
                element_index=3,
                match_text="Add to cart",
            ),
            success=True,
            error=None,
            page_fingerprint="fp",
        )
    )

    intent = parse_task_intent(session.task)
    assert is_goal_satisfied(session, intent, session.latest_page_context)

    guarded = apply_store_dom_guard(
        session,
        PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role="link",
                    element_index=1,
                    match_text="Cart",
                ),
            ],
            terminal="continue",
        ),
    )
    assert guarded.terminal == "complete"
