"""Tests for page fingerprint and stale-page safeguards."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.page_cart import header_cart_item_count
from core.protocol import (
    ClickElementStep,
    PageContext,
    PageElementSummary,
    PageProductSummary,
)
from core.run_manager import RunManager, page_fingerprint


def _home_page(cart_count: int = 0) -> PageContext:
    elements = [
        PageElementSummary(
            index=1,
            role="link",
            tag="a",
            text="Cart",
            aria_label=f"Cart, {cart_count} items",
        ),
        PageElementSummary(
            index=2,
            role="button",
            tag="button",
            text="Add to cart",
        ),
    ]
    products = [
        PageProductSummary(
            title="Head & Shoulders Anti-Dandruff Shampoo 340ml",
            price_text="₹349",
            add_to_cart_element_index=2,
        ),
    ]
    return PageContext(title="Fake Store", url="http://localhost:3001/", elements=elements, products=products)


def test_page_fingerprint_changes_when_cart_count_changes() -> None:
    before = page_fingerprint(_home_page(cart_count=2))
    after = page_fingerprint(_home_page(cart_count=3))
    assert before != after
    assert "cart:3" in (after or "")


def test_header_cart_item_count_from_aria_label() -> None:
    assert header_cart_item_count(_home_page(cart_count=8)) == 8


def test_verified_add_to_cart_does_not_trigger_stale_failure() -> None:
    manager = RunManager()
    session = manager.start_run("run-1", "buy me a shampoo", _home_page(cart_count=2))
    step = ClickElementStep(action="click_element", role="button", match_text="Add to cart")

    for _ in range(6):
        manager.record_action_result(
            session,
            step,
            success=True,
            error=None,
            page_context=_home_page(cart_count=2),
            verified=True,
        )

    assert manager.check_safeguards(session) is None
