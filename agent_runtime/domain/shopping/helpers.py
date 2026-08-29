"""Access shopping fields stored in generic TaskSpec.metadata."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from agent_runtime.task.spec import TaskSpec

if TYPE_CHECKING:
    from agent_runtime.state.run_state import RunState


def shopping_intent(spec: TaskSpec | None) -> str:
    if spec is None:
        return "unknown"
    return str(spec.metadata.get("intent", spec.goal))


def allows_add_to_cart(spec: TaskSpec | None) -> bool:
    if spec is None:
        return False
    return bool(spec.metadata.get("allows_add_to_cart", True))


def requires_checkout(spec: TaskSpec | None) -> bool:
    if spec is None:
        return False
    return bool(spec.metadata.get("requires_checkout", False))


def prefer_best(spec: TaskSpec | None) -> bool:
    if spec is None:
        return False
    return bool(spec.metadata.get("prefer_best", False))


def budget_inr(spec: TaskSpec | None) -> float | None:
    if spec is None:
        return None
    value = spec.metadata.get("budget_inr")
    return float(value) if value is not None else None


def remove_target(spec: TaskSpec | None) -> str | None:
    if spec is None:
        return None
    raw = spec.metadata.get("remove_target")
    return str(raw) if raw else None


def pack_shopping_metadata(**fields: Any) -> dict[str, Any]:
    base = {"domain": "shopping"}
    base.update({k: v for k, v in fields.items() if v is not None or k in {
        "allows_add_to_cart",
        "requires_checkout",
        "prefer_best",
    }})
    return base


def multi_distinct_item_goal(state: "RunState") -> bool:
    """True when the user asked for multiple different products (not same-SKU qty)."""
    hints = state.parsed_task.product_hints
    if len(hints) >= 2:
        return True
    spec = state.task_spec
    if spec and len(spec.entities) >= 2:
        return True
    if spec and len(spec.remaining_items) >= 2:
        return True
    return False


def goal_item_phrase(item: str) -> str:
    """Strip leading quantity from hints like '2 snacks' -> 'snacks'."""
    stripped = re.sub(r"^\d+\s+", "", item.strip())
    return stripped or item.strip()
