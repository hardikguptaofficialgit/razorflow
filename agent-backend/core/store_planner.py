"""Deterministic fast-path planner - now pattern-based (not URL-gated)."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

from core.generic_utils import url_origin
from core.heuristics import _already_searched_for, _needs_fresh_search, _url_search_query
from core.protocol import NavigateUrlStep, PlannerChunkOutput
from core.run_manager import RunSession
from core.search_query import extract_search_query
from core.task_intent import get_active_product_query, parse_task_intent

logger = logging.getLogger(__name__)

_SHOP_HINT = re.compile(
    r"\b(buy|find|search|cheapest|cheap|lowest|price|cart|order|shop|purchase|"
    r"checkout|shampoo|product|add to cart|rating|dress|snacks|earbuds)\b",
    re.I,
)


def is_razorflow_store_url(url: str) -> bool:
    """DEPRECATED: Kept for backward compatibility. Use pattern-based detection instead."""
    from urllib.parse import urlparse
    if not url.strip():
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1"}:
        return True
    return "razorflow" in host


# _store_origin removed - use core.generic_utils.url_origin instead


def try_store_fast_plan(session: RunSession) -> PlannerChunkOutput | None:
    """
    Optional fast-path for known patterns.
    DEPRECATED: This is now optional and should only be used for specific optimizations.
    The core agent should work without any URL-specific fast-paths.
    """
    page = session.latest_page_context
    if page is None:
        return None

    # Only use fast-path if explicitly enabled and on a known pattern
    # For now, keep the RazorFlow check for backward compatibility
    # but this should be removed or made configurable
    if not is_razorflow_store_url(page.url):
        return None

    task_intent = parse_task_intent(session.task)
    if task_intent.goal in {"view_cart", "remove", "update_cart"}:
        return None

    if not _SHOP_HINT.search(session.task):
        return None

    query = get_active_product_query(task_intent, session) or extract_search_query(session.task)
    if not query:
        return None

    from urllib.parse import urlparse
    parsed = urlparse(page.url)
    path = parsed.path.lower()
    url_query = _url_search_query(page.url)
    searched = _already_searched_for(session, query)

    on_search = path.startswith("/search")
    on_product = path.startswith("/product/")
    on_cart = path.startswith("/cart")
    on_checkout = path.startswith("/checkout")
    on_account = path.startswith("/account") or path.startswith("/login")

    if on_account:
        return None

    if on_cart or on_checkout or on_product:
        return None

    if _already_searched_for(session, query) and not on_search:
        return None

    if on_search and page.products and url_query.lower() == query.lower():
        return None

    if on_search and page.products and searched and not _needs_fresh_search(page, query, searched):
        return None

    if searched and on_search and url_query.lower() == query.lower():
        return None

    origin = url_origin(page.url)
    search_url = f"{origin}/search?q={quote(query)}"
    logger.info(
        "Store fast path: navigate search runId=%s query=%s",
        session.run_id,
        query,
    )
    return PlannerChunkOutput(
        steps=[NavigateUrlStep(action="navigate_url", url=search_url)],
        terminal="continue",
    )
