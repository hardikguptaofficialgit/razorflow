"""Agent Runtime V2 loop tests with mocked LLM."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from agent_runtime.executor.actions import AgentAction, ElementTarget, PlannerOutput
from agent_runtime.runtime import AgentRuntime
from core.protocol import PageContext, PageElementSummary, PageProductSummary


class _FakeLLM:
    def __init__(self, outputs: list[PlannerOutput]) -> None:
        self._outputs = outputs
        self._index = 0

    def plan(self, system: str, user: str, *, screenshot_data_url: str | None = None) -> PlannerOutput:
        output = self._outputs[min(self._index, len(self._outputs) - 1)]
        self._index += 1
        return output

    def health_check(self) -> bool:
        return True


def _home_page() -> PageContext:
    return PageContext(
        title="Store",
        url="http://localhost:3001/",
        elements=[
            PageElementSummary(
                index=1,
                role="search",
                tag="input",
                placeholder="Search products",
            ),
            PageElementSummary(index=2, role="button", tag="button", text="Search"),
        ],
        products=[],
    )


def _search_page() -> PageContext:
    return PageContext(
        title="Search",
        url="http://localhost:3001/search?q=earbuds",
        elements=[],
        products=[
            PageProductSummary(
                title="Galaxy Buds FE",
                priceText="₹4999",
                addToCartElementIndex=5,
            ),
        ],
    )


def test_runtime_dispatches_llm_action() -> None:
    llm = _FakeLLM(
        [
            PlannerOutput(
                actions=[
                    AgentAction(
                        type="search",
                        target=ElementTarget(elementId="e1", role="search"),
                        parameters={"query": "wireless earbuds"},
                        reason="User wants earbuds",
                        expectedOutcome="Search results",
                    )
                ]
            )
        ]
    )
    runtime = AgentRuntime(llm=llm)
    state = runtime.start_run("run-1", "search for wireless earbuds", _home_page())
    result = runtime.dispatch_next(state, _home_page())
    assert result.kind == "continue"
    assert len(result.steps) == 1
    assert result.steps[0].action == "type_in_element"


def test_runtime_rejects_fake_finish() -> None:
    llm = _FakeLLM(
        [
            PlannerOutput(
                actions=[],
                proposeFinish=True,
            ),
            PlannerOutput(
                actions=[
                    AgentAction(
                        type="click",
                        target=ElementTarget(elementId="e5", role="button", description="Add to cart"),
                        reason="Add",
                        expectedOutcome="Cart grows",
                    )
                ],
            ),
        ]
    )
    runtime = AgentRuntime(llm=llm)
    state = runtime.start_run("run-2", "add snacks", _search_page())
    result = runtime.dispatch_next(state, _search_page())
    assert result.kind == "continue"
