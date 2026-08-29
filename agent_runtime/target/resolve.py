"""Re-resolve planner targets against the latest observation before acting."""

from __future__ import annotations

import re

from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.observation.browser_state import BrowserPage, ObservedElement

_ELEMENT_ID_RE = re.compile(r"^e(\d+)$", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 2}


def _score_text(needle: str, haystack: str) -> float:
    if not needle or not haystack:
        return 0.0
    n = needle.lower().strip()
    h = haystack.lower()
    if n in h:
        return 1.0 + len(n) / max(len(h), 1)
    n_tokens = _tokens(n)
    h_tokens = _tokens(h)
    if not n_tokens:
        return 0.0
    overlap = len(n_tokens & h_tokens) / len(n_tokens)
    return overlap


def _element_blob(el: ObservedElement) -> str:
    return " ".join(
        part
        for part in (el.text, el.aria_label, el.placeholder, el.href, el.value)
        if part
    )


def _find_element_by_text(
    page: BrowserPage,
    needle: str,
    *,
    role: str | None = None,
    prefer_clickable: bool = False,
) -> ObservedElement | None:
    best: ObservedElement | None = None
    best_score = 0.0
    for el in page.elements:
        if role and el.role != role and el.tag != role:
            continue
        if prefer_clickable and not el.clickable and not el.typeable:
            continue
        if not el.enabled:
            continue
        score = _score_text(needle, _element_blob(el))
        if score > best_score:
            best_score = score
            best = el
    return best if best_score >= 0.5 else None


def _element_still_valid(page: BrowserPage, element_id: str | None, needle: str) -> bool:
    if not element_id:
        return False
    match = _ELEMENT_ID_RE.match(element_id.strip())
    if not match:
        return False
    idx = int(match.group(1))
    for el in page.elements:
        if el.index == idx:
            if not needle:
                return el.enabled
            return _score_text(needle, _element_blob(el)) >= 0.35 and el.enabled
    return False


def refresh_action_target(action: AgentAction, page: BrowserPage | None) -> AgentAction:
    """Return a copy of the action with target refreshed from the current page."""
    if page is None or action.target is None:
        return action
    if action.type not in {"click", "type", "search", "scroll"}:
        return action

    target = action.target
    needle = (target.description or target.match_text or "").strip()
    role = target.role

    if _element_still_valid(page, target.element_id, needle):
        return action

    resolved_id: str | None = None
    resolved_text = needle

    if resolved_id is None and needle:
        el = _find_element_by_text(
            page,
            needle,
            role=role if role in {"search", "input", "button", "link"} else None,
            prefer_clickable=action.type == "click",
        )
        if el:
            resolved_id = el.element_id

    if resolved_id is None:
        return action

    new_target = ElementTarget(
        element_id=resolved_id,
        role=target.role,
        description=resolved_text or target.description,
        match_text=resolved_text or target.match_text,
    )
    return action.model_copy(update={"target": new_target})
