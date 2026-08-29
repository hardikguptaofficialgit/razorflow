"""Resolve domain skill for a run."""

from __future__ import annotations

from agent_runtime.config import shopping_domain_enabled
from agent_runtime.domain.generic_skill import get_generic_skill
from agent_runtime.domain.protocol import DomainSkill
from agent_runtime.domain.shopping.skill import get_shopping_skill


def resolve_domain_skill(
    task: str,
    *,
    shopping_enabled: bool | None = None,
) -> DomainSkill:
    use_shopping = (
        shopping_domain_enabled()
        if shopping_enabled is None
        else shopping_enabled
    )
    if use_shopping:
        return get_shopping_skill()
    return get_generic_skill()
