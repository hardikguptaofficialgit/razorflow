"""Structured run trace events."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOG_DIR = Path(__file__).resolve().parents[2] / "agent-backend" / "logs"
_TRACE_FILE = _LOG_DIR / "agent_runtime_v2.jsonl"


def emit_trace(
    run_id: str,
    event: str,
    *,
    step: int = 0,
    duration_ms: int = 0,
    **fields: Any,
) -> None:
    payload = {
        "ts": time.time(),
        "runId": run_id,
        "event": event,
        "step": step,
        "durationMs": duration_ms,
        **fields,
    }
    logger.info("[V2][%s] %s step=%s %s", run_id[:8], event, step, fields)
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _TRACE_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
