"""Generic domain skill — site-agnostic goals and verification."""

from __future__ import annotations

from agent_runtime.domain.generic_parse import parse_generic_task
from agent_runtime.domain.protocol import DomainSkill
from agent_runtime.executor.actions import AgentAction
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.observation.signals import infer_generic_page_signals
from agent_runtime.policy.handoff import handoff_allowed
from agent_runtime.task.parsed import ParsedTask
from agent_runtime.task.spec import TaskSpec
from core.protocol import PageContext


class GenericDomainSkill(DomainSkill):
    skill_id = "generic"

    def parse_task_with_spec(self, task: str) -> tuple[ParsedTask, TaskSpec]:
        return parse_generic_task(task)

    def infer_page_signals(self, page: PageContext) -> list[str]:
        return infer_generic_page_signals(page)

    def forbidden_for_phase(self, phase: str, spec: TaskSpec) -> frozenset[str]:
        return spec.forbidden_actions or frozenset({"ready_for_payment_link"})

    def phase_completion_text(self, phase: str, spec: TaskSpec) -> str:
        return spec.target_state or spec.objective

    def phase_satisfied(self, phase: str, state: RunState, page: BrowserPage) -> bool:
        if phase == "clarify":
            return False
        if state.verified_progress_count >= 1:
            return True
        if state.milestones:
            return True
        return bool(page.signals) and "login_required" in page.signals

    def milestones_met(self, phase: str, state: RunState) -> bool:
        return state.verified_progress_count > 0 or bool(state.milestones)

    def is_goal_satisfied(self, state: RunState, page: BrowserPage | None) -> bool:
        if page is None or state.task_spec is None:
            return False
        phase = state.current_phase
        return self.phase_satisfied(phase, state, page)

    def approve_completion(
        self, state: RunState, page: BrowserPage | None, *, source: str
    ) -> bool:
        if page is None:
            return False
        if state.verified_progress_count < 1 and not state.milestones:
            return False
        if not self.is_goal_satisfied(state, page):
            return False
        state.metrics["completion_source"] = source
        return True

    def update_milestones(self, state: RunState, page: BrowserPage | None) -> None:
        if page is None:
            return
        if "login_required" in page.signals:
            state.milestones.add("auth_gate_seen")

    def sync_memory(self, state: RunState, page: BrowserPage | None) -> None:
        if page is None:
            return
        memory = state.memory
        memory.current_page = page
        memory.current_url = page.url
        if not memory.remaining_work:
            memory.remaining_work = [state.task_spec.objective if state.task_spec else state.task]

    def try_advance_phase(self, state: RunState, page: BrowserPage | None) -> bool:
        return False

    def filter_forbidden_actions(
        self,
        spec: TaskSpec,
        actions: list[AgentAction],
        *,
        current_phase: str,
        state: RunState,
    ) -> tuple[list[AgentAction], list[str]]:
        forbidden = self.forbidden_for_phase(current_phase, spec)
        kept: list[AgentAction] = []
        blocked: list[str] = []
        for action in actions:
            if action.type == "handoff" and "payment" in forbidden:
                blocked.append(f"{action.type}: payment handoff blocked in generic mode")
                continue
            kept.append(action)
        return kept, blocked

    def filter_non_advancing_actions(
        self, state: RunState, actions: list[AgentAction]
    ) -> tuple[list[AgentAction], list[str]]:
        return actions, []

    def classify_action(self, action: AgentAction) -> set[str]:
        categories: set[str] = set()
        if action.type in {"search", "type"}:
            categories.add("input")
        if action.type == "click":
            categories.add("click")
        if action.type == "navigate":
            categories.add("navigate")
        if action.type == "scroll":
            categories.add("scroll")
        return categories

    def action_advances_goal(
        self, state: RunState, action: AgentAction
    ) -> tuple[bool, str]:
        if action.type in {"wait", "scroll", "go_back", "navigate", "click", "type", "search"}:
            return True, ""
        return True, ""

    def goal_quota_met(self, state: RunState) -> bool:
        return False

    def find_goal_ready(self, state: RunState, page: BrowserPage | None) -> bool:
        return False

    def needs_search(self, state: RunState, page: BrowserPage | None) -> bool:
        return False

    def planner_nudges(self, state: RunState, page: BrowserPage | None) -> list[str]:
        return []

    def planner_context_extra(self, state: RunState, page: BrowserPage | None) -> str:
        return ""

    def verify_action_result(
        self,
        state: RunState,
        action: AgentAction,
        *,
        success: bool,
        verified: bool | None,
        before: BrowserPage | None,
        after: BrowserPage | None,
    ) -> bool:
        if after is None:
            return False
        if not success:
            return False
        if verified is False:
            return False
        if verified is True:
            return True
        if before and before.signature() != after.signature():
            return True
        if action.type in {"wait", "scroll", "go_back"}:
            return True
        return success

    def apply_verified_progress(
        self,
        state: RunState,
        action: AgentAction,
        page: BrowserPage | None,
        *,
        ok: bool,
        before: BrowserPage | None = None,
    ) -> bool:
        if ok:
            state.verified_progress_count += 1
        return ok

    def refresh_action_target(
        self, action: AgentAction, page: BrowserPage | None
    ) -> AgentAction:
        from agent_runtime.target.resolve import refresh_action_target

        return refresh_action_target(action, page)

    def post_action_handoff(
        self,
        state: RunState,
        page: BrowserPage | None,
        action: AgentAction,
        *,
        ok: bool,
    ):
        return None

    def completion_handoff(self, state: RunState, page: BrowserPage | None, *, source: str):
        return None

    def initial_remaining_work(self, parsed: ParsedTask) -> list[str]:
        return [parsed.raw or "Complete user request"]

    def handoff_allowed(self, page: BrowserPage | None, reason: str) -> bool:
        return handoff_allowed(page, reason)


_generic_skill = GenericDomainSkill()


def get_generic_skill() -> GenericDomainSkill:
    return _generic_skill
