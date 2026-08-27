"""Explicit agent run phases."""

from __future__ import annotations

from typing import Literal

AgentPhase = Literal[
    "task_received",
    "observing",
    "planning",
    "action_validation",
    "executing",
    "verifying",
    "recovering",
    "goal_reached",
    "needs_clarification",
    "failed",
    "handoff",
]
