"""Shared helpers for search-vs-browse page state."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import re

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState

_ON_THIS_PAGE = re.compile(r"\bon\s+(?:this|the)\s+page\b", re.I)
_ENTITY_QUALIFIERS = frozenset(
    {
        "cheapest",
        "best",
        "good",
        "nice",
        "great",
        "cheap",
        "affordable",
        "decent",
        "wireless",
        "multiple",
        "several",
    }
)


def on_search_page(page: BrowserPage | None) -> bool:
    if page is None:
        return False
    return bool(page.search_query or "/search" in page.path)


def _url_query(page: BrowserPage) -> str:
    if page.search_query:
        return page.search_query.lower()
    try:
        params = parse_qs(urlparse(page.url).query)
        for key in ("q", "query", "search"):
            if params.get(key):
                return (params[key][0] or "").lower()
    except ValueError:
        pass
    return ""


def search_entity(state: RunState) -> str:
    spec = state.task_spec
    if spec and spec.entities:
        return spec.entities[0]
    hints = state.parsed_task.product_hints
    return hints[0] if hints else ""


def entity_search_tokens(entity: str) -> tuple[str, ...]:
    words = [
        word
        for word in re.findall(r"[a-z0-9]+", entity.lower())
        if len(word) >= 3 and word not in _ENTITY_QUALIFIERS
    ]
    if words:
        return tuple(words)
    return tuple(re.findall(r"[a-z0-9]+", entity.lower()))


def entity_in_search(page: BrowserPage | None, entity: str) -> bool:
    if page is None or not entity.strip():
        return False
    needle = entity.lower().strip()
    blob = f"{_url_query(page)} {page.url.lower()} {(page.search_query or '').lower()}"
    if needle in blob:
        return True
    tokens = entity_search_tokens(entity)
    return bool(tokens) and any(token in blob for token in tokens)


def has_relevant_search_results(
    page: BrowserPage | None,
    state: RunState | None = None,
) -> bool:
    if not on_search_page(page) or page is None:
        return False
    if not (page.products or page.search_query or _url_query(page)):
        return False
    entity = search_entity(state) if state else ""
    if not entity:
        return True
    if entity_in_search(page, entity):
        return True
    if (
        state is not None
        and "verified_search" in state.milestones
        and entity_visible_on_page(page, entity)
    ):
        return True
    if state is not None and "verified_search" in state.milestones:
        tokens = entity_search_tokens(entity)
        return any(entity_visible_on_page(page, token) for token in tokens)
    return False


def is_click_control_task(state: RunState) -> bool:
    spec = state.task_spec
    if spec is None:
        return False
    return spec.objective.startswith("Click the requested UI control")


def browse_page_add_task(state: RunState) -> bool:
    spec = state.task_spec
    raw = spec.raw.lower() if spec else state.task.lower()
    return bool(_ON_THIS_PAGE.search(raw) and re.search(r"\band\s+add\b", raw, re.I))


def needs_search(state: RunState, page: BrowserPage | None) -> bool:
    spec = state.task_spec
    intent = spec.intent if spec else state.parsed_task.goal
    if is_click_control_task(state):
        return False
    if browse_page_add_task(state):
        return False

    if intent == "add_to_cart" and spec and len(spec.effective_phases()) > 1:
        if state.current_phase == "search_results" and "verified_search" not in state.milestones:
            if page and on_search_page(page) and page.products:
                return not has_relevant_search_results(page, state)
        return False

    if intent not in {"search", "compare"}:
        if spec and spec.goal_phases and spec.goal_phases[0] == "search_results":
            if state.current_phase == "search_results" and "verified_search" not in state.milestones:
                return not has_relevant_search_results(page, state)
        return False
    entity = search_entity(state)
    if on_search_page(page) and entity and not entity_in_search(page, entity):
        return True
    if "verified_search" in state.milestones:
        return False
    return not has_relevant_search_results(page, state)


def find_goal_ready(state: RunState, page: BrowserPage | None) -> bool:
    spec = state.task_spec
    if spec is None or page is None:
        return False
    if spec.intent not in {"search", "compare"} or spec.allows_add_to_cart:
        return False
    if "verified_search" not in state.milestones:
        return False
    entity = search_entity(state)
    if entity and not entity_in_search(page, entity):
        return False
    return has_relevant_search_results(page, state)


def entity_visible_on_page(page: BrowserPage | None, entity: str) -> bool:
    if page is None or not entity.strip():
        return False
    needle = entity.lower()
    tokens = entity_search_tokens(entity)
    for product in page.products:
        title = (product.title or "").lower()
        if needle in title or title in needle:
            return True
        title_tokens = tuple(re.findall(r"[a-z0-9]+", title))
        matched_tokens = sum(
            1
            for token in tokens
            if any(token in title_token or title_token in token for title_token in title_tokens)
        )
        if matched_tokens >= max(1, (len(tokens) + 1) // 2):
            return True
    for el in page.elements:
        text = f"{el.text or ''} {el.aria_label or ''}".lower()
        if len(needle) >= 4 and needle in text:
            return True
    return False
