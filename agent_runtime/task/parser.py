"""Parse natural-language tasks into structured goals (site-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_runtime.task.parse import parse_task_spec, spec_to_parsed
from agent_runtime.task.spec import TaskSpec

TaskGoal = Literal[
    "search",
    "add_to_cart",
    "view_cart",
    "checkout",
    "purchase",
    "remove",
    "compare",
    "browse",
    "unknown",
]


@dataclass(frozen=True)
class ParsedTask:
    raw: str
    goal: TaskGoal
    actionable: bool
    clarification_reason: str = ""
    item_count: int = 1
    product_hints: tuple[str, ...] = ()
    remove_target: str | None = None
    budget_inr: float | None = None
    prefer_best: bool = False
    requires_checkout: bool = False

    def summary(self) -> str:
        lines = [
            f"goal={self.goal}",
            f"items={self.item_count}",
        ]
        if self.product_hints:
            lines.append(f"products={', '.join(self.product_hints)}")
        if self.budget_inr is not None:
            lines.append(f"budget_inr={self.budget_inr:.0f}")
        if self.prefer_best:
            lines.append("prefer_best=true")
        if self.remove_target:
            lines.append(f"remove={self.remove_target}")
        return "; ".join(lines)


def parse_task(task: str) -> ParsedTask:
    return spec_to_parsed(parse_task_spec(task))


def parse_task_with_spec(task: str) -> tuple[ParsedTask, TaskSpec]:
    spec = parse_task_spec(task)
    return spec_to_parsed(spec), spec
