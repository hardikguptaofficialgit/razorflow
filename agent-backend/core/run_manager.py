"""In-memory run/session manager for iterative observe-act-replan loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from core.agent_phase import AgentPhase
from core.protocol import (
    ActionHistoryEntry,
    ActionStep,
    BrowserObservation,
    PageContext,
    PaymentLinkProposalPayload,
    RunStatus,
    WaitForUserStep,
)
from core.page_cart import header_cart_item_count
from utils.config import (
    MAX_CONSECUTIVE_FAILURES,
    MAX_PLANNING_TURNS,
    MAX_STALE_PAGE_TURNS,
)


def page_fingerprint(page_context: PageContext | None) -> str | None:
    if page_context is None:
        return None

    element_hints = "|".join(
        f"{item.role}:{item.text}:{item.placeholder}"[:40]
        for item in page_context.elements[:5]
    )
    product_hints = "|".join(
        f"{product.title[:24]}:{product.price_text[:12]}:{product.rating_text[:8]}"
        for product in page_context.products[:3]
    )
    cart_count = header_cart_item_count(page_context)

    return (
        f"{page_context.url}|{page_context.title}|"
        f"cart:{cart_count}|{element_hints}|{product_hints}"
    )


@dataclass
class RunSession:
    run_id: str
    task: str
    status: RunStatus = "active"
    planning_turn: int = 0
    latest_page_context: PageContext | None = None
    history: list[ActionHistoryEntry] = field(default_factory=list)
    consecutive_failures: int = 0
    stale_page_turns: int = 0
    stale_recovery_used: bool = False
    last_page_fingerprint: str | None = None
    last_dispatched_steps: list[ActionStep] = field(default_factory=list)
    waiting_for_user: bool = False
    pending_terminal: Literal[
        "continue",
        "complete",
        "wait_for_user",
        "ready_for_payment_link",
    ] = "continue"
    pending_payment_proposal: PaymentLinkProposalPayload | None = None
    payment_link_attempts: int = 0
    last_planning_source: Literal[
        "page_context_only",
        "page_context_and_browser_use",
    ] = "page_context_only"
    skipped_product_queries: int = 0
    phase: AgentPhase = "task_received"
    planner_nudge: str | None = None
    blocked_action_signatures: set[str] = field(default_factory=set)
    verified_progress_count: int = 0
    milestones: set[str] = field(default_factory=set)
    goal_pre_satisfied: bool = False
    action_step: int = 0
    needs_clarification_reason: str | None = None
    connection_id: str | None = None
    complete_replan_attempts: int = 0


class RunManager:
    def __init__(self) -> None:
        self._sessions: dict[str, RunSession] = {}

    def start_run(
        self,
        run_id: str,
        task: str,
        page_context: PageContext | None,
        *,
        connection_id: str | None = None,
    ) -> RunSession:
        session = RunSession(
            run_id=run_id,
            task=task,
            latest_page_context=page_context,
            last_page_fingerprint=page_fingerprint(page_context),
            connection_id=connection_id,
        )
        from core.goal_verifier import capture_initial_state
        from core.task_interpretation import interpret_task

        interpretation = interpret_task(task)
        if not interpretation.actionable:
            session.needs_clarification_reason = interpretation.reason
            session.phase = "needs_clarification"
        else:
            capture_initial_state(session, interpretation.intent)
        self._sessions[run_id] = session
        return session

    def get_run(self, run_id: str) -> RunSession | None:
        return self._sessions.get(run_id)

    def cancel_run(self, run_id: str) -> RunSession | None:
        session = self._sessions.get(run_id)
        if session is None:
            return None

        session.status = "cancelled"
        return session

    def cancel_active_runs(self, connection_id: str | None = None) -> list[str]:
        cancelled: list[str] = []
        for session in self._sessions.values():
            if session.status not in {"active", "waiting_for_user"}:
                continue
            if connection_id is not None and session.connection_id != connection_id:
                continue
            session.status = "cancelled"
            cancelled.append(session.run_id)
        return cancelled

    def resume_run(
        self,
        run_id: str,
        page_context: PageContext | None,
    ) -> RunSession | None:
        session = self._sessions.get(run_id)
        if session is None or not session.waiting_for_user:
            return None

        session.status = "active"
        session.waiting_for_user = False
        if page_context is not None:
            session.latest_page_context = page_context
            session.last_page_fingerprint = page_fingerprint(page_context)
        return session

    def mark_steps_dispatched(
        self,
        session: RunSession,
        steps: list[ActionStep],
        terminal: Literal[
            "continue",
            "complete",
            "wait_for_user",
            "ready_for_payment_link",
        ],
        payment_proposal: PaymentLinkProposalPayload | None = None,
    ) -> None:
        session.last_dispatched_steps = steps
        # LLM cannot arm completion — only the goal verifier may complete.
        session.pending_terminal = "continue" if terminal == "complete" else terminal
        session.pending_payment_proposal = payment_proposal
        if steps:
            session.action_step += 1

    def record_action_result(
        self,
        session: RunSession,
        step: ActionStep,
        success: bool,
        error: str | None,
        page_context: PageContext | None,
        verified: bool | None = None,
    ) -> None:
        fingerprint = page_fingerprint(page_context)
        session.history.append(
            ActionHistoryEntry(
                step=step,
                success=success,
                error=error,
                verified=verified,
                page_fingerprint=fingerprint,
            ),
        )

        if page_context is not None:
            session.latest_page_context = page_context

        if success:
            session.consecutive_failures = 0
        else:
            session.consecutive_failures += 1
            sig = self._action_signature(step)
            if sig:
                session.blocked_action_signatures.add(sig)

        # Typing into a field often leaves URL/title unchanged — don't treat that as stuck.
        action_name = getattr(step, "action", "")
        progress_expected = action_name in {
            "click_element",
            "wait_for_user",
            "navigate_url",
        }

        if fingerprint and fingerprint == session.last_page_fingerprint:
            if success and progress_expected:
                # Executor-verified actions (e.g. add-to-cart badge) may not change URL/title.
                if verified is True:
                    session.stale_page_turns = 0
                else:
                    session.stale_page_turns += 1
                if action_name == "navigate_url":
                    url = getattr(step, "url", "")
                    recent_navs = [
                        getattr(entry.step, "url", "")
                        for entry in session.history[-4:]
                        if getattr(entry.step, "action", "") == "navigate_url"
                        and entry.success
                    ]
                    if recent_navs.count(url) >= 2:
                        session.stale_page_turns += 1
            elif not success:
                session.stale_page_turns += 1
        else:
            session.stale_page_turns = 0
            session.last_page_fingerprint = fingerprint

    def increment_turn(self, session: RunSession) -> None:
        session.planning_turn += 1

    def check_safeguards(self, session: RunSession) -> str | None:
        if session.status == "cancelled":
            return "Run cancelled."

        if session.planning_turn >= MAX_PLANNING_TURNS:
            return "Reached maximum planning turns."

        if session.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            return "Too many consecutive action failures."

        if session.stale_page_turns >= MAX_STALE_PAGE_TURNS:
            # One soft recovery: reset once so heuristics/LLM can try a different path.
            if not session.stale_recovery_used:
                session.stale_recovery_used = True
                session.stale_page_turns = 0
                return None
            return "No meaningful page change after repeated actions."

        return None

    def complete_run(self, session: RunSession, message: str = "") -> None:
        session.status = "complete"

    def request_payment_confirmation(
        self,
        session: RunSession,
        proposal: PaymentLinkProposalPayload,
    ) -> None:
        session.status = "waiting_for_user"
        session.waiting_for_user = True
        session.pending_payment_proposal = proposal
        session.pending_terminal = "ready_for_payment_link"

    def clear_payment_proposal(self, session: RunSession) -> None:
        session.pending_payment_proposal = None
        session.pending_terminal = "continue"

    def increment_payment_attempt(self, session: RunSession) -> int:
        session.payment_link_attempts += 1
        return session.payment_link_attempts

    def wait_for_user(self, session: RunSession) -> None:
        session.status = "waiting_for_user"
        session.waiting_for_user = True

    def fail_run(self, session: RunSession, message: str) -> None:
        session.status = "error"

    def step_requests_wait(self, step: ActionStep) -> bool:
        return isinstance(step, WaitForUserStep)

    @staticmethod
    def _action_signature(step: ActionStep) -> str | None:
        from core.action_loop import action_signature as sig_fn

        try:
            return sig_fn(step)
        except Exception:
            return None
