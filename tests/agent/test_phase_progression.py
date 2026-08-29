"""Multi-phase goal progression tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.observation.browser_state import BrowserPage, ObservedCartLine
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parse import parse_task_spec
from agent_runtime.task.parser import parse_task
from agent_runtime.task.phase_progression import try_advance_phase
from agent_runtime.policy.action_gate import filter_forbidden_actions
from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.verifier.goal import is_goal_satisfied


def _click(label: str) -> AgentAction:
    return AgentAction(
        type="click",
        target=ElementTarget(element_id="e1", role="button", description=label),
        reason=label,
        expectedOutcome="change",
    )


def test_add_and_checkout_parses_multi_phase() -> None:
    spec = parse_task_spec("add good snacks under ₹200 and checkout")
    assert spec.goal_phases == ("cart_updated", "checkout_reached")
    assert spec.target_phase == "cart_updated"
    assert "checkout" in spec.forbidden_actions


def test_add_only_stays_single_phase() -> None:
    spec = parse_task_spec("add good snacks under ₹200 to my cart")
    assert spec.goal_phases == ("cart_updated",)
    assert "checkout" in spec.forbidden_actions


def test_phase_advances_after_cart_verified() -> None:
    parsed = parse_task("add snacks under ₹200 and checkout")
    spec = parse_task_spec(parsed.raw)
    state = RunState(
        run_id="p1",
        task=parsed.raw,
        parsed_task=parsed,
        task_spec=spec,
        memory=TaskMemory(goal=parsed.goal, items_target=1),
        current_phase="cart_updated",
    )
    state.milestones.add("verified_add_to_cart")
    state.memory.items_added = 1
    page = BrowserPage(
        title="Home",
        url="http://shop.example/",
        path="/",
        search_query="",
        cart_lines=[ObservedCartLine(title="CrunchMix Masala Snacks 200g", quantity=1)],
    )
    assert try_advance_phase(state, page)
    assert state.current_phase == "checkout_reached"
    assert "ADD_PHASE_COMPLETE" in state.memory.constraints
    assert not is_goal_satisfied(state, page)


def test_checkout_phase_blocks_add_to_cart() -> None:
    spec = parse_task_spec("add snacks and checkout")
    allowed, blocked = filter_forbidden_actions(
        spec,
        [_click("Add to cart")],
        current_phase="checkout_reached",
    )
    assert not allowed
    assert blocked


def test_add_only_does_not_advance_to_checkout() -> None:
    parsed = parse_task("add good snacks under ₹200 to my cart")
    spec = parse_task_spec(parsed.raw)
    state = RunState(
        run_id="p2",
        task=parsed.raw,
        parsed_task=parsed,
        task_spec=spec,
        memory=TaskMemory(goal=parsed.goal, items_target=1),
        current_phase="cart_updated",
    )
    state.milestones.add("verified_add_to_cart")
    state.memory.items_added = 1
    page = BrowserPage(
        title="Home",
        url="http://shop.example/",
        path="/",
        search_query="",
        cart_lines=[ObservedCartLine(title="CrunchMix Masala Snacks 200g", quantity=1)],
    )
    assert not try_advance_phase(state, page)
    assert state.current_phase == "cart_updated"
    assert is_goal_satisfied(state, page)
