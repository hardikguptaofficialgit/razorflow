"""Completion verification — verifier owns DONE, not the LLM."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.observation.browser_state import BrowserPage, ObservedProduct
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
