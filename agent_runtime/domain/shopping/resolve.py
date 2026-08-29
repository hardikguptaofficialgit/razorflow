"""Shopping-specific target re-resolution (add-to-cart product matching)."""

from __future__ import annotations

import re
from collections.abc import Callable

from agent_runtime.domain.shopping.action_gate import _is_add_to_cart_action
from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.observation.browser_state import BrowserPage, ObservedElement, ObservedProduct

_ELEMENT_ID_RE = re.compile(r"^e(\d+)$", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
_ADD_PREFIX_RE = re.compile(
    r"^(?:add(?:\s+to\s+(?:cart|bag|basket))?|buy(?:\s+now)?|purchase|get)\s+(?:for\s+)?",
    re.I,
)


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


def _find_product_add_button(
    page: BrowserPage,
    needle: str,
) -> tuple[str | None, str | None]:
    best_product: ObservedProduct | None = None
    best_score = 0.0
    for product in page.products:
        score = _score_text(needle, product.title)
        if score > best_score:
            best_score = score
            best_product = product
    if best_product and best_score >= 0.4 and best_product.add_element_id:
        return best_product.add_element_id, best_product.title
    return None, None


def refresh_shopping_action_target(
    action: AgentAction,
    page: BrowserPage | None,
    *,
    generic: Callable[[AgentAction, BrowserPage | None], AgentAction],
) -> AgentAction:
    if page is None or action.target is None or action.type != "click":
        return generic(action, page)

    needle = (action.target.description or action.target.match_text or "").strip()
    if _is_add_to_cart_action(action):
        product_needle = _ADD_PREFIX_RE.sub("", needle).strip() or needle
        add_id, title = _find_product_add_button(page, product_needle)
        if add_id:
            resolved_text = f"Add to cart for {title}" if title else needle
            new_target = ElementTarget(
                element_id=add_id,
                role=action.target.role,
                description=resolved_text or action.target.description,
                match_text=resolved_text or action.target.match_text,
            )
            return action.model_copy(update={"target": new_target})

    return generic(action, page)
