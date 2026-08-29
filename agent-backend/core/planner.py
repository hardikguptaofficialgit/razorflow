"""Single LLM planner for RazorFlow — no competing heuristic planners."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from core.action_loop import detect_loop_nudge
from core.browser_observer import observe_page_for_planning
from core.protocol import (
    BrowserObservation,
    PageContext,
    PlannerChunkOutput,
    PlanningSource,
)
from core.planner_llm import (
    PlannerConfigurationError,
    PlannerLlmError,
    complete_planner_json,
)
from core.planner_repair import repair_planner_payload
from core.shopping_intent import parse_shopping_intent
from core.task_intent import count_successful_adds, parse_task_intent
from utils.config import (
    MAX_STEPS_PER_CHUNK,
    get_planner_llm_provider,
    is_browser_use_executor_enabled,
)

logger = logging.getLogger(__name__)

_SHOP_TASK_HINT = re.compile(
    r"\b(buy|find|search|cheapest|cart|order|shop|purchase|checkout|product|remove|view)\b",
    re.I,
)


SYSTEM_PROMPT = """You are RazorFlow's browser agent planner.

You plan exactly ONE structured action per turn for a client that executes on the live page.

Return ONLY valid JSON:
{
  "steps": [ { ...one action... } ],
  "terminal": "continue" | "complete" | "wait_for_user" | "ready_for_payment_link",
  "paymentProposal": { "title": "...", "description": "...", "amountPaise": 29900, "currency": "INR" }
}

Allowed step actions:
- set_state, type_in_element, click_element, highlight_element, navigate_url, wait_for_user, ready_for_payment_link

Rules:
1. Observe the CURRENT page context (elements + products). Never assume an action succeeded until you see new context.
2. elementIndex is 1-based from the Interactive elements list. Always set elementIndex AND role.
3. matchText is a short visible label for verification.
4. Follow TASK GOAL strictly — never exceed scope:
   - search: stop at search results (terminal=complete). Do NOT add to cart or open cart.
   - add_to_cart: add required item(s), verify via cart count, then terminal=complete. Do NOT open cart unless asked.
   - view_cart: open cart page only, then complete.
   - checkout: reach checkout review, then complete or wait_for_user.
   - purchase/buy: full flow through payment when appropriate.
   - remove: open cart if needed, remove the named item, then complete.
5. Use observed links and controls. Never invent site-specific route patterns.
6. For multi-item add tasks, handle ONE product query at a time.
7. If the last action failed, choose a different strategy — never repeat the same step.
8. wait_for_user only for login, CAPTCHA, OTP, or payment confirmation.
9. ready_for_payment_link only when checkout total is visible.
10. terminal=complete only when the TASK GOAL is fully satisfied on the current page.
11. No markdown."""


def _format_history(session: RunSession) -> str:
    if not session.history:
        return "Recent actions: none"

    lines = ["Recent actions:"]
    for entry in session.history[-8:]:
        status = "ok" if entry.success else "failed"
        dumped = entry.step.model_dump(by_alias=True, exclude_none=True)
        verified = (
            f" verified={entry.verified}"
            if entry.verified is not None
            else ""
        )
        error = f" error={entry.error}" if entry.error else ""
        lines.append(f"- {dumped} [{status}]{verified}{error}")
    return "\n".join(lines)


def _format_page_context(page_context: PageContext | None) -> str:
    if page_context is None:
        return "Page context: unavailable"

    lines = [
        f"Page title: {page_context.title}",
        f"Page URL: {page_context.url}",
        "Interactive elements (use these elementIndex values):",
    ]

    if not page_context.elements:
        lines.append("- none detected")
    else:
        for position, element in enumerate(page_context.elements, start=1):
            index = element.index if element.index > 0 else position
            lines.append(
                f"{index}. role={element.role} tag={element.tag} "
                f'text="{element.text}" placeholder="{element.placeholder}" '
                f'ariaLabel="{element.aria_label}"'
            )

    if page_context.products:
        lines.append("Product-like items:")
        for product in page_context.products:
            price = f" | price={product.price_text}" if product.price_text else ""
            rating = f" | rating={product.rating_text}" if product.rating_text else ""
            link_index = (
                f" | elementIndex={product.element_index}"
                if product.element_index
                else ""
            )
            cart_index = (
                f" | addToCartIndex={product.add_to_cart_element_index}"
                if product.add_to_cart_element_index
                else ""
            )
            lines.append(f"- {product.title}{price}{rating}{link_index}{cart_index}")

    if page_context.cart_lines:
        lines.append("Cart lines:")
        for line in page_context.cart_lines:
            lines.append(
                f"- {line.title} qty={line.quantity} | removeIndex={line.remove_element_index}"
            )

    return "\n".join(lines)


def _format_browser_observation(observation: BrowserObservation | None) -> str:
    if observation is None:
        return ""

    lines = [
        "Browser-use observation (hints only):",
        observation.page_summary,
    ]
    return "\n".join(lines)


def _build_user_prompt(
    session: RunSession,
    observation: BrowserObservation | None,
    planning_source: PlanningSource,
) -> str:
    guidance: list[str] = []
    if session.planner_nudge:
        guidance.append(session.planner_nudge)
        session.planner_nudge = None

    if session.consecutive_failures:
        guidance.append(
            f"Recovery: {session.consecutive_failures} consecutive failure(s). "
            "Re-observe and choose a different elementIndex."
        )
    if session.stale_page_turns:
        guidance.append(
            f"Stall: page unchanged for {session.stale_page_turns} turn(s)."
        )

    loop_nudge = detect_loop_nudge(session)
    if loop_nudge:
        guidance.append(loop_nudge)

    page = session.latest_page_context

    intent_block = ""
    if _SHOP_TASK_HINT.search(session.task.strip()):
        intent_block = (
            f"{parse_task_intent(session.task).prompt_block()}\n"
            f"{parse_shopping_intent(session.task).prompt_block()}\n"
        )

    screenshot_note = ""
    if page and page.screenshot_data_url:
        screenshot_note = "Page screenshot attached for vision.\n"

    return (
        f"Task: {session.task.strip()}\n"
        f"Planning turn: {session.planning_turn + 1}\n"
        f"Phase: {session.phase}\n"
        f"Input source: {planning_source}\n"
        f"{intent_block}"
        f"{screenshot_note}"
        f"{' '.join(guidance)}\n"
        f"{_format_history(session)}\n"
        f"{_format_page_context(session.latest_page_context)}\n"
        f"{_format_browser_observation(observation)}\n"
        "Return exactly one next action JSON."
    )


def _extract_json_content(raw: str) -> dict[str, Any]:
    content = raw.strip()
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```").strip()
        if content.endswith("```"):
            content = content[:-3].strip()
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Planner output must be a JSON object.")
    return parsed


def _normalize_chunk(chunk: PlannerChunkOutput) -> PlannerChunkOutput:
    filtered = [
        step
        for step in chunk.steps
        if getattr(step, "action", None) != "set_state"
        or step.state == "waiting_for_user"
    ]
    steps = (filtered or list(chunk.steps))[:MAX_STEPS_PER_CHUNK]
    return PlannerChunkOutput(
        steps=steps,
        terminal=chunk.terminal,
        payment_proposal=chunk.payment_proposal,
    )


def _plan_next_chunk_with_llm(
    session: RunSession,
    observation: BrowserObservation | None,
    planning_source: PlanningSource,
) -> PlannerChunkOutput:
    screenshot_data_url = None
    page = session.latest_page_context
    if page is not None:
        screenshot_data_url = page.screenshot_data_url

    raw_content = complete_planner_json(
        SYSTEM_PROMPT,
        _build_user_prompt(session, observation, planning_source),
        screenshot_data_url=screenshot_data_url,
    )
    payload = _extract_json_content(raw_content)
    payload = repair_planner_payload(payload, session.latest_page_context)
    try:
        return _normalize_chunk(PlannerChunkOutput.model_validate(payload))
    except (ValidationError, ValueError) as error:
        raise PlannerLlmError(f"Invalid planner output: {error}") from error


async def plan_with_llm(session: RunSession) -> PlannerChunkOutput:
    """Call the configured LLM planner (OpenRouter → Groq → Gemini)."""
    observation: BrowserObservation | None = None
    planning_source: PlanningSource = "page_context_only"
    include_observer = is_browser_use_executor_enabled()

    if include_observer:
        observation, planning_source = await observe_page_for_planning(
            session.run_id,
            session.latest_page_context,
        )
        session.last_browser_observation = observation
    else:
        session.last_browser_observation = None

    session.last_planning_source = planning_source
    provider = get_planner_llm_provider()
    logger.info(
        "LLM planner runId=%s turn=%s provider=%s source=%s",
        session.run_id,
        session.planning_turn + 1,
        provider,
        planning_source,
    )

    return await asyncio.to_thread(
        _plan_next_chunk_with_llm,
        session,
        observation,
        planning_source,
    )


async def plan_next_chunk(session: RunSession) -> PlannerChunkOutput:
    """Public API — delegates to the centralized agent loop."""
    from core.agent_loop import plan_next_action

    try:
        return await plan_next_action(session)
    except PlannerConfigurationError:
        raise
    except (ValidationError, ValueError, json.JSONDecodeError, PlannerLlmError) as error:
        provider = get_planner_llm_provider()
        raise ValueError(f"Invalid {provider} planner output: {error}") from error
    except Exception as error:
        provider = get_planner_llm_provider()
        raise ValueError(f"{provider} planner failed: {error}") from error
