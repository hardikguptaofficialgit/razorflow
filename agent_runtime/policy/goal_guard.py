"""Goal guard — delegates to the active domain skill."""

from __future__ import annotations

from agent_runtime.executor.actions import AgentAction
from agent_runtime.state.run_state import RunState


def goal_quota_met(state: RunState) -> bool:
    return state.skill().goal_quota_met(state)


def action_advances_goal(state: RunState, action: AgentAction) -> tuple[bool, str]:
    return state.skill().action_advances_goal(state, action)


def filter_non_advancing_actions(
    state: RunState,
    actions: list[AgentAction],
) -> tuple[list[AgentAction], list[str]]:
    return state.skill().filter_non_advancing_actions(state, actions)


def should_stop_without_planning(state: RunState) -> bool:
    work = state.memory.remaining_work
    if work and any(
        token in work[0].lower()
        for token in ("goal satisfied", "stop", "do not add", "do not open")
    ):
        if goal_quota_met(state) or state.parsed_task.goal in {"search", "compare", "achieve"}:
            return True
    return False
