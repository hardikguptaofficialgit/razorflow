"""Deterministic goal verification — runtime owns completion, not the LLM."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState
from agent_runtime.domain.shopping.helpers import allows_add_to_cart, shopping_intent
from agent_runtime.domain.shopping.spec import GoalPhase
from agent_runtime.domain.shopping.cart import cart_satisfies_add_goal
from agent_runtime.domain.shopping.checkout_flow import is_checkout_flow_page, next_param_points_to_checkout
from agent_runtime.domain.shopping.page_semantics import is_cart_page, is_product_details_page, is_search_results_page
from agent_runtime.domain.shopping.search_state import entity_in_search, search_entity


def _path(url: str) -> str:
    try:
        return urlparse(url).path.lower()
    except ValueError:
        return ""


def _is_product_page(path: str) -> bool:
    return "/product" in path


def _is_search_page(page: BrowserPage) -> bool:
    return is_search_results_page(page)


def _has_results(page: BrowserPage) -> bool:
    return is_search_results_page(page) and bool(page.products or page.search_query)


def phase_satisfied(phase: GoalPhase, state: RunState, page: BrowserPage) -> bool:
    return _phase_satisfied(phase, state, page)


def _phase_satisfied(phase: GoalPhase, state: RunState, page: BrowserPage) -> bool:
    if phase == "search_results":
        if is_product_details_page(page):
            return False
        on_results = _has_results(page) and is_search_results_page(page)
        progress = (
            "verified_search" in state.milestones
            or state.verified_progress_count >= 1
        )
        spec = state.task_spec
        entity = search_entity(state) if spec else ""
        if (
            spec
            and shopping_intent(spec) in {"search", "compare"}
            and not allows_add_to_cart(spec)
            and entity
        ):
            if not entity_in_search(page, entity):
                return False
        if (
            spec
            and shopping_intent(spec) == "add_to_cart"
            and len(spec.effective_phases()) > 1
            and on_results
            and progress
        ):
            return True
        return on_results and progress

    if phase == "product_details":
        return is_product_details_page(page) and state.verified_progress_count >= 1

    if phase == "cart_updated":
        if not cart_satisfies_add_goal(state, page):
            return False
        if "verified_add_to_cart" in state.milestones or state.verified_progress_count >= 1:
            return True
        verified = state.memory.verified_items
        return bool(verified) and len(verified) >= state.parsed_task.item_count

    if phase == "cart_visible":
        return is_cart_page(page)

    if phase in {"checkout", "checkout_reached"}:
        return is_checkout_flow_page(page)

    if phase == "purchase_reached":
        return _phase_satisfied("checkout_reached", state, page)

    if phase == "item_removed":
        task = state.parsed_task
        if task.remove_target:
            needle = task.remove_target.lower()
            for line in page.cart_lines:
                if needle in line.title.lower():
                    return False
        return "verified_remove" in state.milestones

    return False


def _milestones_met(phase: GoalPhase, state: RunState) -> bool:
    if phase == "search_results":
        return "verified_search" in state.milestones
    if phase == "product_details":
        return "verified_search" in state.milestones and _is_product_page(
            state.memory.current_page.path if state.memory.current_page else ""
        )
    if phase == "cart_updated":
        page = state.memory.current_page
        if not cart_satisfies_add_goal(state, page):
            return False
        if "verified_add_to_cart" in state.milestones:
            return True
        verified = state.memory.verified_items
        target = state.parsed_task.item_count
        return bool(verified) and len(verified) >= target
    if phase == "cart_visible":
        return "reached_cart" in state.milestones
    if phase in {"checkout", "checkout_reached", "purchase_reached"}:
        return "reached_checkout" in state.milestones
    if phase == "item_removed":
        return "verified_remove" in state.milestones
    return state.verified_progress_count > 0


def is_goal_satisfied(state: RunState, page: BrowserPage | None) -> bool:
    if page is None or state.task_spec is None:
        return False
    spec = state.task_spec
    phases = spec.effective_phases()
    if len(phases) > 1:
        if state.current_phase != phases[-1]:
            return False
        return _phase_satisfied(state.current_phase, state, page)
    return _phase_satisfied(spec.target_phase, state, page)


def milestones_met(state: RunState) -> bool:
    spec = state.task_spec
    if spec is None:
        return False
    phases = spec.effective_phases()
    phase = state.current_phase if len(phases) > 1 else spec.target_phase
    return _milestones_met(phase, state)


def approve_completion(state: RunState, page: BrowserPage | None, *, source: str) -> bool:
    if page is None:
        return False

    from agent_runtime.domain.shopping.search_state import find_goal_ready

    if find_goal_ready(state, page):
        state.milestones.add("verified_search")
        state.metrics["completion_source"] = source
        return True

    phase = state.current_phase if state.task_spec and len(state.task_spec.effective_phases()) > 1 else (
        state.task_spec.target_phase if state.task_spec else "search_results"
    )
    exempt_from_progress = phase in {
        "search_results",
        "product_details",
        "cart_visible",
    }
    if state.verified_progress_count < 1 and not exempt_from_progress:
        if not (
            phase == "cart_updated"
            and cart_satisfies_add_goal(state, page)
            and len(state.memory.verified_items) >= state.parsed_task.item_count
        ):
            return False
    if not is_goal_satisfied(state, page):
        return False
    if not milestones_met(state):
        return False
    state.metrics["completion_source"] = source
    return True


def update_milestones(state: RunState, page: BrowserPage | None) -> None:
    """Passive observation only records navigational hints — not verified progress."""
    if page is None:
        return
    if is_cart_page(page):
        state.milestones.add("reached_cart")
    if is_checkout_flow_page(page):
        state.milestones.add("reached_checkout")
