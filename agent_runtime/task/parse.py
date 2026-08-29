"""Parse tasks via the active domain skill."""

from __future__ import annotations

from agent_runtime.domain.registry import resolve_domain_skill
from agent_runtime.domain.shopping.parse import parse_task_spec as parse_shopping_task_spec
from agent_runtime.domain.shopping.parse import spec_to_parsed
from agent_runtime.task.spec import TaskSpec

__all__ = ["parse_task_spec", "spec_to_parsed", "parse_shopping_task_spec"]


def parse_task_spec(task: str) -> TaskSpec:
    return resolve_domain_skill(task).parse_task_with_spec(task)[1]
