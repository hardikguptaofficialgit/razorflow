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

# What browser state must be reached before the run can complete.
GoalPhase = Literal[
    "search_results",
    "product_details",
    "cart_updated",
    "cart_visible",
    "checkout",
    "checkout_reached",
    "purchase_reached",
    "item_removed",
]

FORBIDDEN_BY_PHASE: dict[GoalPhase, frozenset[str]] = {
    "search_results": frozenset(
        {"product_details", "add_to_cart", "checkout", "payment", "cart_nav"}
    ),
    "product_details": frozenset({"add_to_cart", "checkout", "payment", "cart_nav"}),
    "cart_updated": frozenset({"checkout", "payment"}),
    "cart_visible": frozenset({"checkout", "payment", "add_to_cart", "search"}),
    "checkout": frozenset({"payment", "search", "add_to_cart", "product_details"}),
    "checkout_reached": frozenset(
        {"payment", "search", "add_to_cart", "product_details"}
    ),
    "purchase_reached": frozenset(),
    "item_removed": frozenset({"checkout", "payment", "add_to_cart", "search"}),
}


def forbidden_for_phase(phase: GoalPhase) -> frozenset[str]:
    return FORBIDDEN_BY_PHASE.get(phase, frozenset())

COMPLETION_BY_PHASE: dict[GoalPhase, str] = {
    "search_results": "Relevant search results are visible; do not open product pages.",
    "product_details": "The selected product details page is open.",
    "cart_updated": "Requested product(s) are verified in the cart.",
    "cart_visible": "Cart page is open and cart contents are visible.",
    "checkout": "Navigate to checkout using a visible checkout control.",
    "checkout_reached": "Checkout page or login gate before checkout is reached.",
    "purchase_reached": "Purchase flow reached per policy.",
    "item_removed": "Requested item is no longer in the cart.",
}

# Legacy intent-level forbidden (merged with phase at parse time).
FORBIDDEN_BY_INTENT: dict[TaskIntent, frozenset[str]] = {
    "search": frozenset(),
    "compare": frozenset(),
    "add_to_cart": frozenset(),
    "view_cart": frozenset(),
    "remove": frozenset(),
    "checkout": frozenset(),
    "purchase": frozenset(),
    "unknown": frozenset(),
}


def phase_for_intent(intent: TaskIntent) -> GoalPhase:
    mapping: dict[TaskIntent, GoalPhase] = {
        "search": "search_results",
        "compare": "search_results",
        "add_to_cart": "cart_updated",
        "view_cart": "cart_visible",
        "checkout": "checkout",
        "purchase": "purchase_reached",
        "remove": "item_removed",
        "unknown": "search_results",
    }
    return mapping[intent]


@dataclass(frozen=True)
class TaskSpec:
    raw: str
    intent: TaskIntent
    objective: str
    target_phase: GoalPhase = "search_results"
    entities: tuple[str, ...] = ()
    quantity: int = 1
    budget_inr: float | None = None
    prefer_best: bool = False
    remove_target: str | None = None
    requires_checkout: bool = False
    allows_add_to_cart: bool = True
    actionable: bool = True
    clarification_reason: str = ""
    remaining_items: tuple[str, ...] = ()
    goal_phases: tuple[GoalPhase, ...] = ()
    forbidden_actions: frozenset[str] = field(default_factory=frozenset)
    target_state: str = ""
    completion_conditions: tuple[str, ...] = ()

    def effective_phases(self) -> tuple[GoalPhase, ...]:
        return self.goal_phases if self.goal_phases else (self.target_phase,)

    def to_prompt_block(self, *, current_phase: GoalPhase | None = None) -> str:
        phase = current_phase or self.target_phase
        phases = self.effective_phases()
        try:
            phase_index = phases.index(phase)
        except ValueError:
            phase_index = 0
        completed = phases[:phase_index]
        remaining = phases[phase_index:]
        lines = [
            "TASK SPEC:",
            f"- intent: {self.intent}",
            f"- current_phase: {phase}",
            f"- goal_phases: {' → '.join(phases)}",
        ]
        if completed:
            lines.append(f"- completed_phases: {', '.join(completed)}")
        if remaining:
            lines.append(f"- remaining_phases: {', '.join(remaining)}")
        lines.extend(
            [
                f"- objective: {self.objective}",
                f"- target_state: {COMPLETION_BY_PHASE.get(phase, self.target_state)}",
            ]
        )
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
        phase_forbidden = forbidden_for_phase(phase)
        if not self.allows_add_to_cart and phase not in {"checkout", "checkout_reached"}:
            phase_forbidden = phase_forbidden | frozenset(
                {"add_to_cart", "checkout", "payment"}
            )
        if phase_forbidden:
            lines.append(
                f"- forbidden_now: {', '.join(sorted(phase_forbidden))}"
            )
        if phase in {"checkout", "checkout_reached"} and self.requires_checkout:
            lines.append(
                "- checkout_allowed: true (use visible Checkout / Proceed to checkout controls)"
            )
        if not self.allows_add_to_cart:
            lines.append("- allows_add_to_cart: false (do NOT add items or checkout)")
        completion = COMPLETION_BY_PHASE.get(phase, self.target_state)
        if completion:
            lines.append("- completion_when:")
            lines.append(f"  • {completion}")
        return "\n".join(lines)

    def summary(self) -> str:
        parts = [
            f"intent={self.intent}",
            f"phase={self.target_phase}",
            f"qty={self.quantity}",
        ]
        if self.entities:
            parts.append(f"entities={', '.join(self.entities)}")
        if self.budget_inr is not None:
            parts.append(f"budget_inr<={self.budget_inr:.0f}")
        if self.prefer_best:
            parts.append("prefer_best")
        if self.remove_target:
            parts.append(f"remove={self.remove_target}")
        return "; ".join(parts)
