"""Tests for action loop detection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.action_loop import (  # noqa: E402
    action_signature,
    consecutive_success_repeats,
    detect_loop_nudge,
)
from core.protocol import ClickElementStep, NavigateUrlStep  # noqa: E402
from core.run_manager import ActionHistoryEntry, RunSession  # noqa: E402


def test_action_signature_navigate() -> None:
    step = NavigateUrlStep(action="navigate_url", url="http://localhost/search?q=watches")
    assert action_signature(step) == "nav:http://localhost/search?q=watches"


def test_consecutive_success_repeats() -> None:
    session = RunSession(run_id="r1", task="buy watches")
    nav = NavigateUrlStep(action="navigate_url", url="http://localhost/search?q=watches")
    sig = action_signature(nav)
    session.history = [
        ActionHistoryEntry(step=nav, success=True),
        ActionHistoryEntry(step=nav, success=True),
    ]
    assert consecutive_success_repeats(session, sig) == 2


def test_detect_loop_nudge_repeated_navigate() -> None:
    session = RunSession(run_id="r2", task="buy watches")
    nav = NavigateUrlStep(action="navigate_url", url="http://localhost/search?q=watches")
    session.history = [
        ActionHistoryEntry(step=nav, success=True),
        ActionHistoryEntry(step=nav, success=True),
        ActionHistoryEntry(step=nav, success=True),
    ]
    nudge = detect_loop_nudge(session)
    assert nudge is not None
    assert "LOOP DETECTED" in nudge
