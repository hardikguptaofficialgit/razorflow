"""Tests for goal-driven memory sync."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from agent_runtime.memory.sync import sync_memory_from_observation
from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.observation.browser_state import BrowserPage, ObservedCartLine
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parser import parse_task


def test_checkout_transitions_after_cart_has_items() -> None:
    from agent_runtime.task.parser import parse_task_with_spec

    parsed, spec = parse_task_with_spec("add snacks under ₹200 and checkout")
    state = RunState(
        run_id="t1",
        task=parsed.raw,
        parsed_task=parsed,
        task_spec=spec,
        current_phase=spec.target_phase,
        memory=TaskMemory(goal=parsed.goal, items_target=1),
    )
    page = BrowserPage(
        title="Cart",
        url="http://shop.example/cart",
        path="/cart",
        search_query="",
        cart_lines=[ObservedCartLine(title="Chips", quantity=1)],
        signals=["cart_page", "cart_items:1"],
    )
    sync_memory_from_observation(state, page)
    assert any("checkout" in w.lower() for w in state.memory.remaining_work)
