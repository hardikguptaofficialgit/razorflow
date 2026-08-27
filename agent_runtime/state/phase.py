"""Runtime phase labels (single state machine)."""

from __future__ import annotations

from enum import Enum


class RuntimePhase(str, Enum):
    TASK_RECEIVED = "task_received"
    OBSERVING = "observing"
    PLANNING = "planning"
    ACTING = "acting"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    WAITING = "waiting"
    HANDOFF = "handoff"
    GOAL_REACHED = "goal_reached"
    FAILED = "failed"
    NEEDS_CLARIFICATION = "needs_clarification"
