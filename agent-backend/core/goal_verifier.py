"""Deterministic goal completion — LLM cannot complete alone."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from core.execution_log import log_done, log_state, log_verify
from core.run_manager import RunSession
from core.search_query import search_queries_equivalent
from core.task_intent import TaskIntent, count_successful_adds, is_goal_satisfied


def _url_search_query(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    values = parse_qs(parsed.query).get("q", [])
    return values[0] if values else ""


def capture_initial_state(session: RunSession, intent: TaskIntent) -> None:
    page = session.latest_page_context
    if page is None:
        session.goal_pre_satisfied = False
        return

    if intent.goal == "search" and is_goal_satisfied(session, intent, page):
        query = extract_task_search_query(intent)
        url_query = _url_search_query(page.url)
        if not query or not url_query or search_queries_equivalent(query, url_query):
            session.milestones.add("verified_search")

    session.goal_pre_satisfied = bool(
        is_goal_satisfied(session, intent, page)
        and _milestones_met(session, intent)
    )
    log_state(
        session.run_id,
        "initial_observation",
        goal=intent.goal,
        pre_satisfied=session.goal_pre_satisfied,
        url=page.url,
    )


def record_verified_action(
    session: RunSession,
    intent: TaskIntent,
    *,
    success: bool,
    verified: bool | None,
) -> None:
    if not success or verified is False:
        return

    session.verified_progress_count += 1
    page = session.latest_page_context
    if page is None:
        return

    path = urlparse(page.url).path.lower()
    last = session.history[-1] if session.history else None
    if last is None:
        return

    step = last.step
    action = getattr(step, "action", "")

    if page is not None and path.startswith("/search"):
        query = _url_search_query(page.url)
        task_query = extract_task_search_query(intent)
        if query and (
            not task_query or search_queries_equivalent(query, task_query)
        ):
            session.milestones.add("verified_search")
            log_verify(session.run_id, session.action_step, "search_results_visible", query=query)

    if action == "navigate_url" and path.startswith("/search"):
        query = _url_search_query(page.url)
        if query:
            session.milestones.add("verified_search")
            log_verify(
                session.run_id,
                session.action_step,
                "search_navigation",
                query=query,
            )

    if action == "type_in_element" and path.startswith("/search"):
        session.milestones.add("verified_search")
        log_verify(session.run_id, session.action_step, "search_typed")

    if action == "click_element":
        label = (getattr(step, "match_text", "") or "").lower()
        if "add to cart" in label or "buy now" in label:
            session.milestones.add("verified_add_to_cart")
            log_verify(session.run_id, session.action_step, "add_to_cart_click")
        if label in {"cart", "go to cart", "view cart"} or (
            "cart" in label and "add" not in label
        ):
            session.milestones.add("reached_cart")
        if "checkout" in label or "proceed" in label:
            session.milestones.add("reached_checkout")

    if path.startswith("/cart"):
        session.milestones.add("reached_cart")
    if path.startswith("/checkout"):
        session.milestones.add("reached_checkout")
    url = (page.url or "").lower()
    if "auth=login" in url and "next=/checkout" in url.replace("%2f", "/"):
        session.milestones.add("reached_checkout")
    if any(
        getattr(el, "tag", "") in {"data-rf-auth-required", "data-rf-checkout-gate"}
        for el in page.elements
    ):
        session.milestones.add("reached_checkout")


def _milestones_met(session: RunSession, intent: TaskIntent) -> bool:
    if intent.goal == "search":
        return "verified_search" in session.milestones

    if intent.goal == "add_to_cart":
        return count_successful_adds(session) >= intent.add_target_count and (
            "verified_add_to_cart" in session.milestones
            or session.verified_progress_count > 0
        )

    if intent.goal == "view_cart":
        return "reached_cart" in session.milestones

    if intent.goal == "checkout":
        return "reached_checkout" in session.milestones

    if intent.goal == "purchase":
        return "reached_checkout" in session.milestones

    if intent.goal == "remove":
        return "reached_cart" in session.milestones and is_goal_satisfied(
            session,
            intent,
            session.latest_page_context,
        )

    if intent.goal == "compare":
        return "verified_search" in session.milestones

    return session.verified_progress_count > 0


def approve_completion(
    session: RunSession,
    intent: TaskIntent,
    *,
    source: str,
) -> bool:
    page = session.latest_page_context
    if page is None:
        log_verify(session.run_id, session.action_step, "reject_no_page", source=source)
        return False

    if not is_goal_satisfied(session, intent, page):
        log_verify(
            session.run_id,
            session.action_step,
            "reject_goal_not_met",
            source=source,
            goal=intent.goal,
        )
        return False

    if session.goal_pre_satisfied:
        log_done(session.run_id, "approved_pre_satisfied", source=source)
        return True

    if session.verified_progress_count < 1:
        log_verify(
            session.run_id,
            session.action_step,
            "reject_no_verified_progress",
            source=source,
        )
        return False

    if not _milestones_met(session, intent):
        log_verify(
            session.run_id,
            session.action_step,
            "reject_milestones",
            source=source,
            milestones=",".join(sorted(session.milestones)),
        )
        return False

    if intent.goal == "search":
        query = extract_task_search_query(intent)
        url_query = _url_search_query(page.url)
        if query and url_query and not search_queries_equivalent(query, url_query):
            log_verify(
                session.run_id,
                session.action_step,
                "reject_search_query_mismatch",
                expected=query,
                actual=url_query,
            )
            return False

    log_done(session.run_id, "approved", source=source, goal=intent.goal)
    return True


def extract_task_search_query(intent: TaskIntent) -> str:
    from core.search_query import extract_search_query

    if intent.product_queries:
        return intent.product_queries[0]
    return extract_search_query(intent.raw_task)
