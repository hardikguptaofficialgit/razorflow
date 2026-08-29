"""Completion verification — verifier owns DONE, not the LLM."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.observation.browser_state import (
    BrowserPage,
    ObservedElement,
    ObservedProduct,
)
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parse import parse_task_spec
from agent_runtime.task.parser import parse_task
from agent_runtime.verifier.goal import approve_completion, is_goal_satisfied


def _state(task: str) -> RunState:
    parsed = parse_task(task)
    spec = parse_task_spec(task)
    return RunState(
        run_id="t",
        task=task,
        parsed_task=parsed,
        task_spec=spec,
        memory=TaskMemory(goal=parsed.goal),
    )


def test_false_done_search_still_on_home() -> None:
    state = _state("search for wireless earbuds")
    page = BrowserPage(
        title="Home",
        url="http://localhost:3001/demo",
        path="/demo",
        search_query="",
        elements=[],
        products=[],
        cart_lines=[],
    )
    assert not is_goal_satisfied(state, page)
    assert not approve_completion(state, page, source="llm_proposal")


def test_true_done_search_on_results() -> None:
    state = _state("search for wireless earbuds")
    state.milestones.add("verified_search")
    page = BrowserPage(
        title="Search",
        url="http://localhost:3001/demo/search?q=earbuds",
        path="/search",
        search_query="earbuds",
        elements=[],
        products=[ObservedProduct("p1", "Galaxy Buds FE", "₹4999", "", "e5", "e6")],
        cart_lines=[],
        signals=["search_results"],
    )
    assert is_goal_satisfied(state, page)
    assert approve_completion(state, page, source="goal_check")


def test_search_completes_passively_when_results_already_visible() -> None:
    from agent_runtime.domain.shopping.search_state import bootstrap_passive_search_progress

    state = _state("search for shampoo under ₹300")
    page = BrowserPage(
        title="Search",
        url="http://localhost:3001/demo/search?q=shampoo",
        path="/demo/search",
        search_query="shampoo",
        elements=[],
        products=[
            ObservedProduct("p1", "Herbal Glow Shampoo 400ml", "₹299", "", "e5", "e6"),
            ObservedProduct("p2", "Head & Shoulders Shampoo", "₹349", "", "e7", "e8"),
        ],
        cart_lines=[],
        signals=["search_results"],
    )
    assert "verified_search" not in state.milestones
    assert bootstrap_passive_search_progress(state, page)
    assert is_goal_satisfied(state, page)
    assert approve_completion(state, page, source="pre_plan")


def test_search_auto_adds_single_result_within_budget() -> None:
    from agent_runtime.domain.registry import resolve_domain_skill

    state = _state("search for shampoo under ₹300")
    state.bind_skill(resolve_domain_skill(state.task))
    page = BrowserPage(
        title="Search",
        url="http://localhost:3001/demo/search?q=shampoo",
        path="/demo/search",
        search_query="shampoo",
        elements=[
            ObservedElement(
                element_id="e5",
                index=5,
                role="button",
                tag="button",
                text="Add to cart",
                placeholder="",
                aria_label="Add Herbal Glow Shampoo",
                clickable=True,
            )
        ],
        products=[
            ObservedProduct("p1", "Head & Shoulders Shampoo", "₹349", "", "e4"),
            ObservedProduct("p2", "Herbal Glow Shampoo 400ml", "₹299", "", "e5"),
        ],
        cart_lines=[],
        signals=["search_results"],
    )

    action = state.skill().auto_add_single_budget_match(state, page)

    assert action is not None
    assert action.target is not None
    assert action.target.element_id == "e5"


def test_llm_continue_but_goal_already_met() -> None:
    state = _state("open my cart")
    page = BrowserPage(
        title="Cart",
        url="http://localhost:3001/demo/cart",
        path="/cart",
        search_query="",
        elements=[],
        products=[],
        cart_lines=[],
        signals=["cart_visible"],
    )
    assert is_goal_satisfied(state, page)


def test_add_to_cart_not_done_on_search_page() -> None:
    state = _state("add good snacks under ₹200 to my cart")
    page = BrowserPage(
        title="Search",
        url="http://localhost:3001/demo/search?q=snacks",
        path="/search",
        search_query="snacks",
        elements=[],
        products=[ObservedProduct("p1", "Chips", "₹20", "", "e2", "e3")],
        cart_lines=[],
        signals=["search_results"],
    )
    assert not is_goal_satisfied(state, page)
