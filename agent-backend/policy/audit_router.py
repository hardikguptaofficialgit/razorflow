"""HTTP endpoints for payment audit visibility."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from policy.audit_log import payment_audit_log

router = APIRouter(prefix="/audit", tags=["audit"])


class PaymentAuditEntry(BaseModel):
    run_id: str = Field(alias="runId")
    event_type: str = Field(alias="eventType")
    message: str
    timestamp: str
    details: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class PaymentAuditResponse(BaseModel):
    run_id: str = Field(alias="runId")
    entries: list[PaymentAuditEntry]

    model_config = {"populate_by_name": True}


@router.get("/payment", response_model=PaymentAuditResponse)
def get_payment_audit(
    run_id: str = Query(alias="runId", min_length=1),
    limit: int = Query(default=12, ge=1, le=50),
) -> PaymentAuditResponse:
    events = payment_audit_log.list_for_run(run_id, limit=limit)
    return PaymentAuditResponse(
        runId=run_id,
        entries=[
            PaymentAuditEntry(
                runId=event.run_id,
                eventType=event.event_type,
                message=event.message,
                timestamp=event.timestamp,
                details=event.details,
            )
            for event in events
        ],
    )
