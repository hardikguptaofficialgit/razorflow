"""Generic task parsing — no shopping vocabulary."""

from __future__ import annotations

import re

from agent_runtime.task.parsed import ParsedTask
from agent_runtime.task.spec import TaskSpec

_GIBBERISH = re.compile(r"^[a-z]{1,4}$|^(?:wdwd|asdf|test|hello|hi)$", re.I)


def parse_generic_task(task: str) -> tuple[ParsedTask, TaskSpec]:
    raw = task.strip()
    if not raw or len(raw) < 3 or _GIBBERISH.match(raw):
        spec = TaskSpec(
            raw=raw,
            goal="clarify",
            objective="Clarify what the user wants to accomplish on this page.",
            target_phase="clarify",
            actionable=False,
            clarification_reason="Please describe what you want done on this page.",
        )
        return _spec_to_parsed(spec), spec

    spec = TaskSpec(
        raw=raw,
        goal="achieve",
        objective=raw,
        target_phase="complete",
        goal_phases=("complete",),
        target_state="The user's request is visibly satisfied on the page.",
        completion_conditions=("User request outcome is verified on the current page.",),
    )
    return _spec_to_parsed(spec), spec


def _spec_to_parsed(spec: TaskSpec) -> ParsedTask:
    return ParsedTask(
        raw=spec.raw,
        goal=spec.goal,  # type: ignore[arg-type]
        actionable=spec.actionable,
        clarification_reason=spec.clarification_reason,
        item_count=spec.quantity,
        product_hints=spec.entities,
    )
