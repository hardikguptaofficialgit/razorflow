"""Phase progression — delegates to domain skill."""

from __future__ import annotations

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState
from agent_runtime.task.spec import TaskSpec


def effective_phases(spec: TaskSpec) -> tuple[str, ...]:
    return spec.effective_phases()


def remaining_phases(state: RunState) -> tuple[str, ...]:
    spec = state.task_spec
    if spec is None:
        return ()
    phases = effective_phases(spec)
    try:
        idx = phases.index(state.current_phase)
    except ValueError:
        return phases
    return phases[idx:]


def try_advance_phase(state: RunState, page: BrowserPage | None) -> bool:
    return state.skill().try_advance_phase(state, page)
