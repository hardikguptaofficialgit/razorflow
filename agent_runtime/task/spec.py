"""Explicit task representation for the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TaskIntent = Literal[
    "search",
    "add_to_cart",
    "view_cart",
    "checkout",
    "purchase",
    "remove",
    "compare",
    "unknown",
]

FORBIDDEN_BY_INTENT: dict[TaskIntent, frozenset[str]] = {
    "search": frozenset({"checkout", "payment", "add_to_cart", "cart_nav"}),
    "compare": frozenset({"checkout", "payment", "add_to_cart", "cart_nav"}),
    "add_to_cart": frozenset({"checkout", "payment"}),
    "view_cart": frozenset({"checkout", "payment", "add_to_cart", "search"}),
    "remove": frozenset({"checkout", "payment", "add_to_cart", "search"}),
    "checkout": frozenset({"payment"}),
    "purchase": frozenset(),
    "unknown": frozenset(),
}

COMPLETION_BY_INTENT: dict[TaskIntent, str] = {
    "search": "Relevant products are visible for the requested query/constraints.",
    "compare": "Comparable products are visible with prices/ratings to choose from.",
    "add_to_cart": "Requested product(s) are verified in the cart.",
    "view_cart": "Cart page is open and cart contents are visible.",
    "checkout": "Checkout page or login gate before checkout is reached.",
    "purchase": "Purchase flow reached per policy (checkout or payment handoff).",
    "remove": "Requested item is no longer in the cart.",
    "unknown": "User clarification received.",
}


@dataclass(frozen=True)
class TaskSpec:
    raw: str
    intent: TaskIntent
    objective: str
    entities: tuple[str, ...] = ()
    quantity: int = 1
    budget_inr: float | None = None
    prefer_best: bool = False
    remove_target: str | None = None
    requires_checkout: bool = False
    actionable: bool = True
    clarification_reason: str = ""
    remaining_items: tuple[str, ...] = ()
    forbidden_actions: frozenset[str] = field(default_factory=frozenset)
    target_state: str = ""
    completion_conditions: tuple[str, ...] = ()

    def to_prompt_block(self) -> str:
        lines = [
            "TASK SPEC:",
            f"- intent: {self.intent}",
            f"- objective: {self.objective}",
            f"- target_state: {self.target_state}",
        ]
        if self.entities:
            lines.append(f"- entities: {', '.join(self.entities)}")
        if self.remaining_items:
            lines.append(f"- remaining_items: {', '.join(self.remaining_items)}")
        if self.quantity > 1:
            lines.append(f"- quantity: {self.quantity}")
        if self.budget_inr is not None:
            lines.append(f"- budget_inr: <= {self.budget_inr:.0f}")
        if self.prefer_best:
            lines.append("- prefer_best: true")
        if self.forbidden_actions:
            lines.append(
                f"- forbidden: {', '.join(sorted(self.forbidden_actions))}"
            )
        if self.completion_conditions:
            lines.append("- completion_when:")
            lines.extend(f"  • {c}" for c in self.completion_conditions)
        return "\n".join(lines)

    def summary(self) -> str:
        parts = [f"intent={self.intent}", f"qty={self.quantity}"]
        if self.entities:
            parts.append(f"entities={', '.join(self.entities)}")
        if self.budget_inr is not None:
            parts.append(f"budget_inr<={self.budget_inr:.0f}")
        if self.prefer_best:
            parts.append("prefer_best")
        if self.remove_target:
            parts.append(f"remove={self.remove_target}")
        return "; ".join(parts)
