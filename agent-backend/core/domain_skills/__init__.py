"""Domain-specific skills for the browser agent.

These are optional capabilities that can be enabled/disabled via configuration.
The core agent works without any domain skills - they provide specialized intelligence
for specific domains like e-commerce, form filling, etc.
"""

from __future__ import annotations

from .shopping_skill import ShoppingSkill

__all__ = ["ShoppingSkill"]
