"""Goal verification — delegates to the active domain skill."""

from __future__ import annotations

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState


def phase_satisfied(phase: str, state: RunState, page: BrowserPage) -> bool:
    return state.skill().phase_satisfied(phase, state, page)


def is_goal_satisfied(state: RunState, page: BrowserPage | None) -> bool:
    return state.skill().is_goal_satisfied(state, page)


def milestones_met(state: RunState) -> bool:
    spec = state.task_spec
    if spec is None:
        return False
    phases = spec.effective_phases()
    phase = state.current_phase if len(phases) > 1 else spec.target_phase
    return state.skill().milestones_met(phase, state)


def approve_completion(state: RunState, page: BrowserPage | None, *, source: str) -> bool:
    return state.skill().approve_completion(state, page, source=source)


def update_milestones(state: RunState, page: BrowserPage | None) -> None:
    state.skill().update_milestones(state, page)
