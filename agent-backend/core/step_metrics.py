"""Per-step latency metrics for the Browser Use executor loop."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class StepMetrics:
    """Wall-clock timings for one agent step callback (ms)."""

    run_id: str
    step: int
    observe_ms: float = 0.0
    action_select_ms: float = 0.0
    sync_ms: float = 0.0
    verify_ms: float = 0.0
    callback_total_ms: float = 0.0
    forced_click_index: int | None = None
    page_changed: bool | None = None
    product_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def log(self) -> None:
        logger.info(
            "step_metrics runId=%s step=%s observe_ms=%.0f action_select_ms=%.0f "
            "verify_ms=%.0f sync_ms=%.0f callback_total_ms=%.0f forced_click=%s "
            "products=%s page_changed=%s",
            self.run_id,
            self.step,
            self.observe_ms,
            self.action_select_ms,
            self.verify_ms,
            self.sync_ms,
            self.callback_total_ms,
            self.forced_click_index,
            self.product_count,
            self.page_changed,
        )


@contextmanager
def timed_section(metrics: StepMetrics, attr: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        setattr(metrics, attr, getattr(metrics, attr, 0.0) + elapsed_ms)
