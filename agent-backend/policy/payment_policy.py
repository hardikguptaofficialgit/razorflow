"""Deterministic payment-link policy validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from utils.config import DEFAULT_PAYMENT_CURRENCY, MAX_SPEND_PAISE

PolicyDecision = Literal["approved", "blocked"]


@dataclass(frozen=True)
class PaymentLinkProposal:
    title: str
    description: str
    amount_paise: int
    currency: str = DEFAULT_PAYMENT_CURRENCY
    reference_id: str = ""


@dataclass(frozen=True)
class PolicyValidationResult:
    decision: PolicyDecision
    reason: str
    proposal: PaymentLinkProposal | None = None


def build_reference_id(run_id: str, attempt: int) -> str:
    return f"rf-{run_id[:8]}-{attempt}"


def _blocked(reason: str) -> PolicyValidationResult:
    return PolicyValidationResult(
        decision="blocked",
        reason=f"Policy blocked: {reason}",
    )


def validate_payment_link_proposal(
    proposal: PaymentLinkProposal,
) -> PolicyValidationResult:
    title = proposal.title.strip()
    description = proposal.description.strip()
    currency = proposal.currency.strip().upper() or DEFAULT_PAYMENT_CURRENCY

    if not title:
        return _blocked("Product title is required.")

    if not description:
        return _blocked("Product description is required.")

    if proposal.amount_paise <= 0:
        return _blocked("Amount must be greater than zero.")

    if proposal.amount_paise > MAX_SPEND_PAISE:
        return _blocked(
            f"Amount exceeds max spend limit "
            f"({MAX_SPEND_PAISE} paise / ₹{MAX_SPEND_PAISE / 100:.2f}).",
        )

    if len(currency) != 3:
        return _blocked("Currency must be a 3-letter ISO code.")

    if not proposal.reference_id.strip():
        return _blocked("Reference id is required.")

    normalized = PaymentLinkProposal(
        title=title,
        description=description,
        amount_paise=proposal.amount_paise,
        currency=currency,
        reference_id=proposal.reference_id.strip(),
    )
    return PolicyValidationResult(
        decision="approved",
        reason="Policy checks passed.",
        proposal=normalized,
    )
