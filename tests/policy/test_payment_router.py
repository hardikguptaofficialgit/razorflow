"""Tests for the storefront payment gateway boundary."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from policy.payment_executor import PaymentLinkExecutionResult
from policy.payment_router import PaymentLinkRequest, create_payment_link
from policy.razorpay_mcp_client import PaymentLinkMcpResult


def _request(**overrides: object) -> PaymentLinkRequest:
    values: dict[str, object] = {
        "runId": "web-test-run",
        "idempotencyKey": "checkout-test-key",
        "title": "RazorFlow order",
        "description": "Test item × 1",
        "amountPaise": 29900,
        "currency": "INR",
    }
    values.update(overrides)
    return PaymentLinkRequest(**values)


def test_payment_link_request_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def fake_execute(**_: object) -> PaymentLinkExecutionResult:
        nonlocal calls
        calls += 1
        return PaymentLinkExecutionResult(
            success=True,
            message="Payment link ready.",
            payment_link=PaymentLinkMcpResult(
                payment_link_url="https://rzp.io/i/test-link",
                amount_paise=29900,
                currency="INR",
                description="RazorFlow order — Test item × 1",
                reference_id="web-checkout-test-key",
                raw={},
            ),
        )

    monkeypatch.setattr(
        "policy.payment_router.execute_payment_link_creation",
        fake_execute,
    )

    first = asyncio.run(create_payment_link(_request()))
    second = asyncio.run(create_payment_link(_request()))

    assert first.payment_link_url == second.payment_link_url
    assert second.reused is True
    assert calls == 1


def test_idempotency_key_cannot_change_payment_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_execute(**_: object) -> PaymentLinkExecutionResult:
        return PaymentLinkExecutionResult(
            success=True,
            message="Payment link ready.",
            payment_link=PaymentLinkMcpResult(
                payment_link_url="https://rzp.io/i/conflict-test",
                amount_paise=29900,
                currency="INR",
                description="RazorFlow order — Test item × 1",
                reference_id="web-conflict-test-key",
                raw={},
            ),
        )

    monkeypatch.setattr(
        "policy.payment_router.execute_payment_link_creation",
        fake_execute,
    )
    asyncio.run(create_payment_link(_request(idempotencyKey="conflict-test-key")))

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            create_payment_link(
                _request(
                    idempotencyKey="conflict-test-key",
                    amountPaise=30000,
                ),
            ),
        )

    assert error.value.status_code == 409


def test_policy_block_is_reported_as_forbidden() -> None:
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            create_payment_link(
                _request(
                    idempotencyKey="over-limit-test-key",
                    amountPaise=500001,
                ),
            ),
        )

    assert error.value.status_code == 403
    assert "max spend limit" in str(error.value.detail)
