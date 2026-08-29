"""Adversarial parser and goal-boundary tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_runtime.task.parse import parse_task_spec

NL_SEARCH_VARIANTS = [
    "find wireless earbuds",
    "look for wireless earbuds",
    "I need wireless earbuds",
    "show me wireless earbuds",
    "can you find me some wireless earbuds",
    "search for earbuds",
    "find me good earbuds below 6000",
    "get me earbuds under ₹6000",
]


def test_nl_search_variants() -> None:
    for task in NL_SEARCH_VARIANTS:
        spec = parse_task_spec(task)
        assert spec.intent in {"search", "compare"}, task
        assert spec.target_phase == "search_results", task
        assert "product_details" in spec.forbidden_actions, task


def test_search_only_find_earbuds() -> None:
    spec = parse_task_spec("find earbuds")
    assert spec.intent == "search"
    assert spec.target_phase == "search_results"
    assert "add_to_cart" in spec.forbidden_actions


def test_find_and_show_best() -> None:
    spec = parse_task_spec("find earbuds and show me the best one")
    assert spec.target_phase == "product_details"
    assert "add_to_cart" in spec.forbidden_actions


def test_find_and_add() -> None:
    spec = parse_task_spec("find earbuds and add the best one to my cart")
    assert spec.intent == "add_to_cart"
    assert spec.target_phase == "cart_updated"


def test_add_to_cart_boundary() -> None:
    spec = parse_task_spec("add earbuds to my cart")
    assert spec.intent == "add_to_cart"
    assert "checkout" in spec.forbidden_actions


def test_view_cart_boundary() -> None:
    spec = parse_task_spec("open my cart")
    assert spec.intent == "view_cart"
    assert spec.target_phase == "cart_visible"
    assert "search" in spec.forbidden_actions


def test_clear_cart_is_not_search() -> None:
    spec = parse_task_spec("see clear all my things in the cart")
    assert spec.intent == "remove"
    assert spec.metadata["remove_target"] == "all"
    assert spec.metadata["clear_cart"] is True
    assert spec.target_phase == "item_removed"


def test_checkout_boundary() -> None:
    spec = parse_task_spec("checkout")
    assert spec.intent == "checkout"
    assert spec.target_phase == "checkout"


def test_checkout_negation_is_not_an_instruction_to_checkout() -> None:
    for task in (
        "I am not doing checkout",
        "yeah I was thinking ofnot doing checkout",
        "don't proceed to checkout",
    ):
        spec = parse_task_spec(task)
        assert spec.actionable is False, task
        assert spec.intent == "unknown", task
        assert spec.requires_checkout is False, task


def test_add_without_checkout_stays_add_only() -> None:
    spec = parse_task_spec("add NovaTrack watch to my cart, not checkout")
    assert spec.intent == "add_to_cart"
    assert spec.requires_checkout is False
    assert spec.target_phase == "cart_updated"


def test_buy_purchase_boundary() -> None:
    spec = parse_task_spec("buy earbuds")
    assert spec.intent == "purchase"
    assert spec.target_phase == "purchase_reached"


def test_task2_earbuds_budget() -> None:
    spec = parse_task_spec("find me good wireless earbuds under ₹6000")
    assert spec.intent == "search"
    assert spec.target_phase == "search_results"
    assert spec.budget_inr == 6000
    assert spec.entities[0] == "wireless earbuds"
    assert "product_details" in spec.forbidden_actions


def test_multi_objective_find_two() -> None:
    spec = parse_task_spec("find earbuds and a smartwatch")
    assert spec.intent == "search"
    assert len(spec.entities) >= 2


def test_multi_objective_add_three() -> None:
    spec = parse_task_spec("add butter, chips and cooker")
    assert spec.intent == "add_to_cart"
    assert len(spec.remaining_items) == 3
