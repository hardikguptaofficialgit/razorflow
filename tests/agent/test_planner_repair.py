"""Tests for planner output repair."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.planner_repair import repair_planner_payload, repair_planner_step  # noqa: E402
from core.protocol import PageContext, PageElementSummary  # noqa: E402


def test_repair_missing_click_role_from_element_index() -> None:
    page = PageContext(
        title="Home",
        url="http://localhost:3001/",
        elements=[
            PageElementSummary(
                index=6,
                role="link",
                tag="a",
                text="Cart, 0 items",
                placeholder="",
                aria_label="Cart",
            ),
        ],
        products=[],
    )
    step = {
        "action": "click_element",
        "elementIndex": 6,
        "matchText": "Cart",
    }
    repaired = repair_planner_step(step, page)
    assert repaired["role"] == "link"


def test_repair_relative_navigate_url() -> None:
    page = PageContext(
        title="Home",
        url="http://localhost:3001/",
        elements=[],
        products=[],
    )
    payload = repair_planner_payload(
        {"steps": [{"action": "navigate_url", "url": "/search?q=earbuds"}], "terminal": "continue"},
        page,
    )
    assert payload["steps"][0]["url"] == "http://localhost:3001/search?q=earbuds"
