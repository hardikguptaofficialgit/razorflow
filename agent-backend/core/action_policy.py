"""Validate planner output — never allow LLM-only completion."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from core.action_loop import action_signature, consecutive_success_repeats
from core.execution_log import log_action
from core.goal_verifier import approve_completion
from core.protocol import ClickElementStep, NavigateUrlStep, PlannerChunkOutput, WaitForUserStep
from core.run_manager import RunSession
from core.shopping_intent import parse_shopping_intent
from core.step_predicates import is_add_to_cart_step, is_category_nav_step, is_checkout_step
from core.task_intent import TaskIntent, count_successful_adds, filter_steps_for_goal

logger = logging.getLogger(__name__)


def _parse_price_inr(text: str) -> float | None:
    match = re.search(r"[\d,]+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _fallback_step(session: RunSession, intent: TaskIntent):
    page = session.latest_page_context
    if page is None:
        return None

    path = urlparse(page.url).path.lower()
    adds = count_successful_adds(session)

    if intent.goal in {"checkout", "purchase"} and path.startswith("/cart"):
        logger.info("Action policy: fallback navigate checkout runId=%s", session.run_id)
        origin = f"{urlparse(page.url).scheme}://{urlparse(page.url).netloc}"
        return NavigateUrlStep(action="navigate_url", url=f"{origin}/checkout")

    if intent.goal in {"add_to_cart", "checkout", "purchase"} and adds < intent.add_target_count:
        from core.task_intent import used_add_element_indices

        shop = parse_shopping_intent(session.task)
        budget = shop.budget_max
        used = used_add_element_indices(session)
        candidates: list[ClickElementStep] = []
        unused: list[ClickElementStep] = []
        for product in page.products:
            price = _parse_price_inr(product.price_text) if product.price_text else None
            if budget is not None and price is not None and price > budget:
                continue
            index = product.add_to_cart_element_index
            if not index:
                continue
            step = ClickElementStep(
                action="click_element",
                role="button",
                element_index=index,
                match_text="Add to cart",
            )
            candidates.append(step)
            if index not in used:
                unused.append(step)
        chosen = unused[0] if unused else (candidates[0] if candidates else None)
        if chosen is not None:
            logger.info(
                "Action policy: fallback add_to_cart runId=%s index=%s",
                session.run_id,
                chosen.element_index,
            )
            return chosen

    if intent.goal in {"checkout", "purchase"} and not path.startswith("/checkout"):
        for element in page.elements:
            blob = f"{element.text} {element.aria_label}".lower()
            if is_checkout_step(
                ClickElementStep(
                    action="click_element",
                    role=element.role,
                    element_index=element.index,
                    match_text=element.text[:40] if element.text else "checkout",
                )
            ):
                return ClickElementStep(
                    action="click_element",
                    role=element.role,
                    element_index=element.index if element.index > 0 else None,
                    match_text=element.text[:40] or "checkout",
                )

    return None


def _allows_success_repeat(session: RunSession, intent: TaskIntent, step) -> bool:
    """Multi-qty add tasks may repeat the same add-to-cart click."""
    if not is_add_to_cart_step(step):
        return False
    if intent.goal not in {"add_to_cart", "checkout", "purchase"}:
        return False
    return count_successful_adds(session) < intent.add_target_count


def page_requires_login(page) -> bool:
    import re
    from urllib.parse import urlparse

    url = (page.url or "").lower()
    title = (page.title or "").lower()
    blob = f"{url} {title}"
    if "auth=login" in url:
        return True
    if "sign in to checkout" in blob or "sign in to continue" in blob:
        return True
    if page.elements and any(
        getattr(el, "tag", "") in {"data-rf-auth-required", "data-rf-checkout-gate"}
        for el in page.elements
    ):
        return True
    if re.search(r"sign[\s-]?in|log[\s-]?in", blob):
        return bool(re.search(r"checkout|account|order", blob))
    return False


def validate_planner_chunk(
    session: RunSession,
    chunk: PlannerChunkOutput,
    intent: TaskIntent,
) -> PlannerChunkOutput:
    page = session.latest_page_context

    if page is not None and page_requires_login(page):
        url = (page.url or "").lower()
        path = urlparse(page.url).path.lower()
        if intent.goal in {"checkout", "purchase"} and (
            path.startswith("/checkout")
            or ("auth=login" in url and "next=/checkout" in url.replace("%2f", "/"))
        ):
            if approve_completion(session, intent, source="checkout_auth_gate"):
                return PlannerChunkOutput(steps=[], terminal="system_complete")
        logger.info("Action policy: login handoff runId=%s", session.run_id)
        return PlannerChunkOutput(
            steps=[WaitForUserStep(action="wait_for_user")],
            terminal="wait_for_user",
        )

    if approve_completion(session, intent, source="validate_pre"):
        return PlannerChunkOutput(steps=[], terminal="system_complete")

    if chunk.terminal == "complete":
        session.planner_nudge = (
            "Do not return terminal=complete. The runtime approves completion "
            "only after verified browser progress. Return the next action."
        )
        chunk = chunk.model_copy(update={"terminal": "continue"})

    steps = list(chunk.steps)
    steps = [step for step in steps if not is_category_nav_step(step)]
    steps = filter_steps_for_goal(steps, intent)

    if not steps:
        fallback = _fallback_step(session, intent)
        if fallback is not None:
            log_action(
                session.run_id,
                session.action_step + 1,
                "fallback",
                action=fallback.action,
            )
            return PlannerChunkOutput(steps=[fallback], terminal="continue")

        if approve_completion(session, intent, source="validate_empty"):
            return PlannerChunkOutput(steps=[], terminal="system_complete")
        if chunk.terminal in {"wait_for_user", "ready_for_payment_link", "needs_clarification"}:
            return chunk.model_copy(update={"steps": []})
        session.planner_nudge = (
            "Your last plan was blocked or empty. Re-observe the page and return "
            "ONE concrete action (navigate_url, type_in_element, or click_element)."
        )
        return PlannerChunkOutput(steps=[], terminal="continue")

    first = steps[0]
    sig = action_signature(first)
    log_action(
        session.run_id,
        session.action_step + 1,
        "validated",
        action=getattr(first, "action", ""),
        signature=sig[:120],
    )

    if sig in session.blocked_action_signatures:
        session.planner_nudge = (
            f"The action {sig} already failed. Choose a different strategy."
        )
        return PlannerChunkOutput(steps=[], terminal="continue")

    if consecutive_success_repeats(session, sig) >= 1 and not _allows_success_repeat(
        session,
        intent,
        first,
    ):
        remaining = intent.add_target_count - count_successful_adds(session)
        if remaining > 0 and is_add_to_cart_step(first):
            fallback = _fallback_step(session, intent)
            if fallback is not None:
                log_action(
                    session.run_id,
                    session.action_step + 1,
                    "fallback_after_repeat",
                    action=fallback.action,
                )
                return PlannerChunkOutput(steps=[fallback], terminal="continue")
            session.planner_nudge = (
                f"Add {remaining} more suitable product(s) to cart. "
                "Click Add to cart on another qualifying item or add quantity."
            )
        else:
            session.planner_nudge = (
                "You repeated the same action without progress. Choose a different step."
            )
        return PlannerChunkOutput(steps=[], terminal="continue")

    return chunk.model_copy(update={"steps": steps[:1], "terminal": "continue"})
