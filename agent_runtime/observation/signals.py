"""Generic page signal detection from URL and visible UI text."""

from __future__ import annotations

import re

from core.protocol import PageContext

from agent_runtime.observation.cart_state import header_cart_item_count
from agent_runtime.verifier.checkout_flow import next_param_points_to_checkout

_CHECKOUT_RE = re.compile(
    r"\b(?:checkout|proceed\s+to\s+pay|place\s+order|payment)\b",
    re.I,
)
_CHECKOUT_AUTH_RE = re.compile(
    r"\b(?:sign\s*in|log\s*in)\s+to\s+(?:continue|checkout|check)\b",
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
    elif page.products and _SEARCH_RE.search(combined):
        signals.append("search_results_page")
    if page.cart_lines or "/cart" in url or _CART_RE.search(combined):
        signals.append("cart_page")
    if "/checkout" in url or (_CHECKOUT_RE.search(blob) and "/checkout" in url):
        signals.append("checkout_page")
    # Auth gate on checkout flow — not generic header sign-in
    if _CHECKOUT_AUTH_RE.search(combined):
        signals.append("login_required")
        signals.append("checkout_auth_gate")
    elif "auth=login" in url and next_param_points_to_checkout(page.url or ""):
        signals.append("login_required")
        signals.append("checkout_auth_gate")
    elif any(
        el.tag == "data-rf-checkout-auth-gate"
        or "checkout-login-gate" in (el.aria_label or "").lower()
        for el in page.elements[:40]
    ):
        signals.append("login_required")
        signals.append("checkout_auth_gate")
    elif re.search(r"close dialog", blob, re.I) and re.search(
        r"sign\s*in", blob, re.I
    ) and re.search(r"create an accoun", blob, re.I) and "/checkout" not in url:
        signals.append("login_required")
        signals.append("checkout_auth_gate")
    elif "/checkout" in url and re.search(
        r"\b(?:sign\s*in|log\s*in)\b",
        blob,
        re.I,
    ) and re.search(r"\b(?:modal|dialog|password|email)\b", blob, re.I):
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
