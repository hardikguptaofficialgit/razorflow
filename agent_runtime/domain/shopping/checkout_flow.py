"""Generic checkout-flow detection (not store-specific)."""

from __future__ import annotations

import re

from urllib.parse import parse_qs, unquote, urlparse

from agent_runtime.observation.browser_state import BrowserPage


def next_param_points_to_checkout(url: str) -> bool:
    try:
        query = parse_qs(urlparse(url).query)
    except ValueError:
        return False
    next_val = unquote((query.get("next") or [""])[0]).lower()
    return "checkout" in next_val


def is_checkout_flow_page(page: BrowserPage) -> bool:
    path = page.path.lower()
    url = page.url.lower()
    if (
        "/checkout" in path
        or "checkout_page" in page.signals
        or "checkout_auth_gate" in page.signals
    ):
        return True
    if "auth=login" in url and next_param_points_to_checkout(page.url):
        return True
    return False


def checkout_requires_handoff(page: BrowserPage) -> bool:
    """Login gate that blocks checkout completion — requires human input."""
    blob = " ".join(
        (el.text or el.aria_label or "")[:120]
        for el in page.elements[:40]
    ).lower()
    if re.search(r"\bsign\s*in\s+to\s+(?:checkout|check)\b", blob):
        return True
    if not is_checkout_flow_page(page):
        return False
    url = page.url.lower()
    if "auth=login" in url and next_param_points_to_checkout(page.url):
        return True
    if "checkout_auth_gate" in page.signals and "login_required" in page.signals:
        return True
    if "/checkout" in page.path and "login_required" in page.signals:
        return True
    if "login_required" in page.signals and next_param_points_to_checkout(page.url):
        return True
    return False
