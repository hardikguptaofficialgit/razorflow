"""Provider failover adapter for the open-source browser-use executor LLM.

Satisfies browser-use's `BaseChatModel` protocol structurally, so the agent loop, its
callbacks and its action execution are untouched: the failover and the bounded per-provider
retry both happen strictly inside `ainvoke`, which browser-use calls before any action of
that step is executed. A provider therefore never answers twice for one agent step, and no
browser action can be replayed by this layer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from browser_use.llm.base import BaseChatModel
from browser_use.llm.messages import BaseMessage
from browser_use.llm.views import ChatInvokeCompletion

from utils.llm_resilience import (
    ProviderCallFailed,
    ProviderCallStats,
    ProviderErrorInfo,
    ProviderNotConfiguredError,
    ProviderRateLimitExhaustedError,
    RATE_LIMIT,
    ResilientChatCompleter,
    summarize,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSlot:
    """One configured provider the executor may use."""

    provider: str
    model: str
    llm: BaseChatModel

    def describe(self) -> str:
        return f"{self.provider}:{self.model}"


class FailoverChatModel:
    """Runs each agent step against the first provider that answers.

    Per provider, `ResilientChatCompleter` applies bounded exponential backoff and honours
    Retry-After while it fits the retry budget. When a provider exhausts that budget, or the
    failure is one replaying cannot fix (credits, quota, bad key), the request moves to the
    next configured provider. The provider that last succeeded is tried first on later steps
    so a rate-limited primary is not re-probed on every step.
    """

    def __init__(
        self,
        slots: Sequence[ProviderSlot],
        *,
        on_stats: Callable[[ProviderCallStats], None] | None = None,
    ) -> None:
        if not slots:
            raise ProviderNotConfiguredError("No LLM provider configured for the browser executor.")
        self._slots = list(slots)
        self._active = 0
        self._stats: list[ProviderCallStats] = []
        self._on_stats = on_stats

    # --- browser-use BaseChatModel surface -------------------------------------------
    @property
    def active_slot(self) -> ProviderSlot:
        return self._slots[self._active]

    @property
    def provider(self) -> str:
        return self.active_slot.provider

    @property
    def model(self) -> str:
        return self.active_slot.model

    @property
    def name(self) -> str:
        return self.active_slot.model

    @property
    def model_name(self) -> str:
        return self.active_slot.model

    @property
    def base_url(self) -> str:
        return str(getattr(self.active_slot.llm, "base_url", "") or "")

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(f"{slot.provider}:{slot.model}" for slot in self._slots)

    @property
    def last_stats(self) -> ProviderCallStats | None:
        return self._stats[-1] if self._stats else None

    def summary(self) -> dict[str, float | int]:
        return summarize(self._stats)

    def _record(self, stats: ProviderCallStats) -> None:
        self._stats.append(stats)
        if self._on_stats is not None:
            try:
                self._on_stats(stats)
            except Exception:  # observability must never fail a run
                logger.debug("LLM stats callback failed", exc_info=True)

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        output_format: Any = None,
        **kwargs: Any,
    ) -> ChatInvokeCompletion:
        invoke = (
            (lambda llm: llm.ainvoke(messages, output_format=output_format, **kwargs))
            if output_format is not None
            else (lambda llm: llm.ainvoke(messages, **kwargs))
        )
        order = [self._active] + [index for index in range(len(self._slots)) if index != self._active]
        failures: list[ProviderCallFailed] = []

        for position, index in enumerate(order):
            slot = self._slots[index]
            completer = ResilientChatCompleter(provider=slot.provider, model=slot.model)
            try:
                completion = await completer.complete(lambda llm=slot.llm: invoke(llm))
            except ProviderCallFailed as failure:
                self._record(completer.stats)
                if not failure.info.failover_eligible:
                    raise
                failures.append(failure)
                nxt = order[position + 1] if position + 1 < len(order) else None
                logger.warning(
                    "LLM failover from %s (%s) -> %s",
                    slot.describe(),
                    failure.info.describe(),
                    self._slots[nxt].describe() if nxt is not None else "no provider left",
                )
                continue

            if index != self._active:
                logger.info(
                    "LLM recovered on %s (attempts=%s, retries=%s); staying on this provider",
                    slot.describe(),
                    completer.stats.attempts,
                    completer.stats.retries,
                )
                self._active = index
            self._record(completer.stats)
            return completion

        raise self._aggregate_failure(failures)

    def _aggregate_failure(self, failures: list[ProviderCallFailed]) -> ProviderCallFailed:
        detail = "; ".join(f"{f.info.provider}:{f.info.model} {f.info.kind} ({f.info.message[:120]})" for f in failures)
        attempts = sum(f.attempts for f in failures)
        kinds = {f.info.kind for f in failures}
        last = failures[-1].info
        rate_limited = RATE_LIMIT in kinds
        info = ProviderErrorInfo(
            provider="|".join(f.info.provider for f in failures),
            model=last.model,
            kind=RATE_LIMIT if rate_limited else last.kind,
            status_code=last.status_code,
            retry_after_s=max((f.info.retry_after_s or 0.0) for f in failures) or None,
            message=f"all {len(failures)} configured LLM provider(s) failed: {detail}",
        )
        error_class = ProviderRateLimitExhaustedError if rate_limited else ProviderCallFailed
        return error_class(info, attempts, failures[0])
