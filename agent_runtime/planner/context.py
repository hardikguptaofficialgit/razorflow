"""Compact planner context blocks."""

from __future__ import annotations

from agent_runtime.observation.browser_state import BrowserPage, format_observation
from agent_runtime.observation.checkout_controls import format_checkout_controls_section
from agent_runtime.policy.action_gate import active_forbidden
from agent_runtime.state.run_state import RunState


def build_planning_context(state: RunState, page: BrowserPage | None) -> str:
    spec = state.task_spec
    phase = state.current_phase
    lines = [
        "PLANNING CONTEXT:",
        f"GOAL: {state.task}",
        f"CURRENT PHASE: {phase}",
        f"CURRENT PAGE: {page.url if page else '(unknown)'}",
    ]
    if state.completed_phases:
        lines.append(f"COMPLETED PHASES: {', '.join(state.completed_phases)}")
    if state.memory.completed_steps:
        lines.append(
            "VERIFIED: " + "; ".join(state.memory.completed_steps[-4:])
        )
    if state.memory.remaining_work:
        lines.append("REMAINING: " + "; ".join(state.memory.remaining_work[:3]))
    if spec:
        forbidden = sorted(active_forbidden(spec, phase))
        if forbidden:
            lines.append(f"FORBIDDEN: {', '.join(forbidden)}")
    if state.memory.failed_actions:
        lines.append(
            "RECENT FAILED ACTIONS: " + "; ".join(state.memory.failed_actions[-3:])
        )
    if page:
        checkout_section = format_checkout_controls_section(page)
        if checkout_section:
            lines.append(checkout_section)
        elif phase in {"checkout", "checkout_reached"}:
            lines.append(
                "Checkout-capable controls: (none detected yet — inspect links/buttons)"
            )
    return "\n".join(lines)


def build_observation_block(state: RunState, page: BrowserPage | None) -> str:
    parts = [build_planning_context(state, page)]
    parts.append(format_observation(page))
    return "\n\n".join(parts)
