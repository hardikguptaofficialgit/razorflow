"""Block actions that do not advance the user's remaining goal."""

from __future__ import annotations

from agent_runtime.executor.actions import AgentAction
from agent_runtime.domain.shopping.action_gate import (
    _is_add_to_cart_action,
    _is_cart_nav_action,
    _is_checkout_action,
    _is_payment_action,
    _is_product_details_action,
    _is_search_action,
    classify_action,
)
from agent_runtime.domain.shopping.action_result import _matches_requested_item
from agent_runtime.domain.shopping.helpers import allows_add_to_cart, multi_distinct_item_goal, shopping_intent
from agent_runtime.domain.shopping.search_state import (
    browse_page_add_task,
    entity_visible_on_page,
    find_goal_ready,
    has_relevant_search_results,
    needs_search,
    on_search_page,
    search_entity,
)
from agent_runtime.state.run_state import RunState
from agent_runtime.domain.shopping.cart import cart_satisfies_add_goal


def goal_quota_met(state: RunState) -> bool:
    target = state.parsed_task.item_count
    if target <= 0:
        return False
    return cart_satisfies_add_goal(state, state.memory.current_page)


def remaining_goal_summary(state: RunState) -> str:
    work = state.memory.remaining_work
    if work:
        return work[0]
    spec = state.task_spec
    if spec:
        return spec.objective
    return state.task


def action_advances_goal(state: RunState, action: AgentAction) -> tuple[bool, str]:
    """Return whether the action directly advances incomplete goal work."""
    page = state.memory.current_page
    spec = state.task_spec
    allows_add = allows_add_to_cart(spec) if spec else state.parsed_task.goal in {
        "add_to_cart",
        "checkout",
        "purchase",
    }

    if find_goal_ready(state, page):
        if action.type in {"scroll", "click", "type", "search"}:
            return False, "find/inspect goal satisfied on search results — stop"

    if browse_page_add_task(state) and action.type in {"search", "type"}:
        return False, "target is on this page — scroll to find it, do not search"

    if goal_quota_met(state) and _is_add_to_cart_action(action):
        return False, "add_to_cart blocked — required item count already in cart"

    if (
        allows_add
        and _is_add_to_cart_action(action)
        and multi_distinct_item_goal(state)
        and action.target
    ):
        label = (
            f"{action.target.description} {action.target.match_text} {action.reason}"
        ).lower()
        entity = search_entity(state)
        for verified in state.memory.verified_items:
            if _matches_requested_item(verified, label):
                if entity and not _matches_requested_item(verified, entity):
                    return (
                        False,
                        f"'{verified}' already in cart — add '{entity}' next, do not increase quantity",
                    )

    if needs_search(state, page):
        if action.type == "scroll":
            return (
                False,
                "search required before scrolling — use the search bar with the target entity",
            )
        if _is_add_to_cart_action(action):
            return False, "search first — do not add from the homepage/browse grid"
        if _is_product_details_action(action) and not on_search_page(page):
            return (
                False,
                "search first — open product pages only after relevant search results",
            )

    if state.current_phase == "search_results" and spec and len(spec.effective_phases()) > 1:
        if _is_add_to_cart_action(action) and "verified_search" not in state.milestones:
            return False, "complete search/compare phase before adding to cart"

    if _is_add_to_cart_action(action) and allows_add:
        entity = search_entity(state)
        if entity and page and not on_search_page(page) and not entity_visible_on_page(page, entity):
            if action.type == "scroll":
                return True, ""
            return (
                False,
                f"'{entity}' is not visible — scroll to reveal it or search first",
            )

    if not allows_add:
        if _is_add_to_cart_action(action):
            return False, "add_to_cart blocked — user did not request adding to cart"
        if _is_checkout_action(action) or _is_payment_action(action):
            return False, "checkout/payment blocked — not requested in this goal"
        if _is_cart_nav_action(action) and state.parsed_task.goal not in {
            "view_cart",
            "checkout",
        }:
            return False, "cart navigation blocked — not part of find/inspect goal"

    if state.memory.remaining_work:
        first = state.memory.remaining_work[0].lower()
        if "goal satisfied" in first or first.startswith("stop"):
            if _is_add_to_cart_action(action) or _is_checkout_action(action):
                return False, "goal already satisfied — do not escalate"

    intent = shopping_intent(spec) if spec else state.parsed_task.goal
    phase = state.current_phase

    if (
        phase == "search_results"
        and intent in {"search", "compare"}
        and not allows_add
        and on_search_page(page)
    ):
        if _is_add_to_cart_action(action):
            return False, "search phase — inspect results only, do not add to cart"
        if has_relevant_search_results(page, state) and action.type in {
            "click",
            "scroll",
            "type",
            "search",
        }:
            if not _is_search_action(action):
                return (
                    False,
                    "find/inspect goal satisfied on search results — stop without further clicks",
                )

    if phase == "cart_updated" and goal_quota_met(state):
        if _is_add_to_cart_action(action):
            return False, "cart quota met — do not add more items"

    categories = classify_action(action)
    if not categories and action.type in {"wait", "scroll", "go_back"}:
        return True, ""
    if not categories and action.type == "navigate":
        return True, ""

    return True, ""


def filter_non_advancing_actions(
    state: RunState,
    actions: list[AgentAction],
) -> tuple[list[AgentAction], list[str]]:
    kept: list[AgentAction] = []
    blocked: list[str] = []
    for action in actions:
        ok, reason = action_advances_goal(state, action)
        if ok:
            kept.append(action)
        else:
            blocked.append(f"{action.type}: {reason}")
    return kept, blocked


def should_stop_without_planning(state: RunState) -> bool:
    """Skip LLM when goal is verified or remaining work says stop."""
    work = state.memory.remaining_work
    if work and any(
        token in work[0].lower()
        for token in ("goal satisfied", "stop", "do not add", "do not open")
    ):
        if goal_quota_met(state) or state.parsed_task.goal in {"search", "compare"}:
            return True
    return False
