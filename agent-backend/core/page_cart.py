"""Cart count helpers from page context (header badge or cart lines)."""

from __future__ import annotations

import re

from core.protocol import PageContext

_CART_ARIA_RE = re.compile(r"cart,\s*(\d+)\s*items?", re.I)


def header_cart_item_count(page: PageContext | None) -> int:
    if page is None:
        return 0
    if page.cart_lines:
        return sum(line.quantity for line in page.cart_lines)
    for element in page.elements:
        match = _CART_ARIA_RE.search(element.aria_label or "")
        if match:
            return int(match.group(1))
    return 0
