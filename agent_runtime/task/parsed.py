"""Parsed task view shared by domain skills and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TaskGoal = Literal[
    "search",
    "add_to_cart",
    "view_cart",
    "checkout",
    "purchase",
    "remove",
    "compare",
    "browse",
    "achieve",
    "clarify",
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
