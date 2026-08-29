"""Domain skill protocol — optional commerce (or other) semantics on generic core."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_runtime.executor.actions import AgentAction
    from agent_runtime.observation.browser_state import BrowserPage
    from agent_runtime.runtime import DispatchResult
    from agent_runtime.state.run_state import RunState
    from agent_runtime.task.parser import ParsedTask
    from agent_runtime.task.spec import TaskSpec
    from core.protocol import PageContext


class DomainSkill(ABC):
    """Pluggable domain semantics for V2 runtime (shopping, generic web, etc.)."""

    @property
    @abstractmethod
    def skill_id(self) -> str: ...

    @abstractmethod
    def parse_task_with_spec(self, task: str) -> tuple["ParsedTask", "TaskSpec"]: ...

    @abstractmethod
    def infer_page_signals(self, page: "PageContext") -> list[str]: ...

    @abstractmethod
    def forbidden_for_phase(self, phase: str, spec: "TaskSpec") -> frozenset[str]: ...

    @abstractmethod
    def phase_completion_text(self, phase: str, spec: "TaskSpec") -> str: ...

    @abstractmethod
    def phase_satisfied(self, phase: str, state: "RunState", page: "BrowserPage") -> bool: ...

    @abstractmethod
    def milestones_met(self, phase: str, state: "RunState") -> bool: ...

    @abstractmethod
    def is_goal_satisfied(self, state: "RunState", page: "BrowserPage | None") -> bool: ...

    @abstractmethod
    def approve_completion(
        self, state: "RunState", page: "BrowserPage | None", *, source: str
    ) -> bool: ...

    @abstractmethod
    def update_milestones(self, state: "RunState", page: "BrowserPage | None") -> None: ...

    @abstractmethod
    def sync_memory(self, state: "RunState", page: "BrowserPage | None") -> None: ...

    @abstractmethod
    def try_advance_phase(self, state: "RunState", page: "BrowserPage | None") -> bool: ...

    @abstractmethod
    def filter_forbidden_actions(
        self,
        spec: "TaskSpec",
        actions: list["AgentAction"],
        *,
        current_phase: str,
        state: "RunState",
    ) -> tuple[list["AgentAction"], list[str]]: ...

    @abstractmethod
    def filter_non_advancing_actions(
        self, state: "RunState", actions: list["AgentAction"]
    ) -> tuple[list["AgentAction"], list[str]]: ...

    @abstractmethod
    def classify_action(self, action: "AgentAction") -> set[str]: ...

    @abstractmethod
    def action_advances_goal(
        self, state: "RunState", action: "AgentAction"
    ) -> tuple[bool, str]: ...

    @abstractmethod
    def goal_quota_met(self, state: "RunState") -> bool: ...

    @abstractmethod
    def find_goal_ready(self, state: "RunState", page: "BrowserPage | None") -> bool: ...

    @abstractmethod
    def needs_search(self, state: "RunState", page: "BrowserPage | None") -> bool: ...

    @abstractmethod
    def planner_nudges(self, state: "RunState", page: "BrowserPage | None") -> list[str]: ...

    @abstractmethod
    def planner_context_extra(self, state: "RunState", page: "BrowserPage | None") -> str: ...

    @abstractmethod
    def verify_action_result(
        self,
        state: "RunState",
        action: "AgentAction",
        *,
        success: bool,
        verified: bool | None,
        before: "BrowserPage | None",
        after: "BrowserPage | None",
    ) -> bool: ...

    @abstractmethod
    def apply_verified_progress(
        self,
        state: "RunState",
        action: "AgentAction",
        page: "BrowserPage | None",
        *,
        ok: bool,
        before: "BrowserPage | None" = None,
    ) -> bool: ...

    @abstractmethod
    def refresh_action_target(
        self, action: "AgentAction", page: "BrowserPage | None"
    ) -> "AgentAction": ...

    @abstractmethod
    def post_action_handoff(
        self,
        state: "RunState",
        page: "BrowserPage | None",
        action: "AgentAction",
        *,
        ok: bool,
    ) -> "DispatchResult | None": ...

    @abstractmethod
    def completion_handoff(
        self, state: "RunState", page: "BrowserPage | None", *, source: str
    ) -> "DispatchResult | None": ...

    @abstractmethod
    def initial_remaining_work(self, parsed: "ParsedTask") -> list[str]: ...

    @abstractmethod
    def handoff_allowed(self, page: "BrowserPage | None", reason: str) -> bool: ...
