"""Single source of truth for an agent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from agent_runtime.executor.actions import AgentAction
from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.domain.protocol import DomainSkill
from agent_runtime.state.phase import RuntimePhase
from agent_runtime.task.parsed import ParsedTask
from agent_runtime.task.spec import TaskSpec


PhaseId = str


@dataclass
class ActionRecord:
    step: int
    action: AgentAction
    page_url: str
    success: bool
    verified: bool | None
    error: str | None = None
    state_before: str = ""
    state_after: str = ""
    signature: str = ""
    duration_ms: int = 0


@dataclass
class RunState:
    run_id: str
    task: str
    parsed_task: ParsedTask
    task_spec: TaskSpec | None = None
    phase: RuntimePhase = RuntimePhase.TASK_RECEIVED
    step: int = 0
    planning_turn: int = 0
    terminal: str | None = None
    terminal_message: str = ""
    waiting_for_user: bool = False
    handoff_reason: str = ""
    needs_clarification_reason: str = ""
    verified_progress_count: int = 0
    consecutive_failures: int = 0
    milestones: set[str] = field(default_factory=set)
    memory: TaskMemory = field(default_factory=TaskMemory)
    action_history: list[ActionRecord] = field(default_factory=list)
    pending_actions: list[AgentAction] = field(default_factory=list)
    pending_action_index: int = 0
    last_dispatched_action: AgentAction | None = None
    last_chat_message: str = ""
    planner_nudge: str = ""
    empty_plan_retries: int = 0
    planner_parse_retries: int = 0
    current_phase: PhaseId = "complete"
    completed_phases: list[PhaseId] = field(default_factory=list)
    blocked_signatures: set[str] = field(default_factory=set)
    metrics: dict[str, Any] = field(default_factory=dict)
    connection_id: str = ""
    llm_run_config: object | None = None
    shopping_skill_enabled: bool | None = None
    max_agent_steps: int | None = None
    _domain_skill: DomainSkill | None = field(default=None, repr=False, compare=False)

    def skill(self) -> DomainSkill:
        if self._domain_skill is None:
            from agent_runtime.domain.registry import resolve_domain_skill

            self._domain_skill = resolve_domain_skill(
                self.task,
                shopping_enabled=self.shopping_skill_enabled,
            )
        return self._domain_skill

    def bind_skill(self, skill: DomainSkill) -> None:
        self._domain_skill = skill

    def fingerprint(self) -> str:
        page = self.memory.current_page
        if not page:
            return ""
        return f"{page.url}|{len(page.cart_lines)}|{len(page.products)}"
