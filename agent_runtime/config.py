"""Runtime configuration (env-driven, no shopping assumptions)."""

from __future__ import annotations

import os


def shopping_domain_enabled() -> bool:
    """When false, V2 uses the generic domain skill only."""
    raw = os.getenv("AGENT_SHOPPING_DOMAIN", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}
