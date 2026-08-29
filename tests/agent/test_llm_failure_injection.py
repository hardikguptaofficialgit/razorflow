"""Planner output normalization and parse recovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_runtime.planner.llm_provider import _parse_planner_output  # noqa: E402


def test_normalize_search_input_role() -> None:
    raw = json.dumps(
        {
            "actions": [
                {
                    "type": "search",
                    "target": {"role": "search/input", "elementId": "e1"},
                    "parameters": {"query": "wireless earbuds"},
                    "reason": "search",
                    "expectedOutcome": "results",
                }
            ]
        }
    )
    plan = _parse_planner_output(raw)
    assert plan.actions[0].target is not None
    assert plan.actions[0].target.role == "search"


@pytest.mark.parametrize(
    "role,expected",
    [
        ("searchbox", "search"),
        ("textbox", "input"),
        ("button/link", "button"),
    ],
)
def test_normalize_role_aliases(role: str, expected: str) -> None:
    raw = json.dumps(
        {
            "actions": [
                {
                    "type": "click",
                    "target": {"role": role, "elementId": "e2"},
                    "reason": "click",
                    "expectedOutcome": "navigate",
                }
            ]
        }
    )
    plan = _parse_planner_output(raw)
    assert plan.actions[0].target is not None
    assert plan.actions[0].target.role == expected


def test_invalid_json_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_planner_output("not json at all")


def test_runtime_recovers_from_hallucinated_element_id() -> None:
    from unittest.mock import MagicMock

    sys.path.insert(0, str(ROOT / "agent-backend"))
    from agent_runtime.executor.actions import AgentAction, ElementTarget, PlannerOutput
    from agent_runtime.runtime import AgentRuntime
    from core.protocol import PageContext, PageElementSummary

    class _SeqLLM:
        def __init__(self) -> None:
            self.calls = 0

        def plan(self, system: str, user: str, *, screenshot_data_url: str | None = None) -> PlannerOutput:
            self.calls += 1
            if self.calls == 1:
                return PlannerOutput(
                    actions=[
                        AgentAction(
                            type="click",
                            target=ElementTarget(element_id="e9999", role="button", description="Add to cart"),
                            reason="bad id",
                            expectedOutcome="cart",
                        )
                    ]
                )
            return PlannerOutput(
                actions=[
                    AgentAction(
                        type="search",
                        target=ElementTarget(element_id="e1", role="search"),
                        parameters={"query": "earbuds"},
                        reason="search instead",
                        expectedOutcome="results",
                    )
                ]
            )

        def health_check(self) -> bool:
            return True

    page = PageContext(
        title="Home",
        url="http://localhost:3001/demo",
        elements=[
            PageElementSummary(index=1, role="search", tag="input", placeholder="Search products"),
        ],
        products=[],
    )
    llm = _SeqLLM()
    runtime = AgentRuntime(llm=llm)
    state = runtime.start_run("fail-1", "search earbuds", page)
    result = runtime.dispatch_next(state, page)
    assert result.kind == "continue"
    assert llm.calls >= 1
