"""Semantic page-state detection — avoid hardcoded URL path assumptions."""

from __future__ import annotations

from agent_runtime.observation.browser_state import BrowserPage


def is_search_results_page(page: BrowserPage) -> bool:
    if "search_results_page" in page.signals:
        return True
    if page.search_query and (page.products or "/search" in page.path or "q=" in page.url.lower()):
        return True
    return bool(page.products) and (
        page.search_query
        or "/search" in page.path
        or "q=" in page.url.lower()
        or "search_results_page" in page.signals
    )


def is_cart_page(page: BrowserPage) -> bool:
    if "cart_page" in page.signals or "cart_visible" in page.signals:
        return True
    if page.cart_lines:
        return True
    return any(signal.startswith("cart_badge:") for signal in page.signals)


def is_product_details_page(page: BrowserPage) -> bool:
    if "/product" in page.path:
        return True
    if page.products and len(page.products) == 1 and not page.search_query:
        return True
    return "product_details_page" in page.signals
