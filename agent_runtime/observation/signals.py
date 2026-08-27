"""Generic page signal detection from URL and visible UI text."""

from __future__ import annotations

import re

from core.protocol import PageContext

from agent_runtime.observation.cart_state import header_cart_item_count

_CHECKOUT_RE = re.compile(
    r"\b(?:checkout|proceed\s+to\s+pay|place\s+order|payment)\b",
    re.I,
)
_CART_RE = re.compile(r"\b(?:your\s+cart|shopping\s+cart|cart\s+total)\b", re.I)
_SEARCH_RE = re.compile(r"\b(?:search\s+results|results\s+for)\b", re.I)


def _element_blob(page: PageContext) -> str:
    parts: list[str] = []
    for el in page.elements[:40]:
        parts.extend([el.text, el.aria_label, el.placeholder])
    return " ".join(parts).lower()


def infer_page_signals(page: PageContext) -> list[str]:
    signals: list[str] = []
    url = (page.url or "").lower()
    blob = _element_blob(page)
    title = (page.title or "").lower()
    combined = f"{url} {title} {blob}"

    if "q=" in url or "/search" in url or _SEARCH_RE.search(combined):
        signals.append("search_results_page")
    if "/cart" in url or (_CART_RE.search(blob) and "/cart" in url):
        signals.append("cart_page")
    if "/checkout" in url or (_CHECKOUT_RE.search(blob) and "/checkout" in url):
        signals.append("checkout_page")
    # Auth gate: URL param or checkout-blocked login — not generic header "Sign in"
    if "auth=login" in url:
        signals.append("login_required")
    elif "/checkout" in url and re.search(
        r"\b(?:sign\s*in\s+to\s+checkout|log\s*in\s+to\s+continue|please\s+log\s*in)\b",
        combined,
        re.I,
    ):
        signals.append("login_required")
    if page.products:
        signals.append(f"products_visible:{len(page.products)}")
    if page.cart_lines:
        signals.append(f"cart_items:{len(page.cart_lines)}")
    cart_badge = header_cart_item_count(page)
    if cart_badge > 0:
        signals.append(f"cart_badge:{cart_badge}")
    return signals
