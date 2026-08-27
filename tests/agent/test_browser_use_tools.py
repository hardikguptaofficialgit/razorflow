"""Tests for RazorFlow custom Browser Use tools."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.browser_use_tools import (  # noqa: E402
    MarkShoppingCompleteParams,
    ProposeCheckoutPaymentParams,
    RequestUserHandoffParams,
    bind_tools_for_run,
    clear_tool_state,
    get_tool_state,
)


@pytest.fixture(autouse=True)
def _clean_tool_state() -> None:
    clear_tool_state("run-tools-1")
    yield
    clear_tool_state("run-tools-1")


@pytest.mark.asyncio
async def test_request_user_handoff_pauses_run() -> None:
    tools = bind_tools_for_run("run-tools-1")
    action = tools.registry.registry.actions["request_user_handoff"]
    result = await action.function(params=RequestUserHandoffParams(reason="Please log in"))

    state = get_tool_state("run-tools-1")
    assert state.pause_requested is True
    assert state.handoff_message == "Please log in"
    assert "Waiting for user" in (result.extracted_content or "")


@pytest.mark.asyncio
async def test_propose_checkout_payment_sets_proposal() -> None:
    tools = bind_tools_for_run("run-tools-1")
    action = tools.registry.registry.actions["propose_checkout_payment"]
    result = await action.function(
        params=ProposeCheckoutPaymentParams(
            title="Shampoo",
            description="1 item in cart",
            amount_paise=49900,
            currency="INR",
        ),
    )

    state = get_tool_state("run-tools-1")
    assert state.payment_proposal is not None
    assert state.payment_proposal.amount_paise == 49900
    assert state.pause_requested is True
    assert "Payment confirmation requested" in (result.extracted_content or "")


@pytest.mark.asyncio
async def test_mark_complete_requires_cart_verification() -> None:
    tools = bind_tools_for_run("run-tools-1")
    action = tools.registry.registry.actions["mark_shopping_complete"]
    rejected = await action.function(
        params=MarkShoppingCompleteParams(summary="searched only", cart_count=0),
    )
    assert rejected.error
    assert get_tool_state("run-tools-1").completion_summary is None

    accepted = await action.function(
        params=MarkShoppingCompleteParams(
            summary="Added Sunsilk shampoo to cart",
            product_in_cart="Sunsilk Thick & Long Shampoo",
            cart_count=1,
        ),
    )
    state = get_tool_state("run-tools-1")
    assert state.completion_summary is not None
    assert accepted.is_done is True
    assert accepted.success is True


def test_native_done_action_is_available() -> None:
    tools = bind_tools_for_run("run-tools-1")
    assert "mark_shopping_complete" in tools.registry.registry.actions
    assert "request_user_handoff" in tools.registry.registry.actions
    assert "record_product_decision" in tools.registry.registry.actions
    assert "done" in tools.registry.registry.actions
