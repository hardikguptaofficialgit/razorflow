"""Single source of truth for an agent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from agent_runtime.executor.actions import AgentAction
from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.state.phase import RuntimePhase
from agent_runtime.task.spec import GoalPhase
from agent_runtime.task.parser import ParsedTask
from agent_runtime.task.spec import TaskSpec


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
    current_phase: GoalPhase = "search_results"
    completed_phases: list[GoalPhase] = field(default_factory=list)
    blocked_signatures: set[str] = field(default_factory=set)
    metrics: dict[str, Any] = field(default_factory=dict)
    connection_id: str = ""

    def fingerprint(self) -> str:
        page = self.memory.current_page
        if not page:
            return ""
        return f"{page.url}|{len(page.cart_lines)}|{len(page.products)}"
