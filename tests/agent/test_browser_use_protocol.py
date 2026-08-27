"""Protocol helpers for Browser Use executor sync messages."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.protocol import AgentSyncMessage, ExecutorModeMessage  # noqa: E402


def test_agent_sync_message_round_trip() -> None:
    payload = AgentSyncMessage(
        type="AGENT_SYNC",
        runId="run-1",
        phase="acting",
        url="http://localhost:3000/search?q=shampoo",
        title="Search",
        step=3,
        actionSummary="click element",
        cursor={"x": 120.0, "y": 80.0},
        highlight={"x": 100.0, "y": 60.0, "width": 40.0, "height": 24.0},
    ).model_dump(by_alias=True, exclude_none=True)

    parsed = AgentSyncMessage.model_validate(payload)
    assert parsed.run_id == "run-1"
    assert parsed.phase == "acting"
    assert parsed.cursor is not None
    assert parsed.cursor.x == 120.0
    assert parsed.highlight is not None
    assert parsed.highlight.width == 40.0


def test_executor_mode_message() -> None:
    payload = ExecutorModeMessage(
        type="EXECUTOR_MODE",
        runId="run-2",
        mode="browser_use",
    ).model_dump(by_alias=True, exclude_none=True)

    parsed = ExecutorModeMessage.model_validate(payload)
    assert parsed.mode == "browser_use"
