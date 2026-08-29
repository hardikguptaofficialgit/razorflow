"""Regression tests for autonomy hardening (labels, qty, stale targets, recovery)."""

from __future__ import annotations

from agent_runtime.domain.shopping.action_gate import (
    _is_add_to_cart_action,
    _is_checkout_action,
    _is_product_details_action,
    classify_action,
    filter_forbidden_actions,
)
from agent_runtime.domain.shopping.checkout_controls import is_checkout_control_element
from agent_runtime.domain.shopping.goal_guard import action_advances_goal
from agent_runtime.domain.shopping.helpers import goal_item_phrase, multi_distinct_item_goal
from agent_runtime.domain.shopping.resolve import refresh_shopping_action_target
from agent_runtime.domain.shopping.target_resolve import refresh_action_target
from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.observation.browser_state import (
    BrowserPage,
    ObservedCartLine,
    ObservedElement,
    ObservedProduct,
)
from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.planner.recovery import empty_plan_nudge
from agent_runtime.state.run_state import RunState
from agent_runtime.target.resolve import refresh_action_target as refresh_generic_target
from agent_runtime.task.parser import parse_task_with_spec
from agent_runtime.verifier.action_result import apply_verified_progress, verify_action_result


def _click(label: str, element_id: str = "e1", *, role: str = "button") -> AgentAction:
    return AgentAction(
        type="click",
        target=ElementTarget(element_id=element_id, role=role, description=label),
        reason=label,
        expectedOutcome="advance",
    )


def _search_page() -> BrowserPage:
    return BrowserPage(
        title="Search",
        url="http://example.test/search?q=snacks",
        path="/search",
        search_query="snacks",
        elements=[
            ObservedElement(
                element_id="e1",
                index=1,
                role="button",
                tag="button",
                text="Buy now",
                placeholder="",
                aria_label="Buy now Masala Snacks",
                clickable=True,
            ),
            ObservedElement(
                element_id="e2",
                index=2,
                role="link",
                tag="a",
                text="About us",
                placeholder="",
                aria_label="",
                href="/about",
                clickable=True,
            ),
            ObservedElement(
                element_id="e3",
                index=3,
                role="button",
                tag="button",
                text="Add to bag",
                placeholder="",
                aria_label="Add to bag Galaxy Buds",
                clickable=True,
            ),
        ],
        products=[
            ObservedProduct(
                product_id="p1",
                title="Masala Snacks",
                price_text="₹99",
                rating_text="4",
                add_element_id="e1",
            ),
            ObservedProduct(
                product_id="p2",
                title="Galaxy Buds FE",
                price_text="₹4999",
                rating_text="4.5",
                add_element_id="e3",
            ),
        ],
    )


def test_buy_now_classified_as_add_to_cart() -> None:
    action = _click("Buy now Potato Chips")
    assert "add_to_cart" in classify_action(action)


def test_add_to_bag_classified_as_add_to_cart() -> None:
    action = _click("Add to bag Galaxy Buds")
    assert "add_to_cart" in classify_action(action)


def test_footer_link_not_product_details() -> None:
    action = _click("About us", element_id="e2", role="link")
    assert "product_details" not in classify_action(action)


def test_complete_purchase_is_checkout() -> None:
    action = _click("Complete purchase")
    assert _is_checkout_action(action)
    el = ObservedElement(
        element_id="e9",
        index=9,
        role="button",
        tag="button",
        text="Complete purchase",
        placeholder="",
        aria_label="",
        clickable=True,
    )
    assert is_checkout_control_element(el)


def test_additional_information_not_add_to_cart() -> None:
    action = _click("Additional information")
    assert not _is_add_to_cart_action(action)


def test_refresh_shopping_target_buy_now() -> None:
    page = _search_page()
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e99",
            role="button",
            description="Buy now Masala Snacks",
        ),
        reason="add snacks",
        expectedOutcome="cart grows",
    )
    resolved = refresh_action_target(action, page)
    assert resolved.target is not None
    assert resolved.target.element_id == "e1"


def test_refresh_generic_target_via_product_listing() -> None:
    page = _search_page()
    action = AgentAction(
        type="click",
        target=ElementTarget(
            element_id="e99",
            role="button",
            description="Add Galaxy Buds FE",
        ),
        reason="add buds",
        expectedOutcome="cart grows",
    )
    resolved = refresh_generic_target(action, page)
    assert resolved.target is not None
    assert resolved.target.element_id == "e3"


def test_same_sku_quantity_second_add_allowed() -> None:
    parsed, spec = parse_task_with_spec("add 2 snacks under 200")
    state = RunState(
        run_id="qty-1",
        task="add 2 snacks under 200",
        parsed_task=parsed,
        task_spec=spec,
    )
    state.bind_skill(
        __import__(
            "agent_runtime.domain.registry", fromlist=["resolve_domain_skill"]
        ).resolve_domain_skill("add 2 snacks under 200")
    )
    assert not multi_distinct_item_goal(state)
    assert goal_item_phrase("2 snacks") == "snacks"

    before = _search_page()
    after = BrowserPage(
        title="Cart",
        url="http://example.test/cart",
        path="/cart",
        search_query="",
        cart_lines=[ObservedCartLine(title="Masala Snacks", quantity=2)],
        elements=[],
        products=[],
        signals=["cart_page"],
    )
    state.memory.remaining_items = list(spec.remaining_items)
    state.memory.verified_items = ["Masala Snacks"]
    state.memory.items_added = 1

    action = _click("Buy now Masala Snacks", element_id="e1")
    ok, reason = action_advances_goal(state, action)
    assert ok, reason

    ok = verify_action_result(
        state, action, success=True, verified=None, before=before, after=after
    )
    assert ok
    progress = apply_verified_progress(state, action, after, ok=ok, before=before)
    assert progress
    assert state.memory.items_added == 2
    assert state.memory.remaining_items == []


def test_same_sku_quantity_third_add_blocked_at_quota() -> None:
    parsed, spec = parse_task_with_spec("add 2 snacks under 200")
    state = RunState(
        run_id="qty-2",
        task="add 2 snacks under 200",
        parsed_task=parsed,
        task_spec=spec,
    )
    state.bind_skill(
        __import__(
            "agent_runtime.domain.registry", fromlist=["resolve_domain_skill"]
        ).resolve_domain_skill("add 2 snacks under 200")
    )
    state.memory.items_added = 2
    state.memory.verified_items = ["Masala Snacks"]
    state.memory.current_page = BrowserPage(
        title="Cart",
        url="http://example.test/cart",
        path="/cart",
        search_query="",
        cart_lines=[ObservedCartLine(title="Masala Snacks", quantity=2)],
        elements=[],
        products=[],
        signals=["cart_page"],
    )
    action = _click("Buy now Masala Snacks")
    ok, reason = action_advances_goal(state, action)
    assert not ok
    assert "quota" in reason.lower() or "blocked" in reason.lower()


def test_quantity_goal_allows_repeat_add_before_quota_in_action_gate() -> None:
    parsed, spec = parse_task_with_spec("add 2 snacks under 200")
    state = RunState(
        run_id="qty-3",
        task="add 2 snacks under 200",
        parsed_task=parsed,
        task_spec=spec,
        current_phase=spec.target_phase,
    )
    state.memory.items_added = 1
    state.memory.verified_items = ["Masala Snacks"]
    kept, blocked = filter_forbidden_actions(
        spec, [_click("Buy now")], current_phase=spec.target_phase, state=state
    )
    assert kept
    assert not blocked


def test_empty_plan_nudge_cart_partial_quota() -> None:
    parsed, spec = parse_task_with_spec("add 2 snacks under 200")
    state = RunState(
        run_id="qty-4",
        task="add 2 snacks under 200",
        parsed_task=parsed,
        task_spec=spec,
        current_phase="cart_updated",
    )
    state.memory.items_added = 1
    state.memory.remaining_items = ["2 snacks"]
    nudge = empty_plan_nudge(state)
    assert "1 more needed" in nudge
    assert "2 snacks" in nudge or "snacks" in nudge


def test_search_inspect_blocks_add_before_milestone() -> None:
    parsed, spec = parse_task_with_spec(
        "compare wireless earbuds and add the best one to my cart"
    )
    state = RunState(
        run_id="cmp-1",
        task="compare wireless earbuds and add the best one to my cart",
        parsed_task=parsed,
        task_spec=spec,
        current_phase="search_results",
    )
    state.bind_skill(
        __import__(
            "agent_runtime.domain.registry", fromlist=["resolve_domain_skill"]
        ).resolve_domain_skill(
            "compare wireless earbuds and add the best one to my cart"
        )
    )
    state.memory.current_page = _search_page()
    action = _click("Buy now Galaxy Buds FE", element_id="e3")
    ok, reason = action_advances_goal(state, action)
    assert not ok
    assert "search" in reason.lower() or "compare" in reason.lower()


def test_refresh_shopping_delegates_to_generic_for_non_add() -> None:
    page = _search_page()
    action = AgentAction(
        type="click",
        target=ElementTarget(element_id="e99", role="link", description="About us"),
        reason="nav",
        expectedOutcome="page",
    )

    def generic(a: AgentAction, p: BrowserPage | None) -> AgentAction:
        return refresh_generic_target(a, p)

    resolved = refresh_shopping_action_target(action, page, generic=generic)
    assert resolved.target is not None
    assert resolved.target.element_id == "e2"


def test_search_type_action_sets_verified_search_milestone() -> None:
    """Regression: missing entity_in_search import crashed record_result after search."""
    parsed, spec = parse_task_with_spec("search for shampoo under ₹300")
    state = RunState(
        run_id="search-type",
        task="search for shampoo under ₹300",
        parsed_task=parsed,
        task_spec=spec,
        memory=TaskMemory(
            goal="search",
            items_target=1,
            remaining_work=["shampoo"],
            remaining_items=["shampoo"],
        ),
        current_phase="search_results",
    )
    action = AgentAction(
        type="type",
        target=ElementTarget(element_id="e1", role="search", description="search"),
        parameters={"text": "shampoo"},
        reason="Type shampoo into the search bar",
        expectedOutcome="search results",
    )
    page = BrowserPage(
        title="Search",
        url="http://localhost:3001/demo/search?q=shampoo",
        path="/demo/search",
        search_query="shampoo",
        elements=[],
        products=[
            ObservedProduct(
                product_id="p1",
                title="Herbal Glow Shampoo 400ml",
                price_text="₹299",
                rating_text="4",
                add_element_id="e5",
            ),
        ],
        signals=["search_results"],
    )

    apply_verified_progress(state, action, page, ok=True)

    assert "verified_search" in state.milestones
    assert state.verified_progress_count == 1


def test_add_verification_uses_header_cart_count() -> None:
    task = "add snacks under ₹200 to my cart"
    parsed, spec = parse_task_with_spec(task)
    state = RunState(
        run_id="header-cart",
        task=task,
        parsed_task=parsed,
        task_spec=spec,
        current_phase=spec.target_phase,
    )
    state.bind_skill(
        __import__(
            "agent_runtime.domain.registry", fromlist=["resolve_domain_skill"]
        ).resolve_domain_skill(task)
    )
    state.memory.remaining_items = ["snacks"]
    before = _search_page()
    before.elements[0] = ObservedElement(
        element_id="e0",
        index=0,
        role="link",
        tag="a",
        text="Cart (0)",
        placeholder="",
        aria_label="Cart, 0 items",
    )
    after = _search_page()
    after.elements[0] = ObservedElement(
        element_id="e0",
        index=0,
        role="link",
        tag="a",
        text="Cart (1)",
        placeholder="",
        aria_label="Cart, 1 items",
    )
    action = _click("Add to cart Masala Snacks", element_id="e1")

    assert verify_action_result(
        state,
        action,
        success=True,
        verified=None,
        before=before,
        after=after,
    )
