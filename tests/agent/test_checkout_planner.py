"""Checkout-phase planner regression tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from agent_runtime.executor.actions import AgentAction, ElementTarget, PlannerOutput
from agent_runtime.observation.browser_state import BrowserPage, ObservedCartLine, ObservedElement
from agent_runtime.planner.context import build_observation_block
from agent_runtime.planner.planner import LLMPlanner
from agent_runtime.runtime import AgentRuntime
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parse import parse_task_spec
from agent_runtime.task.parser import parse_task
from agent_runtime.memory.task_memory import TaskMemory
from core.protocol import PageContext, PageElementSummary


class _FakeLLM:
    def __init__(self, outputs: list[PlannerOutput]) -> None:
        self._outputs = outputs
        self._index = 0
        self.prompts: list[str] = []

    def plan(
        self,
        system: str,
        user: str,
        *,
        screenshot_data_url: str | None = None,
        run_config=None,
        **_: object,
    ) -> PlannerOutput:
        self.prompts.append(user)
        output = self._outputs[min(self._index, len(self._outputs) - 1)]
        self._index += 1
        return output

    def health_check(self) -> bool:
        return True


def _cart_page_context() -> PageContext:
    return PageContext(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        elements=[
            PageElementSummary(
                index=1,
                role="link",
                tag="a",
                text="Proceed to checkout",
                href="/demo/checkout",
            ),
            PageElementSummary(
                index=2,
                role="link",
                tag="a",
                text="Continue shopping",
                href="/demo/search",
            ),
        ],
        cart_lines=[],
    )


def _checkout_state() -> RunState:
    parsed = parse_task("add snacks under ₹200 and checkout")
    spec = parse_task_spec(parsed.raw)
    return RunState(
        run_id="checkout-1",
        task=parsed.raw,
        parsed_task=parsed,
        task_spec=spec,
        memory=TaskMemory(
            goal=parsed.goal,
            items_target=1,
            items_added=1,
            constraints=["ADD_PHASE_COMPLETE"],
        ),
        current_phase="checkout",
        completed_phases=["cart_updated"],
        milestones={"verified_add_to_cart", "reached_cart"},
    )


def test_observation_exposes_checkout_control_on_cart_page() -> None:
    state = _checkout_state()
    page = BrowserPage(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        path="/demo/cart",
        search_query="",
        cart_lines=[ObservedCartLine(title="Lay's", quantity=1)],
        elements=[
            ObservedElement(
                element_id="e1",
                index=1,
                role="link",
                tag="a",
                text="Proceed to checkout",
                placeholder="",
                aria_label="",
                href="/demo/checkout",
                clickable=True,
            )
        ],
        signals=["cart_page"],
    )
    block = build_observation_block(state, page)
    assert "CURRENT PHASE: checkout" in block
    assert "Checkout-capable controls" in block
    assert "Proceed to checkout" in block
    assert "e1" in block


def test_planner_produces_checkout_action_on_cart_page() -> None:
    state = _checkout_state()
    page = BrowserPage(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        path="/demo/cart",
        search_query="",
        cart_lines=[ObservedCartLine(title="Lay's", quantity=1)],
        elements=[
            ObservedElement(
                element_id="e1",
                index=1,
                role="link",
                tag="a",
                text="Proceed to checkout",
                placeholder="",
                aria_label="",
                href="/demo/checkout",
                clickable=True,
            )
        ],
        signals=["cart_page"],
    )
    llm = _FakeLLM(
        [
            PlannerOutput(
                actions=[
                    AgentAction(
                        type="click",
                        target=ElementTarget(
                            element_id="e1",
                            role="link",
                            description="Proceed to checkout",
                        ),
                        reason="Navigate to checkout",
                        expectedOutcome="Checkout page opens",
                    )
                ]
            )
        ]
    )
    planner = LLMPlanner(llm)
    output = planner.plan(state, page)
    assert output.actions
    assert output.actions[0].target is not None
    assert output.actions[0].target.element_id == "e1"


def test_runtime_recovers_from_empty_plan_at_checkout() -> None:
    llm = _FakeLLM(
        [
            PlannerOutput(actions=[]),
            PlannerOutput(
                actions=[
                    AgentAction(
                        type="click",
                        target=ElementTarget(
                            element_id="e1",
                            role="link",
                            description="Proceed to checkout",
                        ),
                        reason="Open checkout",
                        expectedOutcome="Checkout page",
                    )
                ]
            ),
        ]
    )
    runtime = AgentRuntime(llm=llm)
    state = runtime.start_run(
        "checkout-recovery",
        "add snacks under ₹200 and checkout",
        _cart_page_context(),
    )
    state.current_phase = "checkout"
    state.completed_phases = ["cart_updated"]
    state.memory.items_added = 1
    state.memory.constraints.append("ADD_PHASE_COMPLETE")
    state.milestones.update({"verified_add_to_cart", "reached_cart"})

    result = runtime.dispatch_next(state, _cart_page_context())
    assert result.kind == "continue"
    assert len(result.steps) == 1
    assert state.metrics.get("empty_plan_count") == 1
    assert state.metrics.get("llm_calls", 0) >= 2
    assert "CURRENT PHASE (checkout)" in llm.prompts[-1]
