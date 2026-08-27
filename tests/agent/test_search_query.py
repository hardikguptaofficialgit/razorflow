"""Tests for conversational → short search-query extraction."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.search_query import extract_search_query, looks_like_chatty_search  # noqa: E402


def test_extracts_dresses_from_chatty_goal() -> None:
    query = extract_search_query(
        "hey , can u help me find some good and dresses for my party tonight , and add to"
    )
    assert "hey" not in query
    assert "help" not in query
    assert "dresses" in query or "party" in query
    assert len(query.split()) <= 4


def test_extracts_shampoo_from_constraint_goal() -> None:
    query = extract_search_query("Buy me the cheapest shampoo with good ratings")
    assert query == "shampoo"


def test_extracts_chocolates() -> None:
    query = extract_search_query("find cheapest chocolates with good ratings")
    assert "chocolate" in query


def test_extracts_gucci_bag() -> None:
    query = extract_search_query("help me buy a gucci bag at discounted price")
    assert "gucci" in query
    assert "bag" in query
    assert "help" not in query
    assert len(query.split()) <= 4


def test_strips_ok_go_noise() -> None:
    query = extract_search_query("luggage bags ok go")
    assert "ok" not in query.split()
    assert "go" not in query.split()


def test_extracts_wireless_earbud_goal() -> None:
    query = extract_search_query("best wireless earbud under 6k")
    assert query == "earbuds"
    assert "6k" not in query
    assert "wireless" not in query


def test_search_queries_equivalent_earbud_variants() -> None:
    from core.search_query import search_queries_equivalent

    assert search_queries_equivalent("wireless earbud", "earbuds")
    assert search_queries_equivalent("earbuds", "galaxy buds")
    assert not search_queries_equivalent("shampoo", "earbuds")


def test_extracts_multi_item_list() -> None:
    from core.search_query import extract_product_queries

    queries = extract_product_queries("add watches , beauty bars in my cart")
    assert len(queries) == 2
    assert queries[0] == "smartwatch"
    assert "beauty" in queries[1]


def test_complex_list_skips_all_and_fixes_typos() -> None:
    from core.search_query import extract_product_queries

    queries = extract_product_queries(
        "add watches , bars , chcolates , buds and all in my cart"
    )
    assert "all" not in queries
    assert queries[0] == "smartwatch"
    assert queries[1] == "beauty bar"
    assert queries[2] == "chocolates"
    assert queries[3] == "earbuds"


def test_single_item_not_split_on_and_in_phrase() -> None:
    from core.search_query import extract_product_queries

    queries = extract_product_queries("find peanut butter and jelly snacks")
    assert len(queries) == 1


def test_add_and_checkout_not_split_as_multi_item() -> None:
    from core.search_query import extract_product_queries

    queries = extract_product_queries("add snacks under ₹200 and checkout")
    assert len(queries) == 1
    assert "snack" in queries[0]


def test_buy_me_list_splits_into_items() -> None:
    from core.search_query import extract_product_queries

    queries = extract_product_queries("buy me amul butter , chips , cooker")
    assert len(queries) == 3
    assert "butter" in queries[0]
    assert queries[1] == "chips"
    assert "cooker" in queries[2]


def test_chatty_detection() -> None:
    assert looks_like_chatty_search(
        "hey can you help me find dresses for my party tonight"
    )
    assert not looks_like_chatty_search("dresses party")

