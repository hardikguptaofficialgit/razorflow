"""Tests for RazorFlow Market fast-path planner."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.protocol import PageContext, PageProductSummary  # noqa: E402
from core.run_manager import RunSession  # noqa: E402
from core.store_planner import is_razorflow_store_url, try_store_fast_plan  # noqa: E402


def test_is_razorflow_store_url_localhost() -> None:
    assert is_razorflow_store_url("http://localhost:3000/")
    assert is_razorflow_store_url("http://127.0.0.1:3000/search?q=shampoo")


def test_store_fast_plan_navigates_from_home() -> None:
    session = RunSession(
        run_id="run-1",
        task="Find the cheapest shampoo under 500",
        latest_page_context=PageContext(
            title="Razorflow Market",
            url="http://localhost:3000/",
            elements=[],
            products=[],
        ),
    )
    chunk = try_store_fast_plan(session)
    assert chunk is not None
    assert chunk.steps[0].action == "navigate_url"
    assert "shampoo" in chunk.steps[0].url


def test_store_fast_plan_skips_when_results_ready() -> None:
    session = RunSession(
        run_id="run-2",
        task="Find shampoo",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3000/search?q=shampoo",
            elements=[],
            products=[
                PageProductSummary(title="Head & Shoulders", price_text="₹349"),
            ],
        ),
    )
    assert try_store_fast_plan(session) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://amazon.in/s?k=shampoo",
        "https://example.com/",
    ],
)
def test_store_fast_plan_ignores_external_sites(url: str) -> None:
    session = RunSession(
        run_id="run-3",
        task="Find shampoo",
        latest_page_context=PageContext(title="Other", url=url, elements=[], products=[]),
    )
    assert try_store_fast_plan(session) is None


def test_store_fast_plan_skips_repeat_navigate_after_success() -> None:
    from core.protocol import ActionHistoryEntry, NavigateUrlStep

    session = RunSession(
        run_id="run-4",
        task="Find shampoo",
        latest_page_context=PageContext(
            title="Razorflow Market",
            url="http://localhost:3000/",
            elements=[],
            products=[],
        ),
    )
    session.history.append(
        ActionHistoryEntry(
            step=NavigateUrlStep(
                action="navigate_url",
                url="http://localhost:3000/search?q=shampoo",
            ),
            success=True,
            error=None,
            page_fingerprint=None,
        ),
    )
    assert try_store_fast_plan(session) is None
