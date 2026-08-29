"""Handoff policy — normal tasks must not trigger handoff."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_runtime.observation.browser_state import BrowserPage, ObservedCartLine, ObservedProduct
from agent_runtime.policy.action_gate import handoff_allowed


def _page(url: str = "http://localhost:3001/demo/search?q=earbuds") -> BrowserPage:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    query = ""
    if parsed.query:
        from urllib.parse import parse_qs

        qs = parse_qs(parsed.query)
        query = qs.get("q", [""])[0]
    return BrowserPage(
        title="Demo",
        url=url,
        path=parsed.path or "/",
        search_query=query,
        elements=[],
        products=[],
        cart_lines=[],
    )


def test_search_task_no_handoff_on_uncertainty() -> None:
    assert not handoff_allowed(_page(), "I am not sure which product to pick")


def test_add_snacks_no_handoff_on_failure() -> None:
    assert not handoff_allowed(_page("/demo/search?q=snacks"), "click failed")


def test_open_cart_no_handoff() -> None:
    assert not handoff_allowed(_page("/demo/cart"), "need help navigating")


def test_login_page_allows_handoff() -> None:
    page = BrowserPage(
        title="Login",
        url="http://localhost:3001/demo/login",
        path="/login",
        search_query="",
        elements=[],
        products=[],
        cart_lines=[],
        signals=["login_required"],
    )
    assert handoff_allowed(page, "Please sign in")


def test_otp_reason_allows_handoff() -> None:
    assert handoff_allowed(_page("/checkout"), "Enter OTP to continue")


def test_payment_confirmation_allows_handoff() -> None:
    assert handoff_allowed(_page("/checkout"), "Confirm payment before proceeding")


def test_captcha_allows_handoff() -> None:
    assert handoff_allowed(_page(), "Solve CAPTCHA to continue")
