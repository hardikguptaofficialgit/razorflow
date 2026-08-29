"""Forbidden-action and completion verifier adversarial tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.observation.browser_state import BrowserPage, ObservedProduct
from agent_runtime.policy.action_gate import classify_action, filter_forbidden_actions
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parse import parse_task_spec
from agent_runtime.verifier.goal import approve_completion, is_goal_satisfied
from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.task.parser import parse_task


def _click(label: str, *, role: str = "button", element_id: str = "e1") -> AgentAction:
    return AgentAction(
        type="click",
        target=ElementTarget(element_id=element_id, role=role, description=label),
        reason=label,
        expectedOutcome="change",
    )


def test_search_forbids_product_click() -> None:
    spec = parse_task_spec("find earbuds")
    allowed, blocked = filter_forbidden_actions(
        spec, [_click("Samsung Galaxy Buds", role="link")]
    )
    assert not allowed
    assert blocked


def test_search_forbids_add_to_cart() -> None:
    spec = parse_task_spec("find earbuds")
    allowed, blocked = filter_forbidden_actions(spec, [_click("Add to cart")])
    assert not allowed
    assert blocked


def test_search_forbids_checkout() -> None:
    spec = parse_task_spec("find earbuds")
    action = AgentAction(
        type="navigate",
        parameters={"url": "/checkout"},
        reason="go checkout",
        expectedOutcome="checkout",
    )
    allowed, blocked = filter_forbidden_actions(spec, [action])
    assert not allowed


def test_add_forbids_checkout() -> None:
    spec = parse_task_spec("add snacks to my cart")
    action = AgentAction(
        type="click",
        target=ElementTarget(element_id="e2", role="button", description="Proceed to checkout"),
        reason="checkout",
        expectedOutcome="checkout",
    )
    allowed, _ = filter_forbidden_actions(spec, [action])
    assert not allowed


def test_verifier_search_complete_on_results_not_product_page() -> None:
    parsed = parse_task("find earbuds")
    spec = parse_task_spec("find earbuds")
    state = RunState(
        run_id="t",
        task=parsed.raw,
        parsed_task=parsed,
        task_spec=spec,
        memory=TaskMemory(goal="search"),
    )
    state.milestones.add("verified_search")
    search_page = BrowserPage(
        title="Search",
        url="http://shop.example/search?q=earbuds",
        path="/search",
        search_query="earbuds",
        products=[ObservedProduct("p1", "Buds", "₹999", "", "e2", "e3")],
    )
    assert is_goal_satisfied(state, search_page)
    assert approve_completion(state, search_page, source="test")

    product_page = BrowserPage(
        title="Product",
        url="http://shop.example/product/buds",
        path="/product/buds",
        search_query="",
        products=[],
    )
    state.milestones.add("verified_search")
    assert not is_goal_satisfied(state, product_page)


def test_verifier_rejects_llm_done_prematurely() -> None:
    parsed = parse_task("add snacks to cart")
    spec = parse_task_spec(parsed.raw)
    state = RunState(
        run_id="t2",
        task=parsed.raw,
        parsed_task=parsed,
        task_spec=spec,
        memory=TaskMemory(goal="add_to_cart", items_target=1),
    )
    page = BrowserPage(
        title="Home",
        url="http://shop.example/",
        path="/",
        search_query="",
        products=[],
        cart_lines=[],
    )
    assert not approve_completion(state, page, source="llm_proposal")


def test_classify_product_details() -> None:
    cats = classify_action(_click("Galaxy Buds FE", role="link"))
    assert "product_details" in cats
