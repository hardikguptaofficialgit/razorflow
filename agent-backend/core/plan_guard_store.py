"""Store-specific planner guards — search-first flow and accurate product picks."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from urllib.parse import quote, urlparse

from core.heuristics import _already_searched_for, _url_search_query
from core.product_compare import select_best_product
from core.protocol import (
    ClickElementStep,
    NavigateUrlStep,
    PlannerChunkOutput,
    TypeInElementStep,
    WaitForUserStep,
)
from core.run_manager import RunSession
from core.search_query import alternate_search_query, search_queries_equivalent
from core.shopping_intent import parse_shopping_intent
from core.store_planner import _store_origin, is_razorflow_store_url
from core.task_intent import (
    complete_chunk,
    count_successful_adds,
    filter_steps_for_goal,
    get_active_product_query,
    goal_allows_add_to_cart,
    goal_allows_cart_nav,
    goal_allows_checkout,
    is_goal_satisfied,
    parse_task_intent,
    used_add_element_indices,
)

logger = logging.getLogger(__name__)

_SHOP_HINT = re.compile(
    r"\b(buy|find|search|cheapest|cheap|lowest|price|cart|order|shop|purchase|"
    r"checkout|cooker|product|add to cart|rating|dress|snacks|earbuds?|wireless|home|watch)\b",
    re.I,
)

_STORE_CATEGORY_LABELS = frozenset(
    {
        "all",
        "electronics",
        "personal care",
        "snacks",
        "home",
        "fashion",
    }
)


def _is_category_nav_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").strip().lower()
    return label in _STORE_CATEGORY_LABELS


def _filter_category_nav_steps(steps: list) -> list:
    return [step for step in steps if not _is_category_nav_step(step)]


def _searched_queries(session: RunSession) -> set[str]:
    queries: set[str] = set()
    for entry in session.history:
        if not entry.success:
            continue
        step = entry.step
        if getattr(step, "action", "") != "navigate_url":
            continue
        url_query = _url_search_query(getattr(step, "url", ""))
        if url_query:
            queries.add(url_query.lower())
    return queries


def _handle_empty_search(
    session: RunSession,
    page,
    task_intent,
    query: str,
) -> PlannerChunkOutput | None:
    if not query:
        return None

    alt = alternate_search_query(query)
    searched = _searched_queries(session)
    if alt and alt.lower() not in searched and not _search_query_applied(page, alt):
        logger.info(
            "Store guard: empty results, try alternate runId=%s query=%s alt=%s",
            session.run_id,
            query,
            alt,
        )
        return _navigate_search(page, alt)

    if (
        task_intent.product_queries
        and session.skipped_product_queries + count_successful_adds(session)
        < len(task_intent.product_queries) - 1
    ):
        session.skipped_product_queries += 1
        next_query = get_active_product_query(task_intent, session)
        logger.info(
            "Store guard: skip empty query runId=%s failed=%s next=%s",
            session.run_id,
            query,
            next_query,
        )
        if next_query and not _search_query_applied(page, next_query):
            return _navigate_search(page, next_query)

    if count_successful_adds(session) > 0:
        return complete_chunk()

    return PlannerChunkOutput(
        steps=[WaitForUserStep(action="wait_for_user")],
        terminal="wait_for_user",
    )


def page_requires_login(page) -> bool:
    url = (page.url or "").lower()
    title = (page.title or "").lower()
    blob = f"{url} {title}"
    if "auth=login" in url or "/login" in url:
        return True
    if "sign in to checkout" in blob or "sign in to continue" in blob:
        return True
    if page.elements and any(
        getattr(el, "tag", "") == "data-rf-auth-required" for el in page.elements
    ):
        return True
    if re.search(r"sign[\s-]?in|log[\s-]?in", blob):
        return bool(re.search(r"checkout|account|order", blob))
    return False


def _is_home_path(path: str) -> bool:
    return path in {"", "/"}


def _is_add_to_cart_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").lower()
    return "add to cart" in label or "buy now" in label


def _is_cart_nav_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    if _is_add_to_cart_step(step):
        return False
    label = (step.match_text or "").lower().strip()
    if label in {"cart", "go to cart", "view cart", "bag", "basket"}:
        return True
    return "cart" in label and "add" not in label


def _is_checkout_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").lower()
    return bool(
        re.search(
            r"proceed to checkout|proceed to buy|checkout|place order|pay now",
            label,
        )
    )


def _session_has_cart_items(session: RunSession) -> bool:
    page = session.latest_page_context
    if page and page.cart_lines:
        return True
    if page:
        for element in page.elements:
            blob = f"{element.text} {element.aria_label}".lower()
            if "cart" in blob and re.search(r"\b([1-9]\d*)\s*items?\b", blob):
                return True
            if re.search(r"cart[^\d]*([1-9]\d*)", blob):
                return True

    return count_successful_adds(session) > 0


def _navigate_search(page, query: str) -> PlannerChunkOutput:
    origin = _store_origin(page.url)
    search_url = f"{origin}/search?q={quote(query)}"
    return PlannerChunkOutput(
        steps=[NavigateUrlStep(action="navigate_url", url=search_url)],
        terminal="continue",
    )


def _navigate_checkout(page) -> PlannerChunkOutput:
    origin = _store_origin(page.url)
    return PlannerChunkOutput(
        steps=[NavigateUrlStep(action="navigate_url", url=f"{origin}/checkout")],
        terminal="continue",
    )


def _should_proceed_to_checkout(
    session: RunSession,
    task_intent,
    page,
    path: str,
    has_cart_items: bool,
) -> bool:
    if not goal_allows_checkout(task_intent.goal):
        return False
    url = (page.url or "").lower()
    if path.startswith("/checkout"):
        return False
    if "auth=login" in url and "next=/checkout" in url.replace("%2f", "/"):
        return False

    adds = count_successful_adds(session)
    needs_add = bool(
        re.search(r"\badd\b", task_intent.raw_task, re.I)
        or len(task_intent.product_queries) >= 2
        or task_intent.add_target_count > 1
    )
    if needs_add and adds < task_intent.add_target_count and not has_cart_items:
        return False
    if not needs_add and not has_cart_items:
        return False

    if (
        adds < task_intent.add_target_count
        and path.startswith("/search")
        and page.products
        and goal_allows_add_to_cart(task_intent.goal)
    ):
        return False
    return True


def _intent_for_query(intent, query: str):
    if intent.search_query == query:
        return intent
    return replace(intent, search_query=query, product=query)


def _pick_best_add_to_cart(
    session: RunSession,
    page,
    intent,
    task_intent,
) -> PlannerChunkOutput:
    if not goal_allows_add_to_cart(task_intent.goal):
        if is_goal_satisfied(session, task_intent, page):
            return complete_chunk()
        return PlannerChunkOutput(
            steps=[WaitForUserStep(action="wait_for_user")],
            terminal="wait_for_user",
        )

    if count_successful_adds(session) >= task_intent.add_target_count:
        logger.info(
            "Store guard: add goal satisfied runId=%s adds=%s target=%s",
            session.run_id,
            count_successful_adds(session),
            task_intent.add_target_count,
        )
        return complete_chunk()

    best, _candidates, reason = select_best_product(
        page,
        intent,
        exclude_element_indices=used_add_element_indices(session),
    )
    if best is None:
        logger.info(
            "Store guard: no matching product runId=%s reason=%s budget=%s",
            session.run_id,
            reason,
            intent.budget_max,
        )
        if count_successful_adds(session) > 0:
            return complete_chunk()
        return PlannerChunkOutput(
            steps=[WaitForUserStep(action="wait_for_user")],
            terminal="wait_for_user",
        )

    cart_index = best.add_to_cart_element_index or best.element_index
    if not cart_index:
        if count_successful_adds(session) > 0:
            return complete_chunk()
        return PlannerChunkOutput(
            steps=[WaitForUserStep(action="wait_for_user")],
            terminal="wait_for_user",
        )

    logger.info(
        "Store guard: pick product runId=%s title=%s index=%s",
        session.run_id,
        best.title[:48],
        cart_index,
    )
    return PlannerChunkOutput(
        steps=[
            ClickElementStep(
                action="click_element",
                role="button",
                element_index=cart_index,
                match_text="Add to cart",
            ),
        ],
        terminal="continue",
    )


def _search_query_applied(page, query: str) -> bool:
    if not query:
        return False
    url_query = _url_search_query(page.url)
    if not url_query:
        return False
    return search_queries_equivalent(url_query, query)


def _block_beyond_goal(
    session: RunSession,
    chunk: PlannerChunkOutput,
    task_intent,
    page,
    intent,
    path: str,
    has_cart_items: bool,
) -> PlannerChunkOutput | None:
    if is_goal_satisfied(session, task_intent, page):
        return complete_chunk()

    filtered_steps = filter_steps_for_goal(chunk.steps, task_intent)
    if filtered_steps != chunk.steps:
        logger.info(
            "Store guard: filtered steps for goal=%s runId=%s",
            task_intent.goal,
            session.run_id,
        )
        if not filtered_steps:
            if is_goal_satisfied(session, task_intent, page):
                return complete_chunk()
            if task_intent.goal == "add_to_cart" and path.startswith("/search") and page.products:
                return _pick_best_add_to_cart(session, page, intent, task_intent)
            if task_intent.goal == "add_to_cart":
                return complete_chunk()
            return chunk.model_copy(update={"steps": [], "terminal": "continue"})
        chunk = chunk.model_copy(update={"steps": filtered_steps})

    for step in chunk.steps:
        if _is_checkout_step(step) and not goal_allows_checkout(task_intent.goal):
            logger.info(
                "Store guard: block checkout runId=%s goal=%s",
                session.run_id,
                task_intent.goal,
            )
            if task_intent.goal == "add_to_cart" and has_cart_items:
                return complete_chunk()
            if path.startswith("/search") and page.products and goal_allows_add_to_cart(task_intent.goal):
                return _pick_best_add_to_cart(session, page, intent, task_intent)
            return complete_chunk()

        if _is_cart_nav_step(step) and not goal_allows_cart_nav(task_intent.goal):
            logger.info(
                "Store guard: block cart nav runId=%s goal=%s",
                session.run_id,
                task_intent.goal,
            )
            if task_intent.goal == "add_to_cart":
                if count_successful_adds(session) >= task_intent.add_target_count:
                    return complete_chunk()
                if path.startswith("/search") and page.products:
                    return _pick_best_add_to_cart(session, page, intent, task_intent)
                if query := get_active_product_query(task_intent, session) or intent.search_query:
                    return _navigate_search(page, query)
            return complete_chunk()

    return None


def apply_store_dom_guard(
    session: RunSession,
    chunk: PlannerChunkOutput,
) -> PlannerChunkOutput:
    page = session.latest_page_context
    if page is None or not is_razorflow_store_url(page.url):
        return chunk
    if not _SHOP_HINT.search(session.task):
        return chunk

    task_intent = parse_task_intent(session.task)
    intent = parse_shopping_intent(session.task)
    query = get_active_product_query(task_intent, session) or intent.search_query
    intent = _intent_for_query(intent, query)
    parsed = urlparse(page.url)
    path = parsed.path.lower()
    has_cart_items = _session_has_cart_items(session)

    if task_intent.goal == "view_cart" and not path.startswith("/cart"):
        logger.info("Store guard: open cart runId=%s", session.run_id)
        origin = _store_origin(page.url)
        return PlannerChunkOutput(
            steps=[NavigateUrlStep(action="navigate_url", url=f"{origin}/cart")],
            terminal="continue",
        )

    if task_intent.goal == "remove" and not path.startswith("/cart"):
        logger.info("Store guard: cart for remove runId=%s", session.run_id)
        origin = _store_origin(page.url)
        return PlannerChunkOutput(
            steps=[NavigateUrlStep(action="navigate_url", url=f"{origin}/cart")],
            terminal="continue",
        )

    if _should_proceed_to_checkout(session, task_intent, page, path, has_cart_items):
        logger.info(
            "Store guard: proceed checkout runId=%s path=%s",
            session.run_id,
            path,
        )
        return _navigate_checkout(page)

    if is_goal_satisfied(session, task_intent, page):
        logger.info(
            "Store guard: goal satisfied runId=%s goal=%s",
            session.run_id,
            task_intent.goal,
        )
        return complete_chunk()

    blocked = _block_beyond_goal(
        session, chunk, task_intent, page, intent, path, has_cart_items
    )
    if blocked is not None:
        return blocked

    if chunk.steps:
        filtered_steps = _filter_category_nav_steps(chunk.steps)
        if len(filtered_steps) < len(chunk.steps):
            logger.info(
                "Store guard: block category nav runId=%s goal=%s query=%s",
                session.run_id,
                task_intent.goal,
                query,
            )
            if path.startswith("/search") and not page.products:
                handled = _handle_empty_search(session, page, task_intent, query)
                if handled is not None:
                    return handled
            if goal_allows_add_to_cart(task_intent.goal) and query:
                if not _search_query_applied(page, query):
                    return _navigate_search(page, query)
                if path.startswith("/search") and page.products:
                    return _pick_best_add_to_cart(session, page, intent, task_intent)
            chunk = chunk.model_copy(update={"steps": filtered_steps or []})

    if (
        path.startswith("/search")
        and query
        and _search_query_applied(page, query)
        and not page.products
        and goal_allows_add_to_cart(task_intent.goal)
    ):
        handled = _handle_empty_search(session, page, task_intent, query)
        if handled is not None:
            return handled

    if task_intent.goal == "search" and path.startswith("/search") and page.products:
        if _search_query_applied(page, query):
            return complete_chunk()

    if any(isinstance(step, TypeInElementStep) for step in chunk.steps) and query:
        logger.info(
            "Store guard: replace type with navigate search runId=%s query=%s",
            session.run_id,
            query,
        )
        return _navigate_search(page, query)

    if path.startswith("/checkout") and page_requires_login(page):
        return PlannerChunkOutput(
            steps=[WaitForUserStep(action="wait_for_user")],
            terminal="wait_for_user",
        )

    if path.startswith("/checkout") and not goal_allows_checkout(task_intent.goal):
        logger.info(
            "Store guard: leave checkout runId=%s goal=%s",
            session.run_id,
            task_intent.goal,
        )
        return complete_chunk()

    if not path.startswith("/cart") and not has_cart_items:
        for step in chunk.steps:
            if _is_cart_nav_step(step):
                logger.info(
                    "Store guard: block early cart runId=%s path=%s",
                    session.run_id,
                    path,
                )
                if path.startswith("/search") and page.products:
                    return _pick_best_add_to_cart(session, page, intent, task_intent)
                if query:
                    return _navigate_search(page, query)
                return PlannerChunkOutput(
                    steps=[WaitForUserStep(action="wait_for_user")],
                    terminal="wait_for_user",
                )

    if (_is_home_path(path) or path.startswith("/search")) and query:
        if _search_query_applied(page, query) and not page.products:
            handled = _handle_empty_search(session, page, task_intent, query)
            if handled is not None:
                return handled

        if not _search_query_applied(page, query):
            if not any(isinstance(step, NavigateUrlStep) for step in chunk.steps):
                logger.info(
                    "Store guard: navigate search runId=%s query=%s",
                    session.run_id,
                    query,
                )
                return _navigate_search(page, query)

        if path.startswith("/search") and page.products and goal_allows_add_to_cart(task_intent.goal):
            for step in chunk.steps:
                if not _is_add_to_cart_step(step):
                    continue
                return _pick_best_add_to_cart(session, page, intent, task_intent)

            if count_successful_adds(session) < task_intent.add_target_count:
                return _pick_best_add_to_cart(session, page, intent, task_intent)

    if _is_home_path(path) and query:
        for step in chunk.steps:
            if _is_add_to_cart_step(step):
                logger.info(
                    "Store guard: search before add on home runId=%s query=%s",
                    session.run_id,
                    query,
                )
                return _navigate_search(page, query)

        if not _already_searched_for(session, query) and not any(
            isinstance(step, NavigateUrlStep) for step in chunk.steps
        ):
            logger.info(
                "Store guard: navigate search from home runId=%s query=%s",
                session.run_id,
                query,
            )
            return _navigate_search(page, query)

    return chunk
