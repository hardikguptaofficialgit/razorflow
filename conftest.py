"""Root pytest hooks — test isolation for domain skills and shopping mode."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "agent-backend"

for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(autouse=True)
def _shopping_domain_isolation(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    """Keep AGENT_SHOPPING_DOMAIN deterministic across the suite."""
    module_name = getattr(request.module, "__name__", "")
    if module_name.endswith("test_generic_mode_runtime"):
        monkeypatch.setenv("AGENT_SHOPPING_DOMAIN", "false")
    else:
        monkeypatch.setenv("AGENT_SHOPPING_DOMAIN", "true")


@pytest.fixture(autouse=True)
def _reset_v1_shopping_skill() -> None:
    """Reset mutable singleton state mutated by customization tests."""
    try:
        from core.domain_skills.shopping_skill import get_shopping_skill

        get_shopping_skill().reset_url_patterns()
    except ImportError:
        pass
    yield
    try:
        from core.domain_skills.shopping_skill import get_shopping_skill

        get_shopping_skill().reset_url_patterns()
    except ImportError:
        pass
