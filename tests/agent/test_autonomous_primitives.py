"""Unit tests for autonomous agent primitives."""

from __future__ import annotations

from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.executor.translate import translate_action
from agent_runtime.observation.browser_state import BrowserPage, ObservedElement, ObservedProduct
from agent_runtime.recovery.loop_detector import loop_nudge, record_action_hash, record_observation
from agent_runtime.state.run_state import RunState
from agent_runtime.target.resolve import refresh_action_target
from agent_runtime.task.parser import parse_task_with_spec
from agent_runtime.verifier.action_result import apply_verified_progress
from agent_runtime.verifier.cart import cart_matches_hints, cart_satisfies_add_goal


def _run_state() -> RunState:
    parsed, spec = parse_task_with_spec("add butter and chips to my cart")
    return RunState(run_id="t1", task="add butter and chips", parsed_task=parsed, task_spec=spec)


def _page_with_products() -> BrowserPage:
    return BrowserPage(
        title="Shop",
        url="http://example.test/",
        path="/",
        search_query="",
        elements=[
            ObservedElement(
                element_id="e1",
                index=1,
                role="button",
                tag="button",
                text="Add to cart",
                placeholder="",
                aria_label="",
                clickable=True,
            ),
            ObservedElement(
                element_id="e2",
                index=2,
                role="button",
                tag="button",
                text="Add to cart for Galaxy Buds FE",
                placeholder="",
                aria_label="",
                clickable=True,
            ),
        ],
        products=[
            ObservedProduct(
                product_id="p1",
                title="Galaxy Buds FE",
                price_text="₹4999",
                rating_text="",
                add_element_id="e2",
            )
        ],
    )


def test_translate_scroll_wait_go_back() -> None:
    scroll = AgentAction(
        type="scroll",
        parameters={"direction": "down", "amount_px": 800},
        reason="reveal products",
        expectedOutcome="more elements visible",
    )
    steps = translate_action(scroll)
    assert len(steps) == 1
    assert steps[0].action == "scroll_page"

    wait = AgentAction(
        type="wait",
        parameters={"duration_ms": 300},
        reason="wait for load",
        expectedOutcome="page settles",
    )
    assert translate_action(wait)[0].action == "wait"

    back = AgentAction(
        type="go_back",
        reason="wrong page",
        expectedOutcome="previous page",
    )
    assert translate_action(back)[0].action == "go_back"


def test_refresh_action_target_by_product_title() -> None:
    page = _page_with_products()
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e99",
            role="button",
            description="Add to cart for Galaxy Buds FE",
        ),
        reason="add buds",
        expectedOutcome="cart grows",
    )
    resolved = refresh_action_target(action, page)
    assert resolved.target is not None
    assert resolved.target.element_id == "e2"


def test_loop_detector_nudge_on_repetition() -> None:
    state = _run_state()
    page = _page_with_products()
    record_observation(state, page)
    action = AgentAction(
        type="click",
        target=ElementTarget(element_id="e1", role="button"),
        reason="x",
        expectedOutcome="y",
    )
    for _ in range(6):
        record_action_hash(state, action)
    assert loop_nudge(state) is not None


def test_cart_matches_multiple_hints() -> None:
    from agent_runtime.observation.browser_state import ObservedCartLine

    page = BrowserPage(
        title="Cart",
        url="http://example.test/cart",
        path="/cart",
        search_query="",
        cart_lines=[
            ObservedCartLine(title="Amul Butter 100g", quantity=1),
            ObservedCartLine(title="Lay's Chips", quantity=1),
        ],
    )
    assert cart_matches_hints(page, ("butter", "chips"))
    state = _run_state()
    state.milestones.add("verified_add_to_cart")
    assert cart_satisfies_add_goal(state, page)


def test_cart_goal_requires_requested_identity_not_memory_only() -> None:
    from agent_runtime.observation.browser_state import ObservedCartLine

    state = _run_state()
    state.memory.items_added = 2
    wrong_page = BrowserPage(
        title="Cart",
        url="http://example.test/cart",
        path="/cart",
        search_query="",
        cart_lines=[ObservedCartLine(title="Wireless Earbuds", quantity=2)],
    )
    assert not cart_satisfies_add_goal(state, wrong_page)


def test_unrelated_add_does_not_advance_requested_cart_goal() -> None:
    from agent_runtime.observation.browser_state import ObservedCartLine

    state = _run_state()
    state.memory.remaining_items = ["butter", "chips"]
    before = _page_with_products()
    after = _page_with_products()
    after.cart_lines = [ObservedCartLine(title="Galaxy Buds FE", quantity=1)]
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e2", role="button", description="Add to cart"
        ),
        reason="add an item",
        expectedOutcome="cart grows",
    )

    apply_verified_progress(state, action, after, ok=True, before=before)

    assert state.memory.items_added == 0
    assert state.memory.remaining_items == ["butter", "chips"]
    assert "verified_add_to_cart" not in state.milestones
