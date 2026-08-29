"""Central agent loop: interpret → observe → plan → validate → execute."""

from __future__ import annotations

import logging

from pydantic import ValidationError

from core.action_policy import validate_planner_chunk
from core.agent_phase import AgentPhase
from core.config import config
from core.execution_log import log_intent, log_observe, log_plan, log_run
from core.generic_page_analyzer import get_generic_page_analyzer
from core.generic_recovery import get_generic_recovery, RecoveryAction
from core.goal_verifier import approve_completion
from core.plan_guard_store import apply_store_dom_guard
from core.planner import plan_with_llm
from core.planner_llm import PlannerLlmError
from core.protocol import PlannerChunkOutput, WaitForUserStep
from core.run_manager import RunSession
from core.store_planner import try_store_fast_plan
from core.task_interpretation import interpret_task

logger = logging.getLogger(__name__)

_MAX_VALIDATION_RETRIES = 2


def _store_plan(session: RunSession, intent) -> PlannerChunkOutput | None:
    """
    Optional store-specific fast path + DOM guard (0 LLM).
    This is now OPTIONAL based on configuration - the core agent works without it.
    Only applies for known patterns when shopping features are enabled.
    """
    if not config.enable_store_fast_path:
        # Shopping fast-path disabled - let LLM handle everything
        return None

    chunk = try_store_fast_plan(session)
    if chunk is None:
        # No fast-path available, let LLM handle it
        return None

    if not config.enable_shopping_guards:
        # Fast-path found but guards disabled - return fast-path without guards
        return chunk

    guarded = apply_store_dom_guard(session, chunk)
    if not guarded.steps and guarded.terminal not in {"complete", "system_complete"}:
        return None
    validated = validate_planner_chunk(session, guarded, intent)
    if validated.terminal == "system_complete" or validated.steps:
        return validated
    if guarded.terminal == "complete" and approve_completion(session, intent, source="store_guard"):
        return PlannerChunkOutput(steps=[], terminal="system_complete")
    return validated if validated.steps else None


def set_phase(session: RunSession, phase: AgentPhase) -> None:
    session.phase = phase


async def plan_next_action(session: RunSession) -> PlannerChunkOutput:
    """Single entry point for extension_dom planning."""
    log_run(session.run_id, "plan_next_action", phase=session.phase)

    set_phase(session, "observing")
    interpretation = interpret_task(session.task)
    log_intent(
        session.run_id,
        "interpreted",
        status=interpretation.status,
        goal=interpretation.intent.goal,
    )

    if not interpretation.actionable:
        set_phase(session, "needs_clarification")
        session.needs_clarification_reason = interpretation.reason
        return PlannerChunkOutput(
            steps=[WaitForUserStep(action="wait_for_user")],
            terminal="needs_clarification",
        )

    intent = interpretation.intent
    page = session.latest_page_context

    # Generic page analysis (works for any task)
    if page and config.enable_goal_verification:
        analyzer = get_generic_page_analyzer()
        page_analysis = analyzer.analyze_page(page, page.url)
        log_observe(
            session.run_id,
            "page_context",
            url=page.url if page else None,
            elements=len(page.elements) if page else 0,
            products=len(page.products) if page else 0,
            page_type=page_analysis.page_type,
        )
    else:
        log_observe(
            session.run_id,
            "page_context",
            url=page.url if page else None,
            elements=len(page.elements) if page else 0,
            products=len(page.products) if page else 0,
        )

    if approve_completion(session, intent, source="pre_plan"):
        set_phase(session, "goal_reached")
        return PlannerChunkOutput(steps=[], terminal="system_complete")

    # Generic recovery check (works for any task)
    if config.enable_goal_verification:
        recovery = get_generic_recovery()
        should_handoff, handoff_reason = recovery.should_handoff(session, page)
        if should_handoff:
            set_phase(session, "handoff")
            logger.info(f"Generic recovery: handoff requested - {handoff_reason}")
            return PlannerChunkOutput(
                steps=[WaitForUserStep(action="wait_for_user")],
                terminal="wait_for_user",
            )

    # Optional store-specific fast path (non-blocking)
    store_result = _store_plan(session, intent)
    if store_result is not None:
        if store_result.terminal == "system_complete":
            set_phase(session, "goal_reached")
        elif store_result.steps:
            set_phase(session, "executing")
        log_plan(
            session.run_id,
            session.action_step + 1,
            "store_guard",
            steps=len(store_result.steps),
            terminal=store_result.terminal,
        )
        return store_result

    for attempt in range(_MAX_VALIDATION_RETRIES):
        set_phase(session, "planning")
        try:
            raw = await plan_with_llm(session)
        except (ValidationError, PlannerLlmError):
            set_phase(session, "recovering")
            session.planner_nudge = (
                "Your last JSON was invalid. Return ONE action with required fields "
                "(role, elementIndex, matchText)."
            )
            if attempt + 1 < _MAX_VALIDATION_RETRIES:
                continue
            set_phase(session, "handoff")
            return PlannerChunkOutput(
                steps=[WaitForUserStep(action="wait_for_user")],
                terminal="wait_for_user",
            )
        log_plan(
            session.run_id,
            session.action_step + 1,
            "llm_chunk",
            steps=len(raw.steps),
            terminal=raw.terminal,
        )

        set_phase(session, "action_validation")

        # Apply shopping guards only if enabled (generic mode skips this)
        if config.enable_shopping_guards:
            guarded = apply_store_dom_guard(session, raw)
        else:
            guarded = raw

        validated = validate_planner_chunk(session, guarded, intent)

        # Generic recovery check after validation failure
        if not validated.steps and validated.terminal not in {"wait_for_user", "ready_for_payment_link", "needs_clarification"}:
            if config.enable_goal_verification:
                recovery = get_generic_recovery()
                recovery_action = recovery.analyze_failure(session)
                if recovery_action and recovery_action.action_type == "handoff":
                    set_phase(session, "handoff")
                    return PlannerChunkOutput(
                        steps=[WaitForUserStep(action="wait_for_user")],
                        terminal="wait_for_user",
                    )

        if validated.terminal == "system_complete":
            set_phase(session, "goal_reached")
            return validated

        if validated.steps:
            set_phase(session, "executing")
            return validated

        if validated.terminal in {"wait_for_user", "ready_for_payment_link"}:
            return validated

        if attempt + 1 < _MAX_VALIDATION_RETRIES:
            set_phase(session, "recovering")
            logger.info(
                "Agent loop: validation retry runId=%s attempt=%d",
                session.run_id,
                attempt + 1,
            )
            continue

    set_phase(session, "handoff")
    return PlannerChunkOutput(
        steps=[WaitForUserStep(action="wait_for_user")],
        terminal="wait_for_user",
    )
