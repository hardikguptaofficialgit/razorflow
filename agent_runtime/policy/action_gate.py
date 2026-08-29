"""Action gating — delegates to the active domain skill."""

from __future__ import annotations

from agent_runtime.config import shopping_domain_enabled
from agent_runtime.domain.generic_skill import get_generic_skill
from agent_runtime.executor.actions import AgentAction
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.policy.handoff import handoff_allowed
from agent_runtime.state.run_state import RunState
from agent_runtime.task.spec import TaskSpec

# Re-export shopping classifiers for tests when shopping domain is active.
from agent_runtime.domain.shopping import action_gate as _shopping_gate


def classify_action(action: AgentAction) -> set[str]:
    if not shopping_domain_enabled():
        return get_generic_skill().classify_action(action)
    return _shopping_gate.classify_action(action)


def active_forbidden(spec: TaskSpec, current_phase: str) -> frozenset[str]:
    return spec.forbidden_actions


def filter_forbidden_actions(
    spec: TaskSpec,
    actions: list[AgentAction],
    *,
    current_phase: str | None = None,
    state: RunState | None = None,
) -> tuple[list[AgentAction], list[str]]:
    phase = current_phase or spec.target_phase
    if state is not None:
        return state.skill().filter_forbidden_actions(
            spec, actions, current_phase=phase, state=state
        )
    if spec.metadata.get("domain") != "shopping":
        return actions, []
    return _shopping_gate.filter_forbidden_actions(
        spec, actions, current_phase=phase, state=None
    )


__all__ = [
    "classify_action",
    "active_forbidden",
    "filter_forbidden_actions",
    "handoff_allowed",
]
