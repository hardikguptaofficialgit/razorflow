"""Autonomous compare-and-buy flow (parse, rank, guard)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_runtime.domain.shopping.goal_guard import action_advances_goal
from agent_runtime.domain.shopping.product_compare import (
    apply_comparison_to_state,
    criteria_from_state,
    rank_products,
)
from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.observation.browser_state import BrowserPage, ObservedProduct
from agent_runtime.state.run_state import RunState
from agent_runtime.task.entities import extract_entity_phrase
from agent_runtime.task.parse import parse_task_spec


def _chocolate_page() -> BrowserPage:
    return BrowserPage(
        title="Search",
        url="http://localhost:3001/search?q=chocolate",
        path="/search",
        search_query="chocolate",
        products=[
            ObservedProduct(
                product_id="p1",
                title="Premium Dark Chocolate 70%",
                price_text="₹499",
                rating_text="4.8 stars",
                add_element_id="e10",
            ),
            ObservedProduct(
                product_id="p2",
                title="Milk Chocolate Bar",
                price_text="₹149",
                rating_text="4.2 stars",
                add_element_id="e11",
            ),
            ObservedProduct(
                product_id="p3",
                title="Artisan Truffle Box",
                price_text="₹899",
                rating_text="4.9 stars",
                add_element_id="e12",
            ),
        ],
    )


def test_buy_me_best_chocolate_parses_autonomous_purchase() -> None:
    task = "Buy me the best chocolate at the best price"
    assert extract_entity_phrase(task) == "chocolate"

    spec = parse_task_spec(task)
    assert spec.intent == "purchase"
    assert spec.allows_add_to_cart is True
    assert spec.requires_checkout is True
    assert spec.prefer_best is True
    assert spec.prefer_cheapest is True
    assert spec.entities == ("chocolate",)
    assert spec.target_phase == "search_results"
    assert spec.goal_phases == ("search_results", "cart_updated", "checkout_reached")


def test_rank_products_picks_cheapest_for_best_price() -> None:
    criteria = criteria_from_state(
        _state_for_task("Buy me the best chocolate at the best price")
    )
    winner, _, reason = rank_products(_chocolate_page(), criteria)
    assert winner is not None
    assert winner.title == "Milk Chocolate Bar"
    assert "lowest price" in reason


def test_apply_comparison_sets_milestone_and_target() -> None:
    state = _state_for_task("Buy me the best chocolate at the best price")
    page = _chocolate_page()
    state.milestones.add("verified_search")

    assert apply_comparison_to_state(state, page) is True
    assert "verified_comparison" in state.milestones
    assert state.metrics["selected_product_title"] == "Milk Chocolate Bar"
    assert state.metrics["selected_product_add_id"] == "e11"
    assert state.memory.current_target == "Milk Chocolate Bar"


def test_goal_guard_blocks_add_before_comparison() -> None:
    state = _state_for_task("Buy me the best chocolate at the best price")
    state.milestones.add("verified_search")
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e11",
            role="button",
            description="Add to cart for Milk Chocolate Bar",
        ),
        reason="add",
        expectedOutcome="cart grows",
    )
    ok, reason = action_advances_goal(state, action)
    assert not ok
    assert "compare" in reason.lower()


def test_goal_guard_allows_add_after_comparison() -> None:
    state = _state_for_task("Buy me the best chocolate at the best price")
    state.milestones.update({"verified_search", "verified_comparison"})
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e11",
            role="button",
            description="Add to cart for Milk Chocolate Bar",
        ),
        reason="add",
        expectedOutcome="cart grows",
    )
    ok, _ = action_advances_goal(state, action)
    assert ok


def _state_for_task(task: str) -> RunState:
    from agent_runtime.domain.shopping.parse import spec_to_parsed

    spec = parse_task_spec(task)
    parsed = spec_to_parsed(spec)
    state = RunState(run_id="buy-test", task=task, parsed_task=parsed, task_spec=spec)
    state.current_phase = spec.target_phase
    state.memory.current_page = _chocolate_page()
    return state
