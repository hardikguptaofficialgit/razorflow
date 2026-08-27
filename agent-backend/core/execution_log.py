"""Structured execution logging for agent runs."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("razorflow.execution")


def log_run(run_id: str, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[RUN] runId=%s %s %s", run_id, message, extra)


def log_intent(run_id: str, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[INTENT] runId=%s %s %s", run_id, message, extra)


def log_observe(run_id: str, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[OBSERVE] runId=%s %s %s", run_id, message, extra)


def log_plan(run_id: str, step: int, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[PLAN] runId=%s step=%s %s %s", run_id, step, message, extra)


def log_action(run_id: str, step: int, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[ACTION] runId=%s step=%s %s %s", run_id, step, message, extra)


def log_execute(run_id: str, step: int, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[EXECUTE] runId=%s step=%s %s %s", run_id, step, message, extra)


def log_verify(run_id: str, step: int, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[VERIFY] runId=%s step=%s %s %s", run_id, step, message, extra)


def log_state(run_id: str, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[STATE] runId=%s %s %s", run_id, message, extra)


def log_recovery(run_id: str, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[RECOVERY] runId=%s %s %s", run_id, message, extra)


def log_done(run_id: str, message: str, **fields: Any) -> None:
    extra = " ".join(f"{key}={value}" for key, value in fields.items() if value is not None)
    logger.info("[DONE] runId=%s %s %s", run_id, message, extra)
