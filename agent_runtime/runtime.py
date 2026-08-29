"""Agent Runtime V2 — central execution loop."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from core.protocol import ActionStep, PageContext

from agent_runtime.chat.messages import completion_message, planning_ack
from agent_runtime.events.trace import emit_trace
from agent_runtime.executor.actions import AgentAction
from agent_runtime.executor.translate import translate_action
from agent_runtime.memory.sync import sync_memory_from_observation
from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.observation.browser_state import BrowserPage, observe_from_page_context
from agent_runtime.planner.llm_provider import LLMProvider, get_default_llm_provider
from agent_runtime.planner.planner import LLMPlanner
from agent_runtime.planner.recovery import empty_plan_nudge
from agent_runtime.policy.goal_guard import (
    action_advances_goal,
    filter_non_advancing_actions,
    goal_quota_met,
)
from agent_runtime.policy.search_state import (
    entity_visible_on_page,
    find_goal_ready,
    needs_search,
    on_search_page,
    search_entity,
)
from agent_runtime.recovery.loop_detector import (
    loop_nudge,
    record_action_hash,
    record_observation,
)
from agent_runtime.recovery.stuck import detect_stuck, record_action
from agent_runtime.target.resolve import refresh_action_target
from agent_runtime.state.phase import RuntimePhase
from agent_runtime.state.run_state import RunState
from agent_runtime.policy.action_gate import (
    _is_checkout_action,
    classify_action,
    filter_forbidden_actions,
    handoff_allowed,
)
from agent_runtime.task.parser import ParsedTask, parse_task_with_spec
from agent_runtime.task.phase_progression import try_advance_phase
from agent_runtime.task.spec import GoalPhase
from agent_runtime.verifier.action_result import apply_verified_progress, verify_action_result
from agent_runtime.verifier.checkout_flow import checkout_requires_handoff, is_checkout_flow_page
from agent_runtime.verifier.goal import approve_completion, is_goal_satisfied, update_milestones
from agent_runtime.planner.recovery import empty_plan_nudge


TerminalKind = Literal[
    "continue",
    "complete",
    "handoff",
    "needs_clarification",
    "error",
    "payment",
]


@dataclass
class DispatchResult:
    kind: TerminalKind
    steps: list[ActionStep]
    message: str = ""
    runtime_phase: str = "acting"
    action_summary: str = ""
    chat_message: str = ""


class AgentRuntime:
    def __init__(self, llm: LLMProvider | None = None) -> None:
        self._llm = llm or get_default_llm_provider()
        self._planner = LLMPlanner(self._llm)
        self._runs: dict[str, RunState] = {}

    def start_run(
        self,
        run_id: str,
        task: str,
        page_context: PageContext | None,
        *,
        connection_id: str = "",
    ) -> RunState:
        parsed, spec = parse_task_with_spec(task)
        memory = TaskMemory(
            goal=parsed.goal,
            items_target=parsed.item_count,
            remaining_work=_initial_remaining(parsed),
            remaining_items=list(spec.remaining_items),
        )
        if parsed.budget_inr is not None:
            memory.constraints.append(f"budget_inr<={parsed.budget_inr:.0f}")
        if parsed.prefer_best:
            memory.constraints.append("prefer_best_match")

        state = RunState(
            run_id=run_id,
            task=task,
            parsed_task=parsed,
            task_spec=spec,
            memory=memory,
            connection_id=connection_id,
            current_phase=spec.effective_phases()[0],
        )
        if not parsed.actionable:
            state.phase = RuntimePhase.NEEDS_CLARIFICATION
            state.needs_clarification_reason = parsed.clarification_reason
            self._runs[run_id] = state
            emit_trace(run_id, "TASK_PARSED", step=0, actionable=False)
            return state

        page = observe_from_page_context(page_context)
        state.memory.current_page = page
        sync_memory_from_observation(state, page)
        update_milestones(state, page)
        self._runs[run_id] = state
        emit_trace(run_id, "RUN_STARTED", step=0, goal=parsed.goal)
        return state

    def get_run(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def resume_run(self, run_id: str, page_context: PageContext | None) -> RunState | None:
        state = self._runs.get(run_id)
        if state is None:
            return None
        state.waiting_for_user = False
        state.phase = RuntimePhase.OBSERVING
        page = observe_from_page_context(page_context)
        state.memory.current_page = page
        emit_trace(run_id, "RESUME", step=state.step)
        return state

    def cancel_run(self, run_id: str) -> None:
        state = self._runs.pop(run_id, None)
        if state:
            state.phase = RuntimePhase.FAILED
            emit_trace(run_id, "CANCELLED", step=state.step)

    def observe(self, state: RunState, page_context: PageContext | None) -> BrowserPage | None:
        state.phase = RuntimePhase.OBSERVING
        page = observe_from_page_context(page_context)
        state.memory.current_page = page
        update_milestones(state, page)
        emit_trace(state.run_id, "OBSERVATION", step=state.step, url=page.url if page else "")
        return page

    def dispatch_next(
        self,
        state: RunState,
        page_context: PageContext | None,
    ) -> DispatchResult:
        if state.phase == RuntimePhase.NEEDS_CLARIFICATION:
            return DispatchResult(
                kind="needs_clarification",
                steps=[],
                message=state.needs_clarification_reason,
            )

        page = self.observe(state, page_context)
        try_advance_phase(state, page)

        if approve_completion(state, page, source="pre_plan"):
            return _completion_or_handoff(state, page, source="pre_plan")

        if find_goal_ready(state, page) and approve_completion(state, page, source="find_ready"):
            return _completion_or_handoff(state, page, source="find_ready")

        spec = state.task_spec
        if (
            spec
            and spec.intent == "add_to_cart"
            and page
            and not on_search_page(page)
            and search_entity(state)
            and not entity_visible_on_page(page, search_entity(state))
            and not state.planner_nudge
        ):
            state.planner_nudge = (
                f"Search for '{search_entity(state)}' using the search bar before adding to cart."
            )

        if needs_search(state, page) and not state.planner_nudge:
            query = search_entity(state) or "the requested product"
            state.planner_nudge = (
                f"Not on search results yet — use search/type for '{query}' in the search bar. "
                "Do NOT scroll the homepage product grid."
            )

        stuck = detect_stuck(state)
        if stuck:
            state.phase = RuntimePhase.RECOVERING
            state.planner_nudge = stuck
            emit_trace(state.run_id, "RECOVERY", step=state.step, reason=stuck)

        loop = loop_nudge(state)
        if loop and not stuck:
            state.phase = RuntimePhase.RECOVERING
            state.planner_nudge = loop
            emit_trace(state.run_id, "LOOP_DETECTED", step=state.step, reason=loop)

        if state.consecutive_failures >= 8:
            state.phase = RuntimePhase.FAILED
            return DispatchResult(
                kind="error",
                steps=[],
                message=(
                    "Could not make verified progress after several attempts. "
                    "Try rephrasing the task or adjusting the page."
                ),
            )

        if state.consecutive_failures >= 2:
            state.planner_nudge = (
                state.planner_nudge
                or f"{state.consecutive_failures} consecutive failures. "
                "Re-observe the page and choose a different strategy."
            )

        if state.pending_actions and state.pending_action_index < len(state.pending_actions):
            return self._dispatch_pending(state)

        state.phase = RuntimePhase.PLANNING
        started = time.perf_counter()
        try:
            screenshot = page_context.screenshot_data_url if page_context else None
            plan = self._planner.plan(state, page, screenshot_data_url=screenshot)
        except Exception as error:
            from pydantic import ValidationError

            recoverable = isinstance(error, (ValueError, ValidationError))
            if recoverable and state.planner_parse_retries < 2:
                state.planner_parse_retries += 1
                state.phase = RuntimePhase.RECOVERING
                state.planner_nudge = (
                    "Planner output was invalid JSON or schema. "
                    "Return valid JSON only. target.role must be one of: "
                    "search, input, button, link."
                )
                emit_trace(
                    state.run_id,
                    "PLAN_PARSE_RECOVERY",
                    step=state.step,
                    error=str(error)[:200],
                )
                return self.dispatch_next(state, page_context)
            state.phase = RuntimePhase.FAILED
            return DispatchResult(kind="error", steps=[], message=str(error))

        emit_trace(
            state.run_id,
            "PLAN",
            step=state.step,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

        if plan.propose_finish:
            if approve_completion(state, page, source="llm_proposal"):
                return _completion_or_handoff(state, page, source="llm_proposal")
            state.planner_nudge = (
                "Goal is not verified yet. Do not propose finish. "
                "Return 1-3 concrete browser actions."
            )
            plan = self._planner.plan(state, page, screenshot_data_url=screenshot)

        if plan.propose_handoff:
            if handoff_allowed(page, plan.handoff_reason or ""):
                state.phase = RuntimePhase.HANDOFF
                state.waiting_for_user = True
                reason = plan.handoff_reason or "User input required to continue."
                return DispatchResult(
                    kind="handoff",
                    steps=[],
                    message=reason,
                    runtime_phase="handoff",
                )
            state.planner_nudge = (
                "Handoff is not allowed for this situation. "
                "Do not propose handoff for uncertainty or failed clicks. "
                "Re-observe and return 1-3 concrete browser actions."
            )
            plan = self._planner.plan(state, page, screenshot_data_url=screenshot)

        spec = state.task_spec
        blocked: list[str] = []
        if spec and plan.actions:
            allowed, blocked = filter_forbidden_actions(
                spec, plan.actions, current_phase=state.current_phase, state=state
            )
            allowed, guard_blocked = filter_non_advancing_actions(state, allowed)
            blocked = blocked + guard_blocked
            if blocked:
                state.metrics["blocked_action_count"] = int(
                    state.metrics.get("blocked_action_count", 0)
                ) + len(blocked)
                if state.current_phase == "checkout":
                    state.planner_nudge = (
                        "CURRENT_PHASE=checkout. Cart is ready. "
                        "Click a checkout-capable control from observation — "
                        "do NOT add items or use header Sign in. "
                        "Blocked: " + "; ".join(blocked)
                    )
                else:
                    state.planner_nudge = (
                        "These actions violate the user goal and were blocked: "
                        + "; ".join(blocked)
                        + ". Choose actions that match the declared intent only."
                    )
                emit_trace(
                    state.run_id,
                    "ACTION_BLOCKED",
                    step=state.step,
                    blocked=blocked,
                )
            plan.actions = allowed

        if not plan.actions:
            if is_goal_satisfied(state, page):
                if approve_completion(state, page, source="empty_plan_satisfied"):
                    return _completion_or_handoff(state, page, source="empty_plan_satisfied")
            state.empty_plan_retries += 1
            state.metrics["empty_plan_count"] = int(
                state.metrics.get("empty_plan_count", 0)
            ) + 1
            if state.empty_plan_retries >= 3:
                state.phase = RuntimePhase.FAILED
                return DispatchResult(
                    kind="error",
                    steps=[],
                    message="Planner could not produce valid actions for this goal.",
                )
            state.planner_nudge = empty_plan_nudge(
                state,
                last_blocked=blocked or None,
            )
            return self.dispatch_next(state, page_context)

        state.empty_plan_retries = 0
        state.pending_actions = plan.actions[:3]
        state.pending_action_index = 0
        state.last_chat_message = (
            plan.user_message.strip()
            or plan.reasoning.strip()
            or planning_ack(state.task)
        )
        return self._dispatch_pending(state)

    def _dispatch_pending(self, state: RunState) -> DispatchResult:
        raw_action = state.pending_actions[state.pending_action_index]
        page = state.memory.current_page
        action = refresh_action_target(raw_action, page)
        if action is not raw_action:
            state.pending_actions[state.pending_action_index] = action
            emit_trace(
                state.run_id,
                "TARGET_RE_RESOLVED",
                step=state.step,
                from_id=raw_action.target.element_id if raw_action.target else "",
                to_id=action.target.element_id if action.target else "",
            )
        ok, block_reason = action_advances_goal(state, action)
        if not ok:
            emit_trace(
                state.run_id,
                "GOAL_GUARD_BLOCKED",
                step=state.step,
                reason=block_reason,
                action=action.type,
            )
            state.planner_nudge = (
                f"Blocked: {block_reason}. "
                "What part of the user's goal remains incomplete? "
                "Only act on that — do not escalate."
            )
            state.pending_action_index += 1
            if state.pending_action_index >= len(state.pending_actions):
                state.pending_actions = []
            if approve_completion(state, page, source="goal_guard"):
                return _completion_or_handoff(state, page, source="goal_guard")
            return self.dispatch_next(state, _page_context_from_memory(state))
        record_action_hash(state, action)
        steps = translate_action(action)
        if not steps and action.type == "finish":
            page = state.memory.current_page
            if approve_completion(state, page, source="finish_action"):
                return _completion_or_handoff(state, page, source="finish_action")
            state.planner_nudge = "Goal not verified. Choose the next concrete action."
            state.pending_actions = []
            return self.dispatch_next(state, _page_context_from_memory(state))

        if not steps:
            state.pending_action_index += 1
            if state.pending_action_index >= len(state.pending_actions):
                state.pending_actions = []
            return self.dispatch_next(state, _page_context_from_memory(state))

        state.phase = RuntimePhase.ACTING
        state.step += 1
        state.last_dispatched_action = action
        summary = f"{action.type}: {action.reason[:80]}"
        chat_message = state.last_chat_message or action.reason[:160]
        emit_trace(
            state.run_id,
            "ACTION_DISPATCHED",
            step=state.step,
            action=action.type,
            reason=action.reason,
        )
        return DispatchResult(
            kind="continue",
            steps=steps,
            action_summary=summary,
            chat_message=chat_message,
            runtime_phase="acting",
        )

    def record_result(
        self,
        state: RunState,
        action: AgentAction,
        *,
        success: bool,
        verified: bool | None,
        error: str | None,
        page_context: PageContext | None,
    ) -> DispatchResult:
        state.phase = RuntimePhase.VERIFYING
        before = state.memory.current_page
        before_sig = before.signature() if before else ""
        page = self.observe(state, page_context)
        after_sig = page.signature() if page else ""

        ok = verify_action_result(
            state,
            action,
            success=success,
            verified=verified,
            before=before,
            after=page,
        )
        apply_verified_progress(state, action, page, ok=ok, before=before)
        phase_changed = try_advance_phase(state, page)
        if phase_changed:
            state.pending_actions = []
            state.pending_action_index = 0
            state.planner_nudge = (
                f"Goal phase is now {state.current_phase}. "
                "Do not repeat completed work. Plan only actions for the current phase."
            )

        _record_action_metrics(state, action, ok=ok, success=success, verified=verified)

        record_action(
            state,
            action=action,
            page_url=page.url if page else "",
            success=success,
            verified=ok,
            error=error,
            state_before=before_sig,
            state_after=after_sig,
        )

        emit_trace(
            state.run_id,
            "VERIFICATION",
            step=state.step,
            success=success,
            verified=ok,
            action=action.type,
            target=action.target.element_id if action.target else None,
            url_before=before.url if before else "",
            url_after=page.url if page else "",
            state_before=before_sig,
            state_after=after_sig,
        )

        state.pending_action_index += 1
        if state.pending_action_index >= len(state.pending_actions):
            state.pending_actions = []

        if action.type == "handoff" and success:
            state.phase = RuntimePhase.HANDOFF
            state.waiting_for_user = True
            return DispatchResult(
                kind="handoff",
                steps=[],
                message=error or "Please complete the required step, then tap Resume.",
                runtime_phase="handoff",
            )

        if not ok:
            state.planner_nudge = (
                "The last action did not produce verified progress. "
                "Do not repeat the same target. Re-observe and try another strategy."
            )

        if (
            ok
            and _is_checkout_action(action)
            and state.current_phase in {"checkout", "checkout_reached"}
        ):
            state.milestones.add("reached_checkout")
            if checkout_requires_handoff(page):
                state.phase = RuntimePhase.HANDOFF
                state.waiting_for_user = True
                state.metrics["completion_source"] = "checkout_action_handoff"
                msg = (
                    "Sign in to complete checkout. Your cart is saved — "
                    "finish signing in, then tap Resume."
                )
                emit_trace(state.run_id, "CHECKOUT_HANDOFF", step=state.step, source="checkout_action")
                return DispatchResult(
                    kind="handoff",
                    steps=[],
                    message=msg,
                    chat_message=msg,
                    runtime_phase="handoff",
                )
            if page and is_checkout_flow_page(page):
                return _completion_or_handoff(state, page, source="checkout_action")
            state.planner_nudge = (
                "Checkout control click did not reach checkout or a login gate. "
                "Re-observe checkout-capable controls on the cart or current page."
            )
            return DispatchResult(kind="continue", steps=[], runtime_phase="observing")

        if approve_completion(state, page, source="post_action"):
            return _completion_or_handoff(state, page, source="post_action")

        if goal_quota_met(state) and state.parsed_task.goal in {
            "add_to_cart",
            "checkout",
        }:
            state.pending_actions = []
            state.pending_action_index = 0
            if approve_completion(state, page, source="quota_met"):
                return _completion_or_handoff(state, page, source="quota_met")

        return DispatchResult(kind="continue", steps=[], runtime_phase="observing")

    def current_action(self, state: RunState) -> AgentAction | None:
        if not state.pending_actions:
            return None
        idx = min(state.pending_action_index, len(state.pending_actions) - 1)
        return state.pending_actions[idx]


def _completion_or_handoff(
    state: RunState,
    page: BrowserPage | None,
    *,
    source: str,
) -> DispatchResult:
    if page and checkout_requires_handoff(page):
        state.phase = RuntimePhase.HANDOFF
        state.waiting_for_user = True
        state.metrics["completion_source"] = f"{source}_handoff"
        msg = (
            "Sign in to complete checkout. Your cart is saved — "
            "finish signing in, then tap Resume."
        )
        emit_trace(state.run_id, "CHECKOUT_HANDOFF", step=state.step, source=source)
        return DispatchResult(
            kind="handoff",
            steps=[],
            message=msg,
            chat_message=msg,
            runtime_phase="handoff",
        )
    state.phase = RuntimePhase.GOAL_REACHED
    msg = completion_message(state, page) if page else "Task completed."
    return DispatchResult(
        kind="complete",
        steps=[],
        message=msg,
        chat_message=msg,
    )


def _initial_remaining(parsed: ParsedTask) -> list[str]:
    if parsed.goal == "search":
        return ["find matching results"]
    if parsed.goal == "add_to_cart":
        if parsed.product_hints:
            return [f"add {hint}" for hint in parsed.product_hints]
        return [f"add {parsed.item_count} item(s) to cart"]
    if parsed.goal == "view_cart":
        return ["open cart page"]
    if parsed.goal in {"checkout", "purchase"}:
        return ["reach checkout"]
    if parsed.goal == "remove":
        return [f"remove {parsed.remove_target or 'item'} from cart"]
    return ["complete user request"]


def _page_context_from_memory(state: RunState) -> PageContext | None:
    page = state.memory.current_page
    if page is None:
        return None
    from core.protocol import PageContext

    return PageContext(title=page.title, url=page.url)


def _record_action_metrics(
    state: RunState,
    action: AgentAction,
    *,
    ok: bool,
    success: bool,
    verified: bool | None,
) -> None:
    categories = classify_action(action)
    spec = state.task_spec
    if spec:
        from agent_runtime.policy.action_gate import active_forbidden

        forbidden = active_forbidden(spec, state.current_phase)
        for category in categories:
            if category in forbidden:
                state.metrics["unnecessary_actions"] = int(
                    state.metrics.get("unnecessary_actions", 0)
                ) + 1
    if success and verified is False:
        state.metrics["verification_failures"] = int(
            state.metrics.get("verification_failures", 0)
        ) + 1
    if not ok:
        state.metrics["failed_actions"] = int(state.metrics.get("failed_actions", 0)) + 1
