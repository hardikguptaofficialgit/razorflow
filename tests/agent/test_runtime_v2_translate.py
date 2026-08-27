"""Unit tests for V2 action translation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.executor.translate import translate_action


def test_click_translation() -> None:
    action = AgentAction(
        type="click",
        target=ElementTarget(elementId="e5", role="button", description="Add to cart"),
        reason="Add product",
        expectedOutcome="Cart updates",
    )
    steps = translate_action(action)
    assert len(steps) == 1
    assert steps[0].action == "click_element"
    assert steps[0].element_index == 5


def test_search_translation() -> None:
    action = AgentAction(
        type="search",
        target=ElementTarget(elementId="e2", role="search"),
        parameters={"query": "wireless earbuds"},
        reason="Search",
        expectedOutcome="Results visible",
    )
    steps = translate_action(action)
    assert len(steps) == 1
    assert steps[0].action == "type_in_element"
    assert steps[0].text == "wireless earbuds"
