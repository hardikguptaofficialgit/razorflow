"""Multi-phase goal progression — advance current_phase when a phase is verified."""

from __future__ import annotations

from agent_runtime.events.trace import emit_trace
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState
from agent_runtime.domain.shopping.spec import GoalPhase
from agent_runtime.task.spec import TaskSpec
from agent_runtime.domain.shopping.goal import phase_satisfied


def effective_phases(spec: TaskSpec) -> tuple[GoalPhase, ...]:
    if spec.goal_phases:
        return spec.goal_phases
    return (spec.target_phase,)


def remaining_phases(state: RunState) -> tuple[GoalPhase, ...]:
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
    """Advance to the next goal phase when the current one is verified."""
    if page is None or state.task_spec is None:
        return False

    spec = state.task_spec
    phases = effective_phases(spec)
    if len(phases) <= 1:
        return False

    if not phase_satisfied(state.current_phase, state, page):
        return False

    try:
        idx = phases.index(state.current_phase)
    except ValueError:
        return False

    if idx >= len(phases) - 1:
        return False

    completed = state.current_phase
    next_phase = phases[idx + 1]
    state.completed_phases.append(completed)
    state.current_phase = next_phase

    if completed == "cart_updated" and next_phase == "checkout_reached":
        if "ADD_PHASE_COMPLETE" not in state.memory.constraints:
            state.memory.constraints.append("ADD_PHASE_COMPLETE")

    state.memory.remaining_work = _remaining_work_for_phase(state, next_phase)
    emit_trace(
        state.run_id,
        "PHASE_ADVANCED",
        step=state.step,
        from_phase=completed,
        to_phase=next_phase,
    )
    return True


def _remaining_work_for_phase(state: RunState, phase: GoalPhase) -> list[str]:
    if phase == "checkout_reached":
        return [
            "Cart requirement verified — navigate to checkout using visible checkout controls. "
            "Do NOT search or add more items."
        ]
    if phase == "cart_updated":
        target = state.parsed_task.item_count
        return [f"Add {target} suitable item(s) to cart"]
    if phase == "search_results":
        return ["Find and display relevant search results"]
    return ["Complete current phase"]
