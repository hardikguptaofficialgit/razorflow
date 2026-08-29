"""Regression tests for multi-item cart tasks and duplicate add prevention."""

from __future__ import annotations

from agent_runtime.domain.shopping.memory_sync import sync_memory_from_observation
from agent_runtime.domain.shopping.search_state import search_entity
from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.memory.sync import sync_memory_from_observation as sync_memory
from agent_runtime.observation.browser_state import (
    BrowserPage,
    ObservedCartLine,
    ObservedElement,
    ObservedProduct,
)
from agent_runtime.policy.goal_guard import action_advances_goal, goal_quota_met
from agent_runtime.runtime import AgentRuntime
from agent_runtime.state.run_state import RunState
from agent_runtime.task.entities import extract_entity_phrases
from agent_runtime.task.parser import parse_task_with_spec
from agent_runtime.verifier.action_result import apply_verified_progress, verify_action_result
from agent_runtime.verifier.cart import cart_satisfies_add_goal
from agent_runtime.verifier.goal import approve_completion
from core.protocol import PageContext, PageElementSummary, PageProductSummary


def _multi_item_state() -> RunState:
    task = "add a watch, buds into my cart"
    parsed, spec = parse_task_with_spec(task)
    state = RunState(
        run_id="multi-1",
        task=task,
        parsed_task=parsed,
        task_spec=spec,
        current_phase=spec.target_phase,
    )
    state.bind_skill(__import__(
        "agent_runtime.domain.registry", fromlist=["resolve_domain_skill"]
    ).resolve_domain_skill(task))
    state.memory.remaining_items = list(spec.remaining_items)
    state.memory.items_target = parsed.item_count
    return state


def _search_page_with_watch() -> BrowserPage:
    return BrowserPage(
        title="Search",
        url="http://localhost:3001/demo/search?q=watch",
        path="/demo/search",
        search_query="watch",
        elements=[
            ObservedElement(
                element_id="e1",
                index=1,
                role="button",
                tag="button",
                text="Add to cart",
                placeholder="",
                aria_label="Add NoiseFit Halo Smartwatch",
                clickable=True,
            ),
            ObservedElement(
                element_id="e2",
                index=2,
                role="button",
                tag="button",
                text="Add to cart",
                placeholder="",
                aria_label="Add Galaxy Buds FE",
                clickable=True,
            ),
        ],
        products=[
            ObservedProduct(
                product_id="p1",
                title="NoiseFit Halo Smartwatch",
                price_text="₹2499",
                rating_text="4.2",
                add_element_id="e1",
            ),
            ObservedProduct(
                product_id="p2",
                title="Galaxy Buds FE",
                price_text="₹4999",
                rating_text="4.5",
                add_element_id="e2",
            ),
        ],
    )


def _cart_page_with_watch(qty: int = 1) -> BrowserPage:
    return BrowserPage(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        path="/demo/cart",
        search_query="",
        cart_lines=[ObservedCartLine(title="NoiseFit Halo Smartwatch", quantity=qty)],
        elements=[],
        products=[],
        signals=["cart_page"],
    )


def test_entity_extraction_watch_and_buds() -> None:
    phrases = extract_entity_phrases("add a watch, buds into my cart")
    assert "watch" in phrases
    assert any("bud" in p for p in phrases)
    assert not any("into" in p for p in phrases)


def test_search_entity_follows_remaining_items() -> None:
    state = _multi_item_state()
    assert search_entity(state) == "watch"
    state.memory.remaining_items = ["buds"]
    assert search_entity(state) == "buds"


def test_sync_memory_updates_remaining_work_after_first_add() -> None:
    state = _multi_item_state()
    page = _cart_page_with_watch()
    state.memory.remaining_items = ["buds"]
    state.memory.verified_items = ["NoiseFit Halo Smartwatch"]
    state.memory.items_added = 1
    sync_memory_from_observation(state, page)
    assert state.memory.current_target == "buds"
    assert any("buds" in item.lower() for item in state.memory.remaining_work)


def test_duplicate_watch_add_not_verified() -> None:
    state = _multi_item_state()
    before = _search_page_with_watch()
    after = _cart_page_with_watch(qty=2)
    state.memory.remaining_items = ["buds"]
    state.memory.verified_items = ["NoiseFit Halo Smartwatch"]
    state.memory.items_added = 1
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e1",
            role="button",
            description="Add NoiseFit Halo Smartwatch to cart",
        ),
        reason="add watch again",
        expectedOutcome="cart grows",
    )
    ok = verify_action_result(
        state, action, success=True, verified=None, before=before, after=after
    )
    assert not ok
    progress = apply_verified_progress(state, action, after, ok=ok, before=before)
    assert not progress
    assert state.memory.items_added == 1
    assert state.memory.remaining_items == ["buds"]


def test_goal_guard_blocks_repeat_verified_product() -> None:
    state = _multi_item_state()
    state.memory.remaining_items = ["buds"]
    state.memory.verified_items = ["NoiseFit Halo Smartwatch"]
    state.memory.current_page = _search_page_with_watch()
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e1",
            role="button",
            description="Add NoiseFit Halo Smartwatch",
        ),
        reason="add watch",
        expectedOutcome="cart",
    )
    ok, reason = action_advances_goal(state, action)
    assert not ok
    assert "already in cart" in reason.lower()


def test_second_item_add_advances_remaining() -> None:
    state = _multi_item_state()
    before = _search_page_with_watch()
    after = BrowserPage(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        path="/demo/cart",
        search_query="",
        cart_lines=[
            ObservedCartLine(title="NoiseFit Halo Smartwatch", quantity=1),
            ObservedCartLine(title="Galaxy Buds FE", quantity=1),
        ],
        elements=[],
        products=[],
        signals=["cart_page"],
    )
    state.memory.remaining_items = ["buds"]
    state.memory.verified_items = ["NoiseFit Halo Smartwatch"]
    state.memory.items_added = 1
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e2",
            role="button",
            description="Add Galaxy Buds FE to cart",
        ),
        reason="add buds",
        expectedOutcome="cart grows",
    )
    ok = verify_action_result(
        state, action, success=True, verified=None, before=before, after=after
    )
    assert ok
    progress = apply_verified_progress(state, action, after, ok=ok, before=before)
    assert progress
    assert state.memory.items_added == 2
    assert state.memory.remaining_items == []
    assert "Galaxy Buds FE" in state.memory.verified_items


def test_goal_complete_when_distinct_items_in_cart() -> None:
    state = _multi_item_state()
    page = BrowserPage(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        path="/demo/cart",
        search_query="",
        cart_lines=[
            ObservedCartLine(title="NoiseFit Halo Smartwatch", quantity=1),
            ObservedCartLine(title="Galaxy Buds FE", quantity=1),
        ],
        elements=[],
        products=[],
        signals=["cart_page"],
    )
    state.memory.verified_items = [
        "NoiseFit Halo Smartwatch",
        "Galaxy Buds FE",
    ]
    state.memory.items_added = 2
    state.memory.remaining_items = []
    sync_memory_from_observation(state, page)
    assert goal_quota_met(state)
    assert cart_satisfies_add_goal(state, page)
    assert approve_completion(state, page, source="test")


class _NoopLLM:
    def plan(self, *_args, **_kwargs):
        raise AssertionError("LLM should not be called when goal is complete")

    def health_check(self) -> bool:
        return True


def test_runtime_stops_after_goal_verified() -> None:
    runtime = AgentRuntime(llm=_NoopLLM())
    page = PageContext(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        elements=[],
        products=[],
        cart_lines=[
            {"title": "NoiseFit Halo Smartwatch", "quantity": 1},
            {"title": "Galaxy Buds FE", "quantity": 1},
        ],
    )
    state = runtime.start_run("multi-1", "add a watch, buds into my cart", page)
    state.memory.verified_items = [
        "NoiseFit Halo Smartwatch",
        "Galaxy Buds FE",
    ]
    state.memory.items_added = 2
    state.memory.remaining_items = []
    sync_memory(state, runtime.observe(state, page))
    result = runtime.dispatch_next(state, page)
    assert result.kind == "complete"
