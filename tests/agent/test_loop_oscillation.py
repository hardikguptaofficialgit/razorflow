"""Loop / oscillation detection in Agent Runtime V2."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.recovery.stuck import detect_stuck, record_action
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parse import parse_task_spec
from agent_runtime.task.parser import parse_task


def _state() -> RunState:
    parsed = parse_task("add snacks")
    spec = parse_task_spec("add snacks")
    return RunState(run_id="loop", task="add snacks", parsed_task=parsed, task_spec=spec)


def _click(sig_label: str) -> AgentAction:
    return AgentAction(
        type="click",
        target=ElementTarget(element_id="e1", role="button", description=sig_label),
        reason=sig_label,
        expectedOutcome="change",
    )


def test_repeated_failed_action_blocked() -> None:
    state = _state()
    action = _click("Add to cart")
    for _ in range(3):
        record_action(
            state,
            action=action,
            page_url="http://localhost/search",
            success=False,
            verified=False,
            error="not found",
            state_before="a",
            state_after="a",
        )
    msg = detect_stuck(state)
    assert msg is not None
    assert "do not repeat" in msg.lower() or "attempted" in msg.lower()


def test_oscillation_ab_detected() -> None:
    state = _state()
    a = _click("Product A")
    b = _click("Product B")
    for pair in [(a, True), (b, True), (a, True), (b, True)]:
        record_action(
            state,
            action=pair[0],
            page_url="http://localhost/search",
            success=pair[1],
            verified=pair[1],
            error=None if pair[1] else "fail",
            state_before="x",
            state_after="x" if not pair[1] else "y",
        )
    msg = detect_stuck(state)
    assert msg is not None
    assert "oscillat" in msg.lower()
