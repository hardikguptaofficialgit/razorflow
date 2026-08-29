"""Tests for goal guard and intent parsing anti-escalation."""

from __future__ import annotations

from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.observation.browser_state import (
    BrowserPage,
    ObservedCartLine,
    ObservedProduct,
)
from agent_runtime.policy.goal_guard import action_advances_goal, goal_quota_met
from agent_runtime.policy.search_state import (
    entity_in_search,
    entity_visible_on_page,
    has_relevant_search_results,
)
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parse import parse_task_spec


def _state(task: str) -> RunState:
    from agent_runtime.task.parser import parse_task_with_spec

    parsed, spec = parse_task_with_spec(task)
    return RunState(
        run_id="g1",
        task=task,
        parsed_task=parsed,
        task_spec=spec,
        current_phase=spec.target_phase,
    )


def test_find_cheapest_disallows_add() -> None:
    spec = parse_task_spec("Find the cheapest smartwatch on this site")
    assert spec.intent == "search"
    assert spec.allows_add_to_cart is False
    state = _state("Find the cheapest smartwatch on this site")
    add = AgentAction(
        type="click",
        target=ElementTarget(role="button", description="Add to cart for Watch"),
        reason="add",
        expectedOutcome="cart",
    )
    ok, reason = action_advances_goal(state, add)
    assert not ok
    assert "add" in reason.lower()


def test_compare_add_best_quantity_one() -> None:
    spec = parse_task_spec(
        "Find wireless earbuds, compare multiple results, then add the best one to my cart"
    )
    assert spec.allows_add_to_cart is True
    assert spec.quantity == 1
    assert spec.goal_phases == ("search_results", "cart_updated")
    assert spec.target_phase == "search_results"
    assert spec.entities == ("wireless earbuds",)


def test_scroll_blocked_before_search() -> None:
    from agent_runtime.observation.browser_state import BrowserPage

    state = _state("Find the cheapest smartwatch on this site")
    page = BrowserPage(
        title="Demo",
        url="http://localhost:3001/demo",
        path="/demo",
        search_query="",
    )
    state.memory.current_page = page
    scroll = AgentAction(type="scroll", reason="scroll", expectedOutcome="more")
    ok, reason = action_advances_goal(state, scroll)
    assert not ok
    assert "search" in reason.lower()


def test_quota_blocks_extra_add() -> None:
    state = _state("add Galaxy Buds FE to my cart")
    state.memory.items_added = 1
    state.memory.current_page = BrowserPage(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        path="/demo/cart",
        search_query="",
        cart_lines=[ObservedCartLine(title="Galaxy Buds FE", quantity=1)],
    )
    assert goal_quota_met(state)
    add = AgentAction(
        type="click",
        target=ElementTarget(role="button", description="Add to cart"),
        reason="add again",
        expectedOutcome="cart",
    )
    ok, _ = action_advances_goal(state, add)
    assert not ok


def test_entity_matches_partial_search_url() -> None:
    page = BrowserPage(
        title="Search",
        url="http://localhost:3001/demo/search?q=earbuds",
        path="/demo/search",
        search_query="earbuds",
        products=[ObservedProduct(product_id="1", title="Galaxy Buds FE", price_text="4999", rating_text="4.5")],
    )
    assert entity_in_search(page, "wireless earbuds")


def test_entity_matches_product_words_in_any_order() -> None:
    page = BrowserPage(
        title="Demo",
        url="http://localhost:3001/demo",
        path="/demo",
        search_query="",
        products=[
            ObservedProduct(
                product_id="watch-1",
                title="NovaTrack Pro Smartwatch",
                price_text="3499",
                rating_text="4.5",
            )
        ],
    )
    assert entity_visible_on_page(page, "NovaTrack watch")


def test_find_goal_ready_with_product_titles() -> None:
    state = _state("Find the cheapest smartwatch on this site")
    state.milestones.add("verified_search")
    page = BrowserPage(
        title="Search",
        url="http://localhost:3001/demo/search?q=smartwatch",
        path="/demo/search",
        search_query="smartwatch",
        products=[
            ObservedProduct(
                product_id="sw1",
                title="Fire-Boltt Smartwatch",
                price_text="1999",
                rating_text="4.2",
            )
        ],
    )
    assert has_relevant_search_results(page, state)
    assert entity_in_search(page, "smartwatch")


def test_compare_add_entity_parsing() -> None:
    from agent_runtime.task.entities import extract_entity_phrases

    phrases = extract_entity_phrases(
        "Find wireless earbuds, compare multiple results, then add the best one to my cart"
    )
    assert phrases == ("wireless earbuds",)


def test_checkout_prompt_allows_checkout_in_checkout_phase() -> None:
    spec = parse_task_spec("add good snacks under ₹200 and checkout")
    block = spec.to_prompt_block(current_phase="checkout")
    assert "checkout_allowed: true" in block
    assert "forbidden_now: checkout" not in block
