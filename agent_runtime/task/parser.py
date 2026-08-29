"""Parse natural-language tasks into structured goals."""

from __future__ import annotations

from agent_runtime.domain.registry import resolve_domain_skill
from agent_runtime.task.parsed import ParsedTask, TaskGoal  # noqa: F401
from agent_runtime.task.spec import TaskSpec


def parse_task(task: str) -> ParsedTask:
    return resolve_domain_skill(task).parse_task_with_spec(task)[0]


def parse_task_with_spec(task: str) -> tuple[ParsedTask, TaskSpec]:
    skill = resolve_domain_skill(task)
    return skill.parse_task_with_spec(task)


__all__ = ["ParsedTask", "TaskGoal", "parse_task", "parse_task_with_spec"]
