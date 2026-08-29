"""Cart-content verification for multi-item goals."""

from __future__ import annotations

import re

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.domain.shopping.helpers import goal_item_phrase, multi_distinct_item_goal
from agent_runtime.domain.shopping.action_result import _matches_requested_item
from agent_runtime.domain.shopping.search_state import entity_search_tokens
from agent_runtime.state.run_state import RunState


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _word_tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", text.lower()))


def cart_item_count(page: BrowserPage | None) -> int:
    if page is None:
        return 0
    if page.cart_lines:
        return sum(line.quantity for line in page.cart_lines)
    for element in page.elements:
        match = re.search(
            r"\bcart\b\D{0,8}(\d+)\s+items?\b",
            f"{element.text} {element.aria_label}",
            re.I,
        )
        if match:
            return int(match.group(1))
    return 0


def cart_matches_hints(page: BrowserPage | None, hints: tuple[str, ...]) -> bool:
    if page is None or not hints:
        return False
    lines = [line for line in page.cart_lines if line.title]
    if not lines:
        return False

    for hint in hints:
        needle = _normalize(hint)
        tokens = entity_search_tokens(needle)
        if not any(
            needle in _normalize(line.title)
            or _normalize(line.title) in needle
            or (
                tokens
                and sum(
                    1
                    for token in tokens
                    if any(
                        token in title_token or title_token in token
                        for title_token in _word_tokens(line.title)
                    )
                )
                >= max(1, (len(tokens) + 1) // 2)
            )
            for line in lines
        ):
            return False
    return True


def cart_satisfies_add_goal(state: RunState, page: BrowserPage | None) -> bool:
    task = state.parsed_task
    if page is None:
        return False
    hints = task.product_hints
    if multi_distinct_item_goal(state) and hints:
        titled_lines = [line for line in page.cart_lines if line.title]
        if titled_lines:
            if len(titled_lines) < len(hints):
                return False
            return cart_matches_hints(page, hints)
        return False

    count = cart_item_count(page)
    if count < task.item_count:
        return False
    if not task.product_hints:
        return True
    if cart_matches_hints(page, task.product_hints):
        return True
    if not multi_distinct_item_goal(state):
        if state.memory.items_added >= task.item_count and state.memory.verified_items:
            return True
        phrase = goal_item_phrase(task.product_hints[0])
        if state.memory.verified_items and any(
            _matches_requested_item(item, phrase)
            or (
                page is not None
                and any(
                    _matches_requested_item(line.title, phrase)
                    for line in page.cart_lines
                )
            )
            for item in state.memory.verified_items
        ):
            return count >= task.item_count
    verified_items = tuple(_normalize(item) for item in state.memory.verified_items)
    return all(
        any(
            hint in item
            or item in hint
            or (
                entity_search_tokens(goal_item_phrase(hint))
                and sum(
                    1
                    for token in entity_search_tokens(goal_item_phrase(hint))
                    if any(
                        token in title_token or title_token in token
                        for title_token in _word_tokens(item)
                    )
                )
                >= max(1, (len(entity_search_tokens(goal_item_phrase(hint))) + 1) // 2)
            )
            for item in verified_items
        )
        for hint in task.product_hints
    )
