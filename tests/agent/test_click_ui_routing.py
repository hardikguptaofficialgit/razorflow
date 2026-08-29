"""Click-only tasks use generic skill — not shopping search workflow."""

from __future__ import annotations

from agent_runtime.domain.registry import resolve_domain_skill
from agent_runtime.task.parser import parse_task_with_spec


def test_click_task_uses_generic_skill() -> None:
    skill = resolve_domain_skill("click the Submit order button")
    assert skill.skill_id == "generic"


def test_shopping_add_still_uses_shopping_skill() -> None:
    skill = resolve_domain_skill("add a watch and earbuds to my cart")
    assert skill.skill_id == "shopping"


def test_inspect_and_add_single_entity() -> None:
    task = "find snacks under ₹200, inspect the results, and add the best one to my cart"
    _, spec = parse_task_with_spec(task)
    assert len(spec.entities) == 1
    assert "snack" in spec.entities[0].lower()
