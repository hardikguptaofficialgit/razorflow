"""Planner pipeline diagnostics for trace/debug."""

from __future__ import annotations

from typing import Any

from agent_runtime.executor.actions import AgentAction, PlannerOutput
from agent_runtime.events.trace import emit_trace


def _truncate(text: str, limit: int = 400) -> str:
    cleaned = text.replace("\n", " ").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def emit_planner_diagnostics(
    run_id: str,
    *,
    step: int,
    user_prompt: str,
    raw_output: str | None,
    schema_result: PlannerOutput | None,
    normalized_actions: list[AgentAction],
    gate_blocked: list[str],
    final_actions: list[AgentAction],
    error: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "planner_input": _truncate(user_prompt, 1200),
        "planner_raw_output": _truncate(raw_output or "", 1200) if raw_output else None,
        "schema_action_count": len(schema_result.actions) if schema_result else 0,
        "normalized_action_count": len(normalized_actions),
        "gate_blocked": gate_blocked[:6],
        "final_action_count": len(final_actions),
        "final_actions": [
            {
                "type": action.type,
                "elementId": action.target.element_id if action.target else None,
                "matchText": action.target.match_text if action.target else None,
                "reason": _truncate(action.reason, 120),
            }
            for action in final_actions[:4]
        ],
    }
    if error:
        payload["error"] = _truncate(error, 300)
    emit_trace(run_id, "PLANNER_DIAGNOSTICS", step=step, **payload)
