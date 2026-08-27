"""Tests for structured shopping intent parsing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.product_compare import (  # noqa: E402
    normalize_product,
    parse_price,
    parse_rating,
    select_best_product,
)
from core.protocol import PageContext, PageProductSummary  # noqa: E402
from core.search_query import extract_search_query  # noqa: E402
from core.shopping_intent import parse_shopping_intent  # noqa: E402


def test_gucci_bag_intent() -> None:
    intent = parse_shopping_intent("help me buy a gucci bag at discounted price")
    assert "gucci" in intent.search_query
    assert "bag" in intent.search_query
    assert "help" not in intent.search_query
    assert "discounted" not in intent.search_query.split()
    assert intent.prefer_discount is True
    assert intent.brand == "gucci"


def test_cheapest_shampoo_intent() -> None:
    intent = parse_shopping_intent("Buy me the cheapest shampoo with good ratings")
    assert intent.search_query == "shampoo"
    assert intent.prefer_cheapest is True
    assert intent.min_rating == 4.0


def test_budget_intent() -> None:
    intent = parse_shopping_intent("find wireless headphones under ₹2000")
    assert "headphone" in intent.search_query or "wireless" in intent.search_query
    assert intent.budget_max == 2000
    assert intent.budget_currency == "INR"


def test_rejects_ok_go_garbage_in_query() -> None:
    query = extract_search_query("luggage bags ok go")
    assert "ok" not in query.split()
    assert "go" not in query.split()
    assert "luggage" in query or "bag" in query


def test_select_best_product_cheapest_with_rating() -> None:
    intent = parse_shopping_intent("cheapest shampoo with good ratings")
    page = PageContext(
        title="Search",
        url="http://localhost:3000/search?q=shampoo",
        products=[
            PageProductSummary(title="Fancy Shampoo", price_text="₹999", rating_text="3.2"),
            PageProductSummary(title="Budget Shampoo", price_text="₹289", rating_text="4.5"),
            PageProductSummary(title="Mid Shampoo", price_text="₹349", rating_text="4.4"),
        ],
    )
    winner, candidates, reason = select_best_product(page, intent)
    assert winner is not None
    assert winner.title == "Budget Shampoo"
    assert len(candidates) == 3
    assert "Selected" in reason


def test_select_best_ignores_missing_ratings() -> None:
    intent = parse_shopping_intent("cheapest shampoo with good ratings")
    page = PageContext(
        title="Search",
        url="http://localhost:3000/search?q=shampoo",
        products=[
            PageProductSummary(title="Fancy Shampoo", price_text="₹999"),
            PageProductSummary(title="Budget Shampoo", price_text="₹289"),
        ],
    )
    winner, _, reason = select_best_product(page, intent)
    assert winner is not None
    assert winner.title == "Budget Shampoo"
    assert "ratings not visible" in reason


def test_parse_price_and_rating() -> None:
    assert parse_price("₹349") == 349
    assert parse_price("$20.99") == 20.99
    assert parse_rating("4.4 out of 5") == 4.4
    product = normalize_product(
        PageProductSummary(title="X", price_text="₹425", rating_text="4.6 stars"),
    )
    assert product.price == 425
    assert product.rating == 4.6
