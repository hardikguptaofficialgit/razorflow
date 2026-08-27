"""Append-only audit log for payment-link attempts."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

AuditEventType = Literal[
    "policy_check_started",
    "policy_approved",
    "policy_blocked",
    "mcp_create_payment_link_called",
    "payment_link_success",
    "payment_link_failure",
]

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LOG_PATH = _ROOT / "logs" / "payment_audit.jsonl"


@dataclass
class AuditEvent:
    run_id: str
    event_type: AuditEventType
    message: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
    )
    details: dict[str, Any] = field(default_factory=dict)


class PaymentAuditLog:
    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = log_path or _DEFAULT_LOG_PATH
        self._events: list[AuditEvent] = []

    def record(self, event: AuditEvent) -> AuditEvent:
        self._events.append(event)
        self._append_to_file(event)
        logger.info(
            "audit runId=%s type=%s message=%s",
            event.run_id,
            event.event_type,
            event.message,
        )
        return event

    def list_for_run(self, run_id: str, limit: int = 20) -> list[AuditEvent]:
        in_memory = [event for event in self._events if event.run_id == run_id]
        if in_memory:
            return in_memory[-limit:]

        return self._read_from_file(run_id, limit)

    def _read_from_file(self, run_id: str, limit: int) -> list[AuditEvent]:
        if not self._log_path.exists():
            return []

        matches: list[AuditEvent] = []
        try:
            with self._log_path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    payload = json.loads(line)
                    if payload.get("run_id") != run_id:
                        continue
                    matches.append(
                        AuditEvent(
                            run_id=payload["run_id"],
                            event_type=payload["event_type"],
                            message=payload["message"],
                            timestamp=payload.get("timestamp", ""),
                            details=payload.get("details", {}),
                        ),
                    )
        except (OSError, json.JSONDecodeError, KeyError):
            logger.exception("Failed to read payment audit log file.")

        return matches[-limit:]

    def _append_to_file(self, event: AuditEvent) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
        except OSError:
            logger.exception("Failed to append payment audit log entry.")


payment_audit_log = PaymentAuditLog()
