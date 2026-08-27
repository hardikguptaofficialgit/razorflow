"""Short-horizon LLM planner."""

from __future__ import annotations

import time

from agent_runtime.events.trace import emit_trace
from agent_runtime.executor.actions import AgentAction, PlannerOutput
from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.observation.browser_state import BrowserPage, format_observation
from agent_runtime.planner.llm_provider import LLMProvider
from agent_runtime.planner.prompts import SYSTEM_PROMPT, build_user_prompt
from agent_runtime.policy.action_gate import filter_forbidden_actions
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parser import ParsedTask


class LLMPlanner:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def plan(
        self,
        state: RunState,
        page: BrowserPage | None,
        *,
        screenshot_data_url: str | None = None,
    ) -> PlannerOutput:
        started = time.perf_counter()
        spec_block = state.task_spec.to_prompt_block() if state.task_spec else ""
        verified = _verified_progress_block(state)
        user_prompt = build_user_prompt(
            task=state.task,
            task_spec_block=spec_block,
            task_summary=state.parsed_task.summary(),
            memory_block=state.memory.to_prompt_block(),
            observation_block=format_observation(page),
            verified_block=verified,
            nudge=state.planner_nudge,
        )
        output = self._provider.plan(
            SYSTEM_PROMPT,
            user_prompt,
            screenshot_data_url=screenshot_data_url,
        )
        output.actions = _filter_blocked(state, output.actions)
        if state.task_spec:
            output.actions, _ = filter_forbidden_actions(state.task_spec, output.actions)
        duration_ms = int((time.perf_counter() - started) * 1000)
        emit_trace(
            state.run_id,
            "PLAN",
            step=state.step,
            duration_ms=duration_ms,
            action_count=len(output.actions),
            propose_finish=output.propose_finish,
            propose_handoff=output.propose_handoff,
        )
        state.planner_nudge = ""
        state.planning_turn += 1
        state.metrics["llm_calls"] = int(state.metrics.get("llm_calls", 0)) + 1
        return output


def _filter_blocked(state: RunState, actions: list[AgentAction]) -> list[AgentAction]:
    filtered: list[AgentAction] = []
    for action in actions:
        sig = action_signature(action)
        if sig in state.blocked_signatures:
            continue
        filtered.append(action)
    return filtered


def action_signature(action: AgentAction) -> str:
    target = action.target
    element = target.element_id if target else ""
    match = target.match_text if target else ""
    params = ",".join(f"{k}={v}" for k, v in sorted(action.parameters.items()))
    return f"{action.type}|{element}|{match}|{params}"


def _verified_progress_block(state: RunState) -> str:
    lines = ["VERIFIED PROGRESS:"]
    if state.milestones:
        lines.append("- milestones: " + ", ".join(sorted(state.milestones)))
    lines.append(f"- verified_actions: {state.verified_progress_count}")
    lines.append(f"- items_added: {state.memory.items_added}/{state.memory.items_target}")
    if state.memory.completed_steps:
        lines.append("- completed:")
        lines.extend(f"  • {step}" for step in state.memory.completed_steps[-6:])
    if state.task_spec:
        lines.append(f"- target_state: {state.task_spec.target_state}")
    return "\n".join(lines)
