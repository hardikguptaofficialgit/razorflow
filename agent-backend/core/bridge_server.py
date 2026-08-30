"""WebSocket bridge server for iterative RazorFlow runs."""

from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from core.connection_registry import (
    clear_agent_config,
    get_agent_config,
    set_agent_config,
)
from core.llm_run_config import (
    SUPPORTED_PLANNER_PROVIDERS,
    agent_config_from_wire,
    agent_config_status_payload,
)

from core.browser_observer import cleanup_observer_session
from core.browser_use_runner import BrowserUseRunController
from core.execution_log import log_execute, log_run, log_state
from core.goal_verifier import approve_completion, record_verified_action
from core.planner import PlannerConfigurationError, plan_next_chunk
from core.search_query import sanitize_plan_steps
from core.task_interpretation import interpret_task
from core.protocol import (
    ActionResultMessage,
    AgentConfigStatusMessage,
    CancelRunMessage,
    ConfigureAgentMessage,
    ConfirmPaymentLinkMessage,
    DeclinePaymentLinkMessage,
    ExtensionMessage,
    ExecutorModeMessage,
    NextActionMessage,
    PaymentLinkConfirmationMessage,
    PaymentLinkFailedMessage,
    PaymentLinkReadyMessage,
    PaymentLinkProposalPayload,
    ReadyForPaymentLinkStep,
    ResumeRunMessage,
    RunCompleteMessage,
    RunNeedsClarificationMessage,
    RunErrorMessage,
    RunWaitingForUserMessage,
    StartRunMessage,
    WaitForUserStep,
)
from core.run_manager import RunManager
from policy.payment_executor import execute_payment_link_creation
from policy.payment_policy import PaymentLinkProposal
from policy.audit_router import router as audit_router
from policy.payment_router import router as payment_router
from utils.config import (
    get_browser_use_cdp_url,
    get_gemini_model,
    get_groq_api_key,
    get_groq_model,
    get_llamacpp_model,
    get_llm_provider,
    get_openrouter_model,
    get_planner_llm_fallback_chain,
    get_planner_llm_model,
    get_planner_llm_provider,
    get_planner_strategy,
    get_vercel_ai_gateway_model,
    is_browser_use_enabled,
    is_browser_use_executor_enabled,
    is_agent_runtime_v2_enabled,
    is_browser_llm_ready,
    is_gemini_configured,
    is_groq_configured,
    is_openrouter_configured,
    is_planner_llm_ready,
    is_razorpay_configured,
    is_vercel_ai_gateway_configured,
    log_config_status,
)
from voice.intent_classifier import router as voice_router

logger = logging.getLogger(__name__)

app = FastAPI(title="RazorFlow Agent Bridge", version="0.2.0")


def _cors_origins() -> list[str]:
    origins = [
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(","):
        normalized = origin.strip().rstrip("/")
        if normalized and normalized not in origins:
            origins.append(normalized)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(voice_router)
app.include_router(audit_router)
app.include_router(payment_router)


class TestLlmRequest(BaseModel):
    provider: str = Field(min_length=1)
    api_key: str = Field(min_length=1, alias="apiKey")
    model: str = Field(min_length=1)
    temperature: float = Field(default=0.05, ge=0.0, le=1.5)

    model_config = {"populate_by_name": True}


def _user_handoff_message(session) -> str:
    page = session.latest_page_context
    url = (page.url if page else "").lower()
    title = (page.title if page else "").lower()
    blob = f"{url} {title}"
    if "auth=login" in url or any(
        token in blob for token in ("sign in to checkout", "sign in to continue")
    ):
        return "Please sign in to complete your order, then tap Resume."
    if any(token in blob for token in ("login", "sign-in", "signin", "log-in")):
        return "Please log in to continue, then tap Resume."
    if any(token in blob for token in ("otp", "captcha", "verify", "2fa", "two-factor")):
        return "Please complete verification, then tap Resume."
    if "/search" in url and session.consecutive_failures >= 2:
        return (
            "I couldn't complete the next step automatically. "
            "Adjust the page if needed, then tap Resume."
        )
    return "Please complete the required step, then tap Resume when ready."
run_manager = RunManager()
browser_use_controller = BrowserUseRunController(run_manager)
extension_message_adapter = TypeAdapter(ExtensionMessage)


@app.on_event("startup")
async def on_startup() -> None:
    log_config_status()


@app.get("/health")
def health() -> dict[str, Any]:
    runtime_v2 = is_agent_runtime_v2_enabled()
    executor = is_browser_use_executor_enabled() and not runtime_v2
    provider = get_llm_provider()
    if provider == "gemini":
        model_name = get_gemini_model() if is_gemini_configured() else ""
    elif provider == "llamacpp":
        model_name = get_llamacpp_model()
    elif provider == "openrouter":
        model_name = get_openrouter_model() if is_openrouter_configured() else ""
    elif is_groq_configured():
        model_name = get_groq_model()
    else:
        model_name = ""

    planner_provider = get_planner_llm_provider()
    planner_chain = list(get_planner_llm_fallback_chain())
    planner_model = ""
    for candidate in planner_chain:
        if candidate == "openrouter" and is_openrouter_configured():
            planner_model = get_planner_llm_model(candidate)
            break
        if candidate == "groq" and is_groq_configured():
            planner_model = get_planner_llm_model(candidate)
            break
        if candidate == "vercel_ai_gateway" and is_vercel_ai_gateway_configured():
            planner_model = get_vercel_ai_gateway_model()
            break
        if candidate == "gemini" and is_gemini_configured():
            planner_model = get_planner_llm_model(candidate)
            break

    return {
        "status": "ok",
        "llmProvider": provider,
        "llmModel": model_name,
        "groqConfigured": is_groq_configured(),
        "razorpayConfigured": is_razorpay_configured(),
        "browserUseEnabled": is_browser_use_enabled(),
        "browserUseExecutorEnabled": executor,
        "executorMode": "browser_use" if executor else "extension_dom",
        "agentRuntimeV2": runtime_v2,
        "plannerMode": planner_provider if is_planner_llm_ready() else "unconfigured",
        "plannerLlmProvider": planner_provider,
        "plannerLlmModel": planner_model,
        "plannerLlmFallbacks": planner_chain[1:],
        "plannerStrategy": get_planner_strategy(),
        "browserUseLlmProvider": provider,
        "browserUseLlmReady": is_browser_llm_ready(),
        "groqModel": get_groq_model(),
        "cdpAttached": bool(get_browser_use_cdp_url()),
        "paidBrowserUseLlm": False,
        "byokSupported": True,
        "supportedPlannerProviders": list(SUPPORTED_PLANNER_PROVIDERS),
    }


@app.post("/api/agent/llm/test")
def test_llm_connection(body: TestLlmRequest) -> dict[str, object]:
    from core.planner_llm import test_planner_connection

    provider = body.provider.strip().lower()
    if provider not in SUPPORTED_PLANNER_PROVIDERS:
        return {"ok": False, "error": f"Unsupported provider: {provider}"}
    return test_planner_connection(
        provider=provider,
        api_key=body.api_key.strip(),
        model=body.model.strip(),
        temperature=body.temperature,
    )


async def _send_json(websocket: WebSocket, payload: Any) -> None:
    await websocket.send_json(payload)


async def _terminate_run(session) -> None:
    if not is_agent_runtime_v2_enabled() and is_browser_use_executor_enabled():
        await browser_use_controller.cancel_run(session.run_id, cleanup=True)
    await cleanup_observer_session(session.run_id)


def _resolve_start_url(message: StartRunMessage | ResumeRunMessage) -> str | None:
    if isinstance(message, StartRunMessage) and message.url:
        return message.url
    if message.page_context and message.page_context.url:
        return message.page_context.url
    return None


async def _notify_executor_mode(websocket: WebSocket, run_id: str) -> None:
    mode = (
        "extension_dom"
        if is_agent_runtime_v2_enabled()
        else "browser_use" if is_browser_use_executor_enabled() else "extension_dom"
    )
    await _send_json(
        websocket,
        ExecutorModeMessage(
            type="EXECUTOR_MODE",
            runId=run_id,
            mode=mode,
        ).model_dump(by_alias=True, exclude_none=True),
    )


def _summarize_steps(steps: list) -> str:
    if not steps:
        return "Planning…"
    first = steps[0]
    action = getattr(first, "action", "")
    if action == "navigate_url":
        return "Opening search results…"
    if action == "click_element":
        match = getattr(first, "match_text", None) or "element"
        normalized = match.lower()
        if "add to cart" in normalized or "buy now" in normalized:
            return "Adding to cart…"
        if normalized in {"cart", "go to cart", "view cart", "bag", "basket"}:
            return "Opening cart…"
        if "cart" in normalized and "add" not in normalized:
            return "Opening cart…"
        return f"Clicking {match}…"
    if action == "type_in_element":
        return f"Searching for {getattr(first, 'text', 'products')}…"
    if action == "wait_for_user":
        return "Waiting for you…"
    if action == "ready_for_payment_link":
        return "Preparing payment…"
    return "Working…"


async def _send_payment_confirmation(
    websocket: WebSocket,
    session,
    proposal: PaymentLinkProposalPayload,
) -> None:
    run_manager.request_payment_confirmation(session, proposal)
    await _send_json(
        websocket,
        PaymentLinkConfirmationMessage(
            type="PAYMENT_LINK_CONFIRMATION_REQUIRED",
            runId=session.run_id,
            proposal=proposal,
            message="Review and confirm payment link creation.",
        ).model_dump(by_alias=True, exclude_none=True),
    )


def _proposal_from_step(step: ReadyForPaymentLinkStep) -> PaymentLinkProposalPayload:
    return PaymentLinkProposalPayload(
        title=step.title,
        description=step.description,
        amountPaise=step.amount_paise,
        currency=step.currency,
    )


async def _send_needs_clarification(websocket: WebSocket, session) -> None:
    message = (
        session.needs_clarification_reason
        or "Please clarify what you want to search, add, or buy."
    )
    run_manager.wait_for_user(session)
    await _send_json(
        websocket,
        RunNeedsClarificationMessage(
            type="RUN_NEEDS_CLARIFICATION",
            runId=session.run_id,
            message=message,
        ).model_dump(by_alias=True, exclude_none=True),
    )


async def _try_complete_run(websocket: WebSocket, session, *, source: str) -> bool:
    interpretation = interpret_task(session.task)
    if not approve_completion(session, interpretation.intent, source=source):
        log_state(
            session.run_id,
            "completion_rejected",
            source=source,
            goal=interpretation.intent.goal,
        )
        return False

    run_manager.complete_run(session, "Task completed.")
    await _send_json(
        websocket,
        RunCompleteMessage(
            type="RUN_COMPLETE",
            runId=session.run_id,
            message="Task completed.",
        ).model_dump(by_alias=True, exclude_none=True),
    )
    await _terminate_run(session)
    return True


async def _dispatch_next_chunk(websocket: WebSocket, session) -> None:
    if is_agent_runtime_v2_enabled():
        from agent_runtime.bridge.adapter import dispatch_next

        await dispatch_next(
            lambda payload: _send_json(websocket, payload),
            run_manager,
            session,
        )
        return

    safeguard_error = run_manager.check_safeguards(session)
    if safeguard_error:
        if "page change" in safeguard_error.lower() or "consecutive" in safeguard_error.lower():
            run_manager.wait_for_user(session)
            await _send_json(
                websocket,
                RunWaitingForUserMessage(
                    type="RUN_WAITING_FOR_USER",
                    runId=session.run_id,
                    message=_user_handoff_message(session),
                ).model_dump(by_alias=True, exclude_none=True),
            )
            return

        run_manager.fail_run(session, safeguard_error)
        await _send_json(
            websocket,
            RunErrorMessage(
                type="RUN_ERROR",
                runId=session.run_id,
                message=safeguard_error,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        await _terminate_run(session)
        return

    try:
        chunk = await plan_next_chunk(session)
    except PlannerConfigurationError as error:
        run_manager.fail_run(session, str(error))
        await _send_json(
            websocket,
            RunErrorMessage(
                type="RUN_ERROR",
                runId=session.run_id,
                message=str(error),
            ).model_dump(by_alias=True, exclude_none=True),
        )
        await _terminate_run(session)
        return
    except (ValueError, ValidationError) as error:
        run_manager.fail_run(session, str(error))
        await _send_json(
            websocket,
            RunErrorMessage(
                type="RUN_ERROR",
                runId=session.run_id,
                message=str(error),
            ).model_dump(by_alias=True, exclude_none=True),
        )
        await _terminate_run(session)
        return
    except Exception as error:
        logger.exception("Planning failed for runId=%s", session.run_id)
        message = f"Planning failed: {error}"
        run_manager.fail_run(session, message)
        await _send_json(
            websocket,
            RunErrorMessage(
                type="RUN_ERROR",
                runId=session.run_id,
                message=message,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        await _terminate_run(session)
        return

    if chunk.terminal == "needs_clarification":
        await _send_needs_clarification(websocket, session)
        return

    if chunk.terminal == "system_complete":
        if await _try_complete_run(websocket, session, source="dispatch_system_complete"):
            return
        run_manager.wait_for_user(session)
        await _send_json(
            websocket,
            RunWaitingForUserMessage(
                type="RUN_WAITING_FOR_USER",
                runId=session.run_id,
                message="Could not verify task completion. Adjust the page and resume.",
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    if chunk.terminal == "complete" and not chunk.steps:
        log_state(session.run_id, "ignored_llm_complete_without_steps")
        session.complete_replan_attempts += 1
        if session.complete_replan_attempts > 2:
            run_manager.wait_for_user(session)
            await _send_json(
                websocket,
                RunWaitingForUserMessage(
                    type="RUN_WAITING_FOR_USER",
                    runId=session.run_id,
                    message=_user_handoff_message(session),
                ).model_dump(by_alias=True, exclude_none=True),
            )
            return
        session.planner_nudge = (
            "Goal not verified yet. Return the next concrete browser action — "
            "do not use terminal=complete."
        )
        await _dispatch_next_chunk(websocket, session)
        return

    if chunk.terminal == "ready_for_payment_link":
        proposal = chunk.payment_proposal
        if proposal is None:
            for step in chunk.steps:
                if isinstance(step, ReadyForPaymentLinkStep):
                    proposal = _proposal_from_step(step)
                    break

        if proposal is None:
            run_manager.wait_for_user(session)
            await _send_json(
                websocket,
                RunWaitingForUserMessage(
                    type="RUN_WAITING_FOR_USER",
                    runId=session.run_id,
                    message="Payment details missing. Please confirm checkout total.",
                ).model_dump(by_alias=True, exclude_none=True),
            )
            return

        run_manager.increment_turn(session)
        run_manager.mark_steps_dispatched(
            session,
            chunk.steps,
            chunk.terminal,
            proposal,
        )
        await _send_payment_confirmation(websocket, session, proposal)
        return

    if not chunk.steps:
        run_manager.wait_for_user(session)
        await _send_json(
            websocket,
            RunWaitingForUserMessage(
                type="RUN_WAITING_FOR_USER",
                runId=session.run_id,
                message="Planner requested user input.",
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    run_manager.increment_turn(session)
    steps = sanitize_plan_steps(chunk.steps, session.task)
    run_manager.mark_steps_dispatched(
        session,
        steps,
        chunk.terminal,
        chunk.payment_proposal,
    )

    await _send_json(
        websocket,
        NextActionMessage(
            type="NEXT_ACTION",
            runId=session.run_id,
            steps=steps,
            turn=session.planning_turn,
            actionSummary=_summarize_steps(steps),
            screenshotDataUrl=(
                session.latest_page_context.screenshot_data_url
                if session.latest_page_context
                and session.latest_page_context.screenshot_data_url
                else None
            ),
        ).model_dump(by_alias=True, exclude_none=True),
    )


async def _finish_after_action_result(websocket: WebSocket, session) -> None:
    if session.pending_terminal == "ready_for_payment_link":
        proposal = session.pending_payment_proposal
        if proposal is not None:
            await _send_payment_confirmation(websocket, session, proposal)
            return

    if session.pending_terminal == "wait_for_user":
        run_manager.wait_for_user(session)
        await _send_json(
            websocket,
            RunWaitingForUserMessage(
                type="RUN_WAITING_FOR_USER",
                runId=session.run_id,
                message=_user_handoff_message(session),
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    await _dispatch_next_chunk(websocket, session)


async def _handle_configure_agent(
    websocket: WebSocket,
    message: ConfigureAgentMessage,
    *,
    connection_id: str,
) -> None:
    try:
        config = agent_config_from_wire(message.model_dump(by_alias=True))
    except ValueError as error:
        await _send_json(
            websocket,
            AgentConfigStatusMessage(
                type="AGENT_CONFIG_STATUS",
                mode="server_default",
                useByok=False,
                maxAgentSteps=40,
                shoppingSkillEnabled=True,
                message=str(error),
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    set_agent_config(connection_id, config)
    status = agent_config_status_payload(config)
    await _send_json(
        websocket,
        AgentConfigStatusMessage(
            type="AGENT_CONFIG_STATUS",
            mode=status["mode"],  # type: ignore[arg-type]
            useByok=status["useByok"],
            provider=status.get("provider"),
            model=status.get("model"),
            temperature=status.get("temperature"),
            maxAgentSteps=status["maxAgentSteps"],
            shoppingSkillEnabled=status["shoppingSkillEnabled"],
            message="Agent configuration saved.",
        ).model_dump(by_alias=True, exclude_none=True),
    )


async def _handle_start_run(
    websocket: WebSocket,
    message: StartRunMessage,
    *,
    connection_id: str,
) -> None:
    session = run_manager.start_run(
        message.run_id,
        message.task,
        message.page_context,
        connection_id=connection_id,
    )
    log_run(session.run_id, "start_run", task=message.task)
    logger.info("START_RUN runId=%s task=%s", message.run_id, message.task)

    await _notify_executor_mode(websocket, message.run_id)

    if is_agent_runtime_v2_enabled():
        from agent_runtime.bridge.adapter import handle_start_run as v2_start_run

        await v2_start_run(
            lambda payload: _send_json(websocket, payload),
            run_manager,
            session,
            message,
            agent_config=get_agent_config(connection_id),
        )
        return

    if session.needs_clarification_reason:
        await _send_needs_clarification(websocket, session)
        return

    if not is_agent_runtime_v2_enabled() and is_browser_use_executor_enabled():
        await browser_use_controller.start_run(
            lambda payload: _send_json(websocket, payload),
            session,
            _resolve_start_url(message),
        )
        return

    await _dispatch_next_chunk(websocket, session)


async def _handle_action_result(
    websocket: WebSocket,
    message: ActionResultMessage,
) -> None:
    if not is_agent_runtime_v2_enabled() and is_browser_use_executor_enabled():
        return

    if is_agent_runtime_v2_enabled():
        from agent_runtime.bridge.adapter import handle_action_result

        await handle_action_result(
            lambda payload: _send_json(websocket, payload),
            run_manager,
            message,
        )
        return

    session = run_manager.get_run(message.run_id)
    if session is None or session.status == "cancelled":
        return

    run_manager.record_action_result(
        session,
        message.step,
        message.success,
        message.error,
        message.page_context,
        message.verified,
    )
    interpretation = interpret_task(session.task)
    log_execute(
        session.run_id,
        session.action_step,
        "action_result",
        success=message.success,
        verified=message.verified,
        error=message.error,
    )
    record_verified_action(
        session,
        interpretation.intent,
        success=message.success,
        verified=message.verified,
    )

    if isinstance(message.step, WaitForUserStep) and message.success:
        run_manager.wait_for_user(session)
        await _send_json(
            websocket,
            RunWaitingForUserMessage(
                type="RUN_WAITING_FOR_USER",
                runId=session.run_id,
                message=_user_handoff_message(session),
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    if isinstance(message.step, ReadyForPaymentLinkStep) and message.success:
        proposal = _proposal_from_step(message.step)
        run_manager.mark_steps_dispatched(
            session,
            [message.step],
            "ready_for_payment_link",
            proposal,
        )
        await _send_payment_confirmation(websocket, session, proposal)
        return

    if not message.success:
        error_text = (message.error or "").lower()
        connection_lost = (
            "browser connection lost" in error_text
            or "content script unavailable" in error_text
            or (
                message.page_context is None
                and ("connection" in error_text or "reconnect" in error_text)
            )
        )
        if connection_lost:
            run_manager.wait_for_user(session)
            await _send_json(
                websocket,
                RunWaitingForUserMessage(
                    type="RUN_WAITING_FOR_USER",
                    runId=session.run_id,
                    message=message.error
                    or "Browser connection lost. Refresh the page, then resume.",
                ).model_dump(by_alias=True, exclude_none=True),
            )
            return

        safeguard_error = run_manager.check_safeguards(session)
        if safeguard_error:
            run_manager.fail_run(session, safeguard_error)
            await _send_json(
                websocket,
                RunErrorMessage(
                    type="RUN_ERROR",
                    runId=session.run_id,
                    message=safeguard_error,
                ).model_dump(by_alias=True, exclude_none=True),
            )
            await _terminate_run(session)
            return

    if message.success:
        if message.verified is False:
            session.planner_nudge = (
                "The last action reported success but verification failed. "
                "Re-observe the page and choose a different approach."
            )
        elif await _try_complete_run(websocket, session, source="action_result"):
            return

    await _finish_after_action_result(websocket, session)


async def _handle_resume_run(
    websocket: WebSocket,
    message: ResumeRunMessage,
) -> None:
    session = run_manager.resume_run(message.run_id, message.page_context)
    if session is None:
        await _send_json(
            websocket,
            RunErrorMessage(
                type="RUN_ERROR",
                runId=message.run_id,
                message="Run is not waiting for user.",
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    logger.info("RESUME_RUN runId=%s", message.run_id)

    if not is_agent_runtime_v2_enabled() and is_browser_use_executor_enabled():
        run_manager.clear_payment_proposal(session)
        await browser_use_controller.resume_run(
            lambda payload: _send_json(websocket, payload),
            session,
            _resolve_start_url(message),
        )
        return

    if is_agent_runtime_v2_enabled():
        from agent_runtime.bridge.adapter import handle_resume_run

        ok = await handle_resume_run(
            lambda payload: _send_json(websocket, payload),
            run_manager,
            message.run_id,
            message.page_context,
        )
        if not ok:
            await _send_json(
                websocket,
                RunErrorMessage(
                    type="RUN_ERROR",
                    runId=message.run_id,
                    message="Run is not waiting for user.",
                ).model_dump(by_alias=True, exclude_none=True),
            )
        return

    await _dispatch_next_chunk(websocket, session)


async def _handle_confirm_payment_link(
    websocket: WebSocket,
    message: ConfirmPaymentLinkMessage,
) -> None:
    session = run_manager.get_run(message.run_id)
    if session is None or session.status == "cancelled":
        return

    proposal_payload = session.pending_payment_proposal
    if proposal_payload is None:
        await _send_json(
            websocket,
            PaymentLinkFailedMessage(
                type="PAYMENT_LINK_FAILED",
                runId=message.run_id,
                message="No pending payment proposal for this run.",
                recoverable=True,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    attempt = run_manager.increment_payment_attempt(session)
    result = await execute_payment_link_creation(
        run_id=session.run_id,
        proposal=PaymentLinkProposal(
            title=proposal_payload.title,
            description=proposal_payload.description,
            amount_paise=proposal_payload.amount_paise,
            currency=proposal_payload.currency,
        ),
        attempt=attempt,
    )

    if not result.success or result.payment_link is None:
        session.status = "waiting_for_user"
        session.waiting_for_user = True
        await _send_json(
            websocket,
            PaymentLinkFailedMessage(
                type="PAYMENT_LINK_FAILED",
                runId=session.run_id,
                message=result.message,
                recoverable=True,
            ).model_dump(by_alias=True, exclude_none=True),
        )
        return

    payment_link = result.payment_link
    run_manager.clear_payment_proposal(session)
    session.status = "waiting_for_user"
    session.waiting_for_user = True

    await _send_json(
        websocket,
        PaymentLinkReadyMessage(
            type="PAYMENT_LINK_READY",
            runId=session.run_id,
            paymentLinkUrl=payment_link.payment_link_url,
            amountPaise=payment_link.amount_paise,
            currency=payment_link.currency,
            description=payment_link.description,
            referenceId=payment_link.reference_id,
            message="Payment link ready.",
        ).model_dump(by_alias=True, exclude_none=True),
    )


async def _handle_decline_payment_link(
    websocket: WebSocket,
    message: DeclinePaymentLinkMessage,
) -> None:
    session = run_manager.get_run(message.run_id)
    if session is None or session.status == "cancelled":
        return

    run_manager.clear_payment_proposal(session)
    run_manager.wait_for_user(session)
    await _send_json(
        websocket,
        RunWaitingForUserMessage(
            type="RUN_WAITING_FOR_USER",
            runId=session.run_id,
            message="Payment link creation declined. Adjust cart or resume when ready.",
        ).model_dump(by_alias=True, exclude_none=True),
    )


async def _handle_cancel_run(message: CancelRunMessage) -> None:
    if is_agent_runtime_v2_enabled():
        from agent_runtime.bridge.adapter import handle_cancel

        await handle_cancel(message.run_id)

    if not is_agent_runtime_v2_enabled() and is_browser_use_executor_enabled():
        await browser_use_controller.cancel_run(message.run_id, cleanup=True)

    session = run_manager.cancel_run(message.run_id)
    if session is not None:
        logger.info("CANCEL_RUN runId=%s", message.run_id)
        await cleanup_observer_session(message.run_id)


@app.websocket("/ws")
async def websocket_bridge(websocket: WebSocket) -> None:
    await websocket.accept()
    connection_id = uuid.uuid4().hex
    logger.info("Agent client connected over WebSocket connectionId=%s", connection_id)

    try:
        while True:
            payload = await websocket.receive_json()

            try:
                message = extension_message_adapter.validate_python(payload)
            except ValidationError as exc:
                logger.warning("Invalid extension message: %s (%s)", payload.get("type"), exc)
                continue

            if isinstance(message, StartRunMessage):
                await _handle_start_run(websocket, message, connection_id=connection_id)
            elif isinstance(message, ActionResultMessage):
                await _handle_action_result(websocket, message)
            elif isinstance(message, ResumeRunMessage):
                await _handle_resume_run(websocket, message)
            elif isinstance(message, CancelRunMessage):
                await _handle_cancel_run(message)
            elif isinstance(message, ConfirmPaymentLinkMessage):
                await _handle_confirm_payment_link(websocket, message)
            elif isinstance(message, DeclinePaymentLinkMessage):
                await _handle_decline_payment_link(websocket, message)
            elif isinstance(message, ConfigureAgentMessage):
                await _handle_configure_agent(
                    websocket,
                    message,
                    connection_id=connection_id,
                )
    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected connectionId=%s — cancelling its active runs",
            connection_id,
        )
        clear_agent_config(connection_id)
        if not is_agent_runtime_v2_enabled() and is_browser_use_executor_enabled():
            await browser_use_controller.cancel_all_runs()
        for run_id in run_manager.cancel_active_runs(connection_id):
            logger.info("Cancelled run on disconnect runId=%s", run_id)
    except Exception:
        logger.exception("WebSocket bridge error")
        await websocket.close()
