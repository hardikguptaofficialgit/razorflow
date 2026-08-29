"""Authenticated HTTP boundary for storefront payment-link requests."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from policy.payment_executor import execute_payment_link_creation
from policy.payment_policy import PaymentLinkProposal

router = APIRouter(prefix="/api/payments", tags=["payments"])
_idempotency_lock = asyncio.Lock()
_successful_requests: dict[str, tuple[str, dict[str, Any]]] = {}


class PaymentLinkRequest(BaseModel):
    run_id: str = Field(alias="runId", min_length=1, max_length=120)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=200)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    amount_paise: int = Field(alias="amountPaise", gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)

    model_config = {"populate_by_name": True}


class PaymentLinkResponse(BaseModel):
    payment_link_url: str = Field(alias="paymentLinkUrl")
    amount_paise: int = Field(alias="amountPaise")
    currency: str
    description: str
    reference_id: str = Field(alias="referenceId")
    reused: bool = False

    model_config = {"populate_by_name": True}


def _check_internal_token(token: str | None) -> None:
    expected = os.getenv("AGENT_BACKEND_TOKEN", "").strip()
    if expected and token != expected:
        raise HTTPException(status_code=401, detail="Invalid payment gateway token.")


@router.post("/payment-link", response_model=PaymentLinkResponse)
async def create_payment_link(
    request: PaymentLinkRequest,
    x_razorflow_internal_token: str | None = Header(default=None),
) -> PaymentLinkResponse:
    """Create one policy-approved link; repeated keys return the same link."""
    _check_internal_token(x_razorflow_internal_token)
    key = request.idempotency_key.strip()
    fingerprint = "|".join(
        (
            request.title.strip(),
            request.description.strip(),
            str(request.amount_paise),
            request.currency.strip().upper(),
        ),
    )

    async with _idempotency_lock:
        cached = _successful_requests.get(key)
        if cached is not None:
            if cached[0] != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency key was already used for different payment details.",
                )
            return PaymentLinkResponse(**cached[1], reused=True)

        result = await execute_payment_link_creation(
            run_id=request.run_id,
            proposal=PaymentLinkProposal(
                title=request.title,
                description=request.description,
                amount_paise=request.amount_paise,
                currency=request.currency,
                reference_id=f"web-{key}",
            ),
            attempt=1,
        )

        if not result.success or result.payment_link is None:
            raise HTTPException(status_code=502, detail=result.message)

        payload = {
            "paymentLinkUrl": result.payment_link.payment_link_url,
            "amountPaise": result.payment_link.amount_paise,
            "currency": result.payment_link.currency,
            "description": result.payment_link.description,
            "referenceId": result.payment_link.reference_id,
        }
        _successful_requests[key] = (fingerprint, payload)
        return PaymentLinkResponse(**payload)
