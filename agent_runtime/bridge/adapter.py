"""Bridge server integration for Agent Runtime V2."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from core.protocol import (
    ActionResultMessage,
    ActionStep,
    NextActionMessage,
    PageContext,
    RunCompleteMessage,
    RunErrorMessage,
    RunNeedsClarificationMessage,
    RunWaitingForUserMessage,
    StartRunMessage,
)
from core.run_manager import RunManager

from agent_runtime.chat.messages import clarification_message
from agent_runtime.runtime import AgentRuntime, DispatchResult
from agent_runtime.state.run_state import RunState

logger = logging.getLogger(__name__)

SendJson = Callable[[dict[str, Any]], Awaitable[None]]

_runtime: AgentRuntime | None = None
_v2_run_ids: set[str] = set()


def get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime


def reset_runtime() -> None:
    """Test hook: rebuild runtime (e.g. after setting AGENT_LLM_TEST_FIXTURE)."""
    global _runtime
    _runtime = AgentRuntime()


def get_v2_state(run_id: str) -> RunState | None:
    return get_runtime().get_run(run_id)


def is_v2_run(run_id: str) -> bool:
    return run_id in _v2_run_ids


async def handle_start_run(
    send_json: SendJson,
    run_manager: RunManager,
    session,
    message: StartRunMessage,
    *,
    agent_config: object | None = None,
) -> None:
    state = await asyncio.to_thread(
        get_runtime().start_run,
        message.run_id,
        message.task,
        message.page_context,
        connection_id=session.connection_id or "",
        agent_config=agent_config,
    )
    _v2_run_ids.add(message.run_id)

    if state.phase.value == "needs_clarification":
        session.needs_clarification_reason = state.needs_clarification_reason
        run_manager.wait_for_user(session)
        await send_json(
            RunNeedsClarificationMessage(
                type="RUN_NEEDS_CLARIFICATION",
                runId=message.run_id,
                message=clarification_message(message.task),
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    await dispatch_next(send_json, run_manager, session)


async def handle_action_result(
    send_json: SendJson,
    run_manager: RunManager,
    message: ActionResultMessage,
) -> None:
    session = run_manager.get_run(message.run_id)
    state = get_runtime().get_run(message.run_id)
    if session is None or state is None:
        return

    action = state.last_dispatched_action
    if action is None:
        await dispatch_next(send_json, run_manager, session)
        return

    run_manager.record_action_result(
        session,
        message.step,
        message.success,
        message.error,
        message.page_context,
        message.verified,
    )

    result = await asyncio.to_thread(
        get_runtime().record_result,
        state,
        action,
        success=message.success,
        verified=message.verified,
        error=message.error,
        page_context=message.page_context,
    )
    last = state.action_history[-1] if state.action_history else None
    if last and last.verified is True and not message.success:
        session.consecutive_failures = 0
    if result.kind == "continue" and not result.steps:
        await dispatch_next(send_json, run_manager, session)
        return
    await _apply_dispatch(send_json, run_manager, session, state, result)


async def handle_resume_run(
    send_json: SendJson,
    run_manager: RunManager,
    run_id: str,
    page_context: PageContext | None,
) -> bool:
    session = run_manager.resume_run(run_id, page_context)
    state = get_runtime().resume_run(run_id, page_context)
    if session is None or state is None:
        return False
    await dispatch_next(send_json, run_manager, session)
    return True


async def handle_cancel(run_id: str) -> None:
    get_runtime().cancel_run(run_id)
    _v2_run_ids.discard(run_id)


async def dispatch_next(
    send_json: SendJson,
    run_manager: RunManager,
    session,
) -> None:
    state = get_runtime().get_run(session.run_id)
    if state is None:
        return

    safeguard_error = run_manager.check_safeguards(session)
    if safeguard_error:
        run_manager.fail_run(session, safeguard_error)
        await send_json(
            RunErrorMessage(
                type="RUN_ERROR",
                runId=session.run_id,
                message=safeguard_error,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    result = await asyncio.to_thread(
        get_runtime().dispatch_next,
        state,
        session.latest_page_context,
    )
    await _apply_dispatch(send_json, run_manager, session, state, result)


async def _apply_dispatch(
    send_json: SendJson,
    run_manager: RunManager,
    session,
    state: RunState,
    result: DispatchResult,
) -> None:
    if result.kind == "needs_clarification":
        run_manager.wait_for_user(session)
        await send_json(
            RunNeedsClarificationMessage(
                type="RUN_NEEDS_CLARIFICATION",
                runId=session.run_id,
                message=result.message,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    if result.kind == "complete":
        run_manager.complete_run(session, result.message)
        await send_json(
            RunCompleteMessage(
                type="RUN_COMPLETE",
                runId=session.run_id,
                message=result.message,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        _v2_run_ids.discard(session.run_id)
        return

    if result.kind == "handoff":
        run_manager.wait_for_user(session)
        await send_json(
            RunWaitingForUserMessage(
                type="RUN_WAITING_FOR_USER",
                runId=session.run_id,
                message=result.message,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    if result.kind == "error":
        run_manager.fail_run(session, result.message)
        await send_json(
            RunErrorMessage(
                type="RUN_ERROR",
                runId=session.run_id,
                message=result.message,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        _v2_run_ids.discard(session.run_id)
        return

    if result.kind == "continue" and result.steps:
        run_manager.increment_turn(session)
        run_manager.mark_steps_dispatched(session, result.steps, None, None)
        payload = NextActionMessage(
            type="NEXT_ACTION",
            runId=session.run_id,
            steps=result.steps,
            turn=session.planning_turn,
            actionSummary=result.action_summary,
            screenshotDataUrl=(
                session.latest_page_context.screenshot_data_url
                if session.latest_page_context
                and session.latest_page_context.screenshot_data_url
                else None
            ),
        ).model_dump(by_alias=True, exclude_none=True)
        payload["runtimePhase"] = result.runtime_phase
        if result.chat_message:
            payload["chatMessage"] = result.chat_message
        await send_json(payload)
        return

    await dispatch_next(send_json, run_manager, session)
