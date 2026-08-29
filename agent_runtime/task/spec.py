"""Explicit domain-agnostic task representation for the agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskSpec:
    """Generic task spec — no commerce/checkout vocabulary."""

    raw: str
    goal: str
    objective: str
    target_phase: str = "complete"
    entities: tuple[str, ...] = ()
    quantity: int = 1
    actionable: bool = True
    clarification_reason: str = ""
    remaining_items: tuple[str, ...] = ()
    goal_phases: tuple[str, ...] = ()
    forbidden_actions: frozenset[str] = field(default_factory=frozenset)
    target_state: str = ""
    completion_conditions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def intent(self) -> str:
        """Backward-compatible alias used by legacy call sites."""
        return str(self.metadata.get("intent", self.goal))

    @property
    def allows_add_to_cart(self) -> bool:
        return bool(self.metadata.get("allows_add_to_cart", True))

    @property
    def requires_checkout(self) -> bool:
        return bool(self.metadata.get("requires_checkout", False))

    @property
    def budget_inr(self) -> float | None:
        value = self.metadata.get("budget_inr")
        return float(value) if value is not None else None

    @property
    def prefer_best(self) -> bool:
        return bool(self.metadata.get("prefer_best", False))

    def effective_phases(self) -> tuple[str, ...]:
        return self.goal_phases if self.goal_phases else (self.target_phase,)

    def to_prompt_block(self, *, current_phase: str | None = None) -> str:
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
            f"- goal: {self.goal}",
            f"- current_phase: {phase}",
            f"- goal_phases: {' → '.join(phases)}",
        ]
        if completed:
            lines.append(f"- completed_phases: {', '.join(completed)}")
        if remaining:
            lines.append(f"- remaining_phases: {', '.join(remaining)}")
        lines.append(f"- objective: {self.objective}")
        if self.target_state:
            lines.append(f"- target_state: {self.target_state}")
        if self.entities:
            lines.append(f"- entities: {', '.join(self.entities)}")
        if self.remaining_items:
            lines.append(f"- remaining_items: {', '.join(self.remaining_items)}")
        if self.quantity > 1:
            lines.append(f"- quantity: {self.quantity}")
        forbidden = self.forbidden_actions
        if self.metadata.get("domain") == "shopping":
            from agent_runtime.domain.shopping.spec import forbidden_for_phase

            forbidden = forbidden_for_phase(phase)  # type: ignore[arg-type]
            if phase in {"checkout", "checkout_reached"}:
                lines.append("- checkout_allowed: true")
        if forbidden:
            lines.append(f"- forbidden_now: {', '.join(sorted(forbidden))}")
        if self.completion_conditions:
            lines.append("- completion_when:")
            for item in self.completion_conditions:
                lines.append(f"  • {item}")
        return "\n".join(lines)

    def summary(self) -> str:
        parts = [f"goal={self.goal}", f"phase={self.target_phase}", f"qty={self.quantity}"]
        if self.entities:
            parts.append(f"entities={', '.join(self.entities)}")
        return "; ".join(parts)
