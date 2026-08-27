"""Deterministic goal verification."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parser import ParsedTask


def _path(url: str) -> str:
    try:
        return urlparse(url).path.lower()
    except ValueError:
        return ""


def _price_inr(text: str) -> float | None:
    match = re.search(r"(?:₹|rs\.?)\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if not match:
        match = re.search(r"([\d,]+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _cart_count(page: BrowserPage) -> int:
    if page.cart_lines:
        return sum(line.quantity for line in page.cart_lines)
    return 0


def is_goal_satisfied(state: RunState, page: BrowserPage | None) -> bool:
    if page is None:
        return False

    task = state.parsed_task
    goal = task.goal

    if goal == "search":
        return bool(
            state.milestones.intersection({"verified_search"})
            and (page.search_query or "/search" in page.path or page.products)
        )

    if goal in {"compare", "browse"}:
        return "verified_search" in state.milestones and bool(page.products or page.search_query)

    if goal == "view_cart":
        return (
            "/cart" in page.path
            or "cart_page" in page.signals
            or "reached_cart" in state.milestones
        )

    if goal in {"checkout", "purchase"}:
        return (
            "reached_checkout" in state.milestones
            or (
                (
                    "checkout_page" in page.signals
                    or "login_required" in page.signals
                    or "/checkout" in page.path
                    or "auth=login" in page.url.lower()
                )
                and state.verified_progress_count >= 1
            )
        )

    if goal == "remove":
        if task.remove_target:
            needle = task.remove_target.lower()
            for line in page.cart_lines:
                if needle in line.title.lower():
                    return False
        return "/cart" in page.path and state.memory.items_added >= 0

    if goal == "add_to_cart":
        return state.memory.items_added >= task.item_count

    return False


def milestones_met(state: RunState) -> bool:
    task = state.parsed_task
    if task.goal == "search":
        return "verified_search" in state.milestones
    if task.goal == "add_to_cart":
        return (
            state.memory.items_added >= task.item_count
            and "verified_add_to_cart" in state.milestones
        )
    if task.goal == "view_cart":
        return "reached_cart" in state.milestones
    if task.goal in {"checkout", "purchase"}:
        return "reached_checkout" in state.milestones
    if task.goal == "remove":
        return "reached_cart" in state.milestones
    return state.verified_progress_count > 0


def approve_completion(state: RunState, page: BrowserPage | None, *, source: str) -> bool:
    if page is None:
        return False
    if state.verified_progress_count < 1 and state.parsed_task.goal not in {
        "search",
        "compare",
        "view_cart",
    }:
        return False
    if not is_goal_satisfied(state, page):
        return False
    if not milestones_met(state):
        return False
    state.metrics["completion_source"] = source
    return True


def update_milestones(state: RunState, page: BrowserPage | None) -> None:
    if page is None:
        return
    if page.search_query or "/search" in page.path:
        state.milestones.add("verified_search")
    if "/cart" in page.path:
        state.milestones.add("reached_cart")
    if "/checkout" in page.path or "login_required" in page.signals:
        state.milestones.add("reached_checkout")
