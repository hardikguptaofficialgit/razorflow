"""Unit tests for Agent Runtime V2 task parser."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from agent_runtime.task.parser import parse_task


def test_gibberish_needs_clarification() -> None:
    parsed = parse_task("wdwd")
    assert parsed.actionable is False
    assert parsed.goal == "unknown"


def test_search_earbuds_budget() -> None:
    parsed = parse_task("find the best wireless earbuds under ₹6000")
    assert parsed.actionable is True
    assert parsed.goal in {"search", "add_to_cart", "compare"}
    assert parsed.budget_inr == 6000
    assert parsed.prefer_best is True


def test_multi_item_buy_list() -> None:
    parsed = parse_task("buy me amul butter, chips, cooker")
    assert parsed.goal == "add_to_cart"
    assert parsed.item_count >= 2
    assert len(parsed.product_hints) >= 2


def test_single_item_buy_me_is_add_to_cart() -> None:
    parsed = parse_task("buy me a shampoo")
    assert parsed.goal == "add_to_cart"
    assert parsed.actionable is True
    assert parsed.product_hints[0].lower() == "shampoo"


def test_vague_buy_something_needs_clarification() -> None:
    parsed = parse_task("see i want to buy something")
    assert parsed.actionable is False
    assert parsed.goal == "unknown"


def test_checkout_task() -> None:
    parsed = parse_task("add snacks under ₹200 and checkout")
    assert parsed.goal == "checkout"
    assert parsed.requires_checkout is True
