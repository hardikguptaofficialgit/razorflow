"""Append-only structured decision log for Browser Use shopping steps."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from queue import Full, Queue
from typing import Any

logger = logging.getLogger(__name__)

_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
_LOG_FILE = _LOG_DIR / "agent_decisions.jsonl"
_QUEUE: Queue[dict[str, Any] | None] = Queue(maxsize=2000)
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def _ensure_worker() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True
        thread = threading.Thread(target=_writer_loop, name="agent-decision-log", daemon=True)
        thread.start()


def _writer_loop() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    while True:
        record = _QUEUE.get()
        if record is None:
            return
        try:
            with _LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as error:
            logger.warning("Failed to write agent decision log: %s", error)


def log_agent_decision(
    *,
    run_id: str,
    step: int,
    phase: str,
    observation: dict[str, Any] | None = None,
    extracted: dict[str, Any] | None = None,
    reasoning: str | None = None,
    action: str | None = None,
    verification: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Enqueue one structured decision record (non-blocking for the agent loop)."""
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "runId": run_id,
        "step": step,
        "phase": phase,
        "observation": observation or {},
        "extracted": extracted or {},
        "reasoning": reasoning or "",
        "action": action or "",
        "verification": verification or {},
    }
    if extra:
        record["extra"] = extra

    _ensure_worker()
    try:
        _QUEUE.put_nowait(record)
    except Full:
        logger.warning("agent decision log queue full — dropping record phase=%s", phase)

    logger.info(
        "agent_decision runId=%s step=%s phase=%s action=%s reasoning=%s",
        run_id,
        step,
        phase,
        action,
        (reasoning or "")[:160],
    )
    return record
