"""Deterministic fast-path planner for RazorFlow Market (fake-store)."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote, urlparse

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


def _store_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def try_store_fast_plan(session: RunSession) -> PlannerChunkOutput | None:
    """Skip LLM when we can jump straight to a known store route."""
    page = session.latest_page_context
    if page is None or not is_razorflow_store_url(page.url):
        return None
    task_intent = parse_task_intent(session.task)
    if task_intent.goal in {"view_cart", "remove", "update_cart"}:
        return None

    if not _SHOP_HINT.search(session.task):
        return None

    query = get_active_product_query(task_intent, session) or extract_search_query(session.task)
    if not query:
        return None

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

    origin = _store_origin(page.url)
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
