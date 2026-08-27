"""Policy-gated payment-link execution (planner never calls MCP directly)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from policy.audit_log import AuditEvent, payment_audit_log
from policy.payment_policy import (
    PaymentLinkProposal,
    PolicyValidationResult,
    build_reference_id,
    validate_payment_link_proposal,
)
from policy.razorpay_mcp_client import (
    PaymentLinkMcpResult,
    RazorpayMcpError,
    razorpay_mcp_client,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentLinkExecutionResult:
    success: bool
    message: str
    policy: PolicyValidationResult | None = None
    payment_link: PaymentLinkMcpResult | None = None


async def execute_payment_link_creation(
    *,
    run_id: str,
    proposal: PaymentLinkProposal,
    attempt: int,
) -> PaymentLinkExecutionResult:
    reference_id = proposal.reference_id or build_reference_id(run_id, attempt)
    normalized_input = PaymentLinkProposal(
        title=proposal.title,
        description=proposal.description,
        amount_paise=proposal.amount_paise,
        currency=proposal.currency,
        reference_id=reference_id,
    )

    payment_audit_log.record(
        AuditEvent(
            run_id=run_id,
            event_type="policy_check_started",
            message="Validating payment-link proposal.",
            details={
                "title": normalized_input.title,
                "amountPaise": normalized_input.amount_paise,
                "currency": normalized_input.currency,
                "referenceId": normalized_input.reference_id,
            },
        ),
    )

    policy = validate_payment_link_proposal(normalized_input)
    if policy.decision == "blocked" or policy.proposal is None:
        payment_audit_log.record(
            AuditEvent(
                run_id=run_id,
                event_type="policy_blocked",
                message=policy.reason,
                details={"proposal": normalized_input.__dict__},
            ),
        )
        return PaymentLinkExecutionResult(
            success=False,
            message=policy.reason,
            policy=policy,
        )

    approved = policy.proposal
    payment_audit_log.record(
        AuditEvent(
            run_id=run_id,
            event_type="policy_approved",
            message=policy.reason,
            details={
                "title": approved.title,
                "amountPaise": approved.amount_paise,
                "currency": approved.currency,
                "referenceId": approved.reference_id,
            },
        ),
    )

    payment_audit_log.record(
        AuditEvent(
            run_id=run_id,
            event_type="mcp_create_payment_link_called",
            message="Calling Razorpay MCP create_payment_link.",
            details={
                "tool": "create_payment_link",
                "amountPaise": approved.amount_paise,
                "currency": approved.currency,
                "referenceId": approved.reference_id,
            },
        ),
    )

    try:
        payment_link = await razorpay_mcp_client.create_payment_link(
            amount_paise=approved.amount_paise,
            currency=approved.currency,
            description=f"{approved.title} — {approved.description}",
            reference_id=approved.reference_id,
        )
    except RazorpayMcpError as error:
        payment_audit_log.record(
            AuditEvent(
                run_id=run_id,
                event_type="payment_link_failure",
                message=str(error),
                details={"stage": "mcp"},
            ),
        )
        logger.warning("Payment link MCP failure runId=%s: %s", run_id, error)
        return PaymentLinkExecutionResult(
            success=False,
            message=str(error),
            policy=policy,
        )

    payment_audit_log.record(
        AuditEvent(
            run_id=run_id,
            event_type="payment_link_success",
            message="Payment link created successfully.",
            details={
                "paymentLinkUrl": payment_link.payment_link_url,
                "amountPaise": payment_link.amount_paise,
                "currency": payment_link.currency,
                "referenceId": payment_link.reference_id,
            },
        ),
    )

    return PaymentLinkExecutionResult(
        success=True,
        message="Payment link ready.",
        policy=policy,
        payment_link=payment_link,
    )
