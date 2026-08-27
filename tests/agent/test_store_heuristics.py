"""Heuristic planner tests for RazorFlow Market pages."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.heuristics import try_heuristic_plan  # noqa: E402
from core.protocol import PageContext, PageElementSummary, PageProductSummary  # noqa: E402
from core.run_manager import RunSession  # noqa: E402


def _search_page() -> PageContext:
    return PageContext(
        title="Search",
        url="http://localhost:3000/search?q=shampoo",
        elements=[
            PageElementSummary(
                index=1,
                role="button",
                tag="button",
                text="Add to cart",
                placeholder="",
                aria_label="",
            ),
            PageElementSummary(
                index=2,
                role="link",
                tag="a",
                text="Cart",
                placeholder="",
                aria_label="Cart, 0 items",
            ),
        ],
        products=[
            PageProductSummary(
                title="Head & Shoulders Shampoo",
                price_text="₹349",
                add_to_cart_element_index=1,
                element_index=1,
            ),
        ],
    )


def test_heuristic_adds_cheapest_product_from_search() -> None:
    session = RunSession(
        run_id="h-1",
        task="Buy the cheapest shampoo under 500",
        latest_page_context=_search_page(),
    )
    chunk = try_heuristic_plan(session)
    assert chunk is not None
    assert chunk.steps[0].action == "click_element"
    assert chunk.steps[0].match_text == "add to cart"


def test_heuristic_opens_cart_after_add() -> None:
    from core.protocol import ActionHistoryEntry, ClickElementStep

    session = RunSession(
        run_id="h-2",
        task="Buy shampoo",
        latest_page_context=PageContext(
            title="Product",
            url="http://localhost:3000/product/prod-001",
            elements=[
                PageElementSummary(
                    index=1,
                    role="button",
                    tag="button",
                    text="Add to cart",
                    placeholder="",
                    aria_label="",
                ),
                PageElementSummary(
                    index=2,
                    role="link",
                    tag="a",
                    text="Cart",
                    placeholder="",
                    aria_label="Cart, 1 items",
                ),
            ],
            products=[],
        ),
    )
    session.history.append(
        ActionHistoryEntry(
            step=ClickElementStep(
                action="click_element",
                role="button",
                element_index=1,
                match_text="add to cart",
            ),
            success=True,
            error=None,
            page_fingerprint=None,
        ),
    )
    chunk = try_heuristic_plan(session)
    assert chunk is not None
    assert chunk.steps[0].action == "click_element"
    assert chunk.steps[0].match_text == "cart"


def test_heuristic_prefers_cheapest_shampoo_title_match() -> None:
    session = RunSession(
        run_id="h-3",
        task="Buy the cheapest shampoo under 500",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3000/search?q=shampoo",
            elements=[
                PageElementSummary(
                    index=1,
                    role="button",
                    tag="button",
                    text="Add to cart",
                    placeholder="",
                    aria_label="",
                ),
                PageElementSummary(
                    index=2,
                    role="button",
                    tag="button",
                    text="Add to cart",
                    placeholder="",
                    aria_label="",
                ),
            ],
            products=[
                PageProductSummary(
                    title="Patanjali Aloe Vera Gel 150ml",
                    price_text="₹120",
                    add_to_cart_element_index=1,
                ),
                PageProductSummary(
                    title="Sunsilk Thick & Long Shampoo 180ml",
                    price_text="₹289",
                    add_to_cart_element_index=2,
                ),
            ],
        ),
    )
    chunk = try_heuristic_plan(session)
    assert chunk is not None
    assert chunk.steps[0].element_index == 2


def test_heuristic_does_not_shop_from_homepage_grid() -> None:
    session = RunSession(
        run_id="h-4",
        task="Buy the cheapest shampoo under 500",
        latest_page_context=PageContext(
            title="Razorflow Market",
            url="http://localhost:3000/",
            elements=[
                PageElementSummary(
                    index=1,
                    role="search",
                    tag="input",
                    text="",
                    placeholder="Search products",
                    aria_label="Search products",
                ),
                PageElementSummary(
                    index=2,
                    role="button",
                    tag="button",
                    text="Add to cart",
                    placeholder="",
                    aria_label="",
                ),
            ],
            products=[
                PageProductSummary(
                    title="Lay's Classic Salted Chips 52g",
                    price_text="₹20",
                    add_to_cart_element_index=2,
                ),
            ],
        ),
    )
    chunk = try_heuristic_plan(session)
    assert chunk is not None
    assert chunk.steps[0].action == "type_in_element"
