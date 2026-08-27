"""Tests for payment-link policy validation."""

from __future__ import annotations

from policy.payment_policy import PaymentLinkProposal, validate_payment_link_proposal


def test_validate_payment_link_approved() -> None:
    result = validate_payment_link_proposal(
        PaymentLinkProposal(
            title="Shampoo",
            description="Cheapest shampoo checkout",
            amount_paise=29900,
            currency="INR",
            reference_id="rf-test-1",
        ),
    )

    assert result.decision == "approved"
    assert result.proposal is not None


def test_validate_payment_link_blocks_over_limit() -> None:
    result = validate_payment_link_proposal(
        PaymentLinkProposal(
            title="Luxury bundle",
            description="Too expensive",
            amount_paise=10_000_000,
            currency="INR",
            reference_id="rf-test-2",
        ),
    )

    assert result.decision == "blocked"
    assert "Policy blocked" in result.reason


def test_validate_payment_link_blocks_missing_title() -> None:
    result = validate_payment_link_proposal(
        PaymentLinkProposal(
            title=" ",
            description="Missing title",
            amount_paise=100,
            currency="INR",
            reference_id="rf-test-3",
        ),
    )

    assert result.decision == "blocked"
