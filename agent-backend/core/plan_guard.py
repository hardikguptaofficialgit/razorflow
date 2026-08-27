"""Backward-compatible alias for action policy validation."""

from __future__ import annotations

from core.action_policy import validate_planner_chunk as _validate
from core.task_intent import parse_task_intent


def guard_planner_chunk(session, chunk):
    return _validate(session, chunk, parse_task_intent(session.task))


__all__ = ["guard_planner_chunk"]
