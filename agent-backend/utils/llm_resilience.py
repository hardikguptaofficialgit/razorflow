"""Provider-agnostic LLM call resilience: rate-limit detection, bounded backoff, metrics.

Deliberately free of browser-use / agent imports so every LLM surface (DOM planner and
browser executor) shares one policy.

Invariant: retries wrap a *single provider completion request*. A completion is replayed
at most until it returns; once a provider has answered, this module never calls it again.
Anything that executes side effects (browser actions, payment calls) lives above this
layer and is therefore never repeated by a retry here.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import random
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

RATE_LIMIT = "rate_limit"
BILLING = "billing"
AUTH = "auth"
TRANSPORT = "transport"
SERVER = "server"
CLIENT = "client"
OUTPUT_TRUNCATED = "output_truncated"
OUTPUT_INVALID = "output_invalid"
UNKNOWN = "unknown"

# Retrying the same provider only helps when the provider itself was transiently unhappy.
_SAME_PROVIDER_RETRY = {RATE_LIMIT, TRANSPORT, SERVER}
# A different provider can serve requests this one never will (credits, keys, output caps).
_FAILOVER_ELIGIBLE = {RATE_LIMIT, TRANSPORT, SERVER, BILLING, AUTH, OUTPUT_TRUNCATED, UNKNOWN}
# 401/402/403 are credential/credit problems where sleeping on the same key only burns
# wall-clock time, so they map straight to a non-retryable kind.
_STATUS_KIND = {401: AUTH, 403: AUTH, 402: BILLING, 429: RATE_LIMIT}

# Acronyms need word boundaries: "tps" is otherwise a substring of every "https://" URL.
_RATE_LIMIT_RE = re.compile(
    r"rate[ _-]?limit|too many requests|tokens per (?:minute|hour|day|second|month)"
    r"|requests per (?:minute|second|hour)|\b(?:tpm|tph|tpd|tps|rps)\b|\bquota\b|exceeded your current quota"
    r"|try again in|retry after|backoff",
    re.I,
)
_BILLING_RE = re.compile(r"insufficient credit|more credits|billing|\bpayment required\b|can only afford", re.I)
_AUTH_RE = re.compile(r"invalid api key|unauthorized|forbidden|authentication|\bno api key\b|incorrect api key", re.I)
_TRANSPORT_RE = re.compile(r"timed?[ _]?out|connection|unreachable|refused|reset by peer|network|dns", re.I)

_RETRY_AFTER_HEADER_RE = re.compile(r"retry-after", re.I)
_STATUS_TEXT_RE = re.compile(r"(?:error code|http(?:/1\.[01])?|status[_ ]?code)\D{0,3}(\d{3})\b", re.I)
# Groq/OpenRouter embed the reset window in prose: "Please try again in 2m33.36s."
_RETRY_AFTER_TEXT_RE = re.compile(
    r"(?:try again in|retry in|resets? in|backoff(?:ing)? for|available in)\s+"
    r"((?:\d+(?:\.\d+)?\s*(?:h|hour|hours?|m|min|minutes?|s|sec|seconds?)\s*)+)",
    re.I,
)
_UNIT_SECONDS_RE = re.compile(r"([\d.]+)\s*([a-zA-Z]+)")
_UNIT_MULTIPLIERS = {"h": 3600.0, "m": 60.0, "s": 1.0}


@dataclass(frozen=True)
class ProviderErrorInfo:
    """What a provider actually told us, independent of the agent's own success."""

    provider: str = "unknown"
    model: str = "unknown"
    kind: str = UNKNOWN
    status_code: int | None = None
    retry_after_s: float | None = None
    message: str = ""

    @property
    def is_rate_limit(self) -> bool:
        return self.kind == RATE_LIMIT

    @property
    def retryable(self) -> bool:
        """Worth replaying the identical request against the same provider."""
        return self.kind in _SAME_PROVIDER_RETRY

    @property
    def failover_eligible(self) -> bool:
        """Worth asking another provider, even when replaying this one is pointless."""
        return self.kind in _FAILOVER_ELIGIBLE

    def describe(self) -> str:
        parts = [f"provider={self.provider}", f"model={self.model}", f"kind={self.kind}"]
        if self.status_code is not None:
            parts.append(f"http={self.status_code}")
        if self.retry_after_s is not None:
            parts.append(f"retry_after={self.retry_after_s:.1f}s")
        return " ".join(parts)


class ProviderCallFailed(RuntimeError):
    """A provider call could not be completed. Carries provider truth, not agent truth."""

    def __init__(self, info: ProviderErrorInfo, attempts: int, cause: BaseException | None = None) -> None:
        self.info = info
        self.attempts = attempts
        self.provider = info.provider
        self.model = info.model
        super().__init__(
            f"LLM provider failure ({info.describe()}, attempts={attempts}): {info.message}"
        )
        if cause is not None:
            self.__cause__ = cause


class ProviderRateLimitExhaustedError(ProviderCallFailed):
    """Rate limit survived the bounded retry budget; the agent itself never ran wrong."""

    def __init__(self, info: ProviderErrorInfo, attempts: int, cause: BaseException | None = None) -> None:
        super().__init__(info, attempts, cause)


class ProviderNotConfiguredError(RuntimeError):
    """No usable provider exists — a configuration problem, not a rate limit."""


@dataclass
class ProviderCallStats:
    provider: str
    model: str
    attempts: int = 0
    retries: int = 0
    latency_ms: float = 0.0
    backoff_ms: float = 0.0
    ok: bool = False
    final_error: ProviderErrorInfo | None = None
    chain: list[str] = field(default_factory=list)

    def line(self) -> str:
        error = "-" if self.final_error is None else f"{self.final_error.kind}:{self.final_error.message[:160]}"
        return (
            f"LLM_CALL provider={self.provider} model={self.model} ok={self.ok} "
            f"attempts={self.attempts} retries={self.retries} "
            f"latency_ms={self.latency_ms:.0f} backoff_ms={self.backoff_ms:.0f} "
            f"providers_tried={'|'.join(self.chain) or self.provider} error={error}"
        )


def parse_retry_after(value: Any) -> float | None:
    """Parse a Retry-After header (delta-seconds or HTTP-date) into non-negative seconds."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except ValueError:
        try:
            when = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        if when is None:
            return None
        now = datetime.now(tz=when.tzinfo) if when.tzinfo else datetime.now()
        seconds = (when - now).total_seconds()
    if seconds != seconds or seconds < 0:  # NaN guard, expired date
        return 0.0
    return round(seconds, 3)


def retry_after_from_text(message: str) -> float | None:
    """Extract a stated reset window from provider prose ("try again in 2m33.36s")."""
    match = _RETRY_AFTER_TEXT_RE.search(message or "")
    if not match:
        return None
    total = 0.0
    for amount, unit in _UNIT_SECONDS_RE.findall(match.group(1)):
        multiplier = _UNIT_MULTIPLIERS.get(unit[:1].lower())
        if multiplier is None:
            continue
        try:
            total += float(amount) * multiplier
        except ValueError:
            continue
    return round(total, 3) if total > 0 else None


def _headers_of(error: BaseException) -> Any:
    response = getattr(error, "response", None)
    return getattr(response, "headers", None) or getattr(error, "headers", None)


def _retry_after_from_exception(error: BaseException) -> float | None:
    headers = _headers_of(error)
    if headers:
        try:
            items = dict(headers.items())
        except (AttributeError, TypeError, ValueError):
            items = {}
        for name, value in items.items():
            if _RETRY_AFTER_HEADER_RE.fullmatch(str(name)):
                parsed = parse_retry_after(value)
                if parsed is not None:
                    return parsed
        get = getattr(headers, "get", None)
        if get:
            parsed = parse_retry_after(get("retry-after") or get("Retry-After"))
            if parsed is not None:
                return parsed
    return retry_after_from_text(str(error))


def _status_code_of(error: BaseException) -> int | None:
    for attribute in ("status_code", "status", "code"):
        value = getattr(error, attribute, None)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and 100 <= value <= 599:
            return value
        if isinstance(value, str) and value.isdigit():
            code = int(value)
            if 100 <= code <= 599:
                return code
    response = getattr(error, "response", None)
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    match = _STATUS_TEXT_RE.search(str(error))
    return int(match.group(1)) if match else None


def _classify_text(message: str) -> str:
    if _RATE_LIMIT_RE.search(message):
        return RATE_LIMIT
    if _BILLING_RE.search(message):
        return BILLING
    if _AUTH_RE.search(message):
        return AUTH
    if _TRANSPORT_RE.search(message):
        return TRANSPORT
    return UNKNOWN


def _classify_status(status_code: int | None, message: str) -> str:
    if status_code in _STATUS_KIND:
        return _STATUS_KIND[status_code]
    if status_code == 400 and "too many tokens" in message.lower():
        return RATE_LIMIT
    text_kind = _classify_text(message)
    if status_code is not None and text_kind == UNKNOWN:
        if status_code >= 500:
            return SERVER
        if 400 <= status_code < 500:
            return CLIENT
    return text_kind


def classify_error(error: BaseException, *, provider: str = "unknown", model: str = "unknown") -> ProviderErrorInfo:
    """Turn any provider exception into a typed, comparable failure record."""
    status_code = _status_code_of(error)
    raw_message = str(error)
    name = type(error).__name__.lower()

    if "truncat" in name:
        kind = OUTPUT_TRUNCATED
    elif "validationerror" in name and any(token in raw_message.lower() for token in ("schema", "field required", "json")):
        kind = OUTPUT_INVALID
    elif "ratelimit" in name:
        kind = RATE_LIMIT
    else:
        kind = _classify_status(status_code, raw_message)
    if kind == UNKNOWN and "validationerror" in name:
        kind = OUTPUT_INVALID

    retry_after = _retry_after_from_exception(error) if kind == RATE_LIMIT else None
    message = " ".join(raw_message.split())[:600] or type(error).__name__
    return ProviderErrorInfo(
        provider=provider,
        model=model,
        kind=kind,
        status_code=status_code,
        retry_after_s=retry_after,
        message=message,
    )


def is_rate_limit_failure(error: BaseException | None) -> bool:
    """True when the failure came from provider capacity, not from the agent's logic."""
    if error is None:
        return False
    if isinstance(error, ProviderRateLimitExhaustedError):
        return True
    return classify_error(error).is_rate_limit


def is_provider_failure(error: BaseException | None) -> bool:
    """True for any upstream LLM problem, so callers can keep it distinct from agent failure."""
    if error is None:
        return False
    if isinstance(error, (ProviderCallFailed, ProviderNotConfiguredError)):
        return True
    return classify_error(error).kind != UNKNOWN


def retry_policy_from_env() -> dict[str, float | int]:
    from utils.config import (
        get_llm_retry_base_delay,
        get_llm_retry_budget,
        get_llm_retry_max_attempts,
        get_llm_retry_max_delay,
    )

    return {
        "max_attempts": get_llm_retry_max_attempts(),
        "base_delay": get_llm_retry_base_delay(),
        "max_delay": get_llm_retry_max_delay(),
        "budget": get_llm_retry_budget(),
    }


def compute_delay(
    attempt: int,
    info: ProviderErrorInfo,
    *,
    base_delay: float,
    max_delay: float,
    elapsed: float,
    budget: float,
) -> float | None:
    """Seconds to wait before the next attempt, or None when waiting is pointless."""
    remaining = budget - elapsed
    if remaining <= 0:
        return None
    if info.kind == RATE_LIMIT and info.retry_after_s is not None:
        # Respect Retry-After only when it actually fits the budget; a daily quota reset
        # hours away must fail over now, not sleep.
        if info.retry_after_s > remaining:
            return None
        delay = min(info.retry_after_s, max_delay, remaining)
    else:
        delay = min(base_delay * (2 ** (attempt - 1)), max_delay, remaining)
    return round(delay * random.uniform(1.0, 1.0 + 0.2), 3)


def _raise_final(info: ProviderErrorInfo, attempts: int, cause: BaseException | None) -> None:
    if info.is_rate_limit:
        raise ProviderRateLimitExhaustedError(info, attempts) from cause
    raise ProviderCallFailed(info, attempts) from cause


def call_with_resilience(
    call: Callable[[], T],
    *,
    provider: str,
    model: str,
    max_attempts: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    budget: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, ProviderCallStats]:
    """Synchronously run one provider completion with bounded rate-limit backoff."""
    policy = retry_policy_from_env()
    attempts_limit = int(max_attempts if max_attempts is not None else policy["max_attempts"])
    base = float(base_delay if base_delay is not None else policy["base_delay"])
    cap = float(max_delay if max_delay is not None else policy["max_delay"])
    total_budget = float(budget if budget is not None else policy["budget"])

    stats = ProviderCallStats(provider=provider, model=model, chain=[provider])
    started = time.perf_counter()
    last_info: ProviderErrorInfo | None = None
    last_error: BaseException | None = None

    for attempt in range(1, attempts_limit + 1):
        stats.attempts = attempt
        try:
            result = call()
        except Exception as error:
            last_error = error
            last_info = classify_error(error, provider=provider, model=model)
            wait = (
                compute_delay(attempt, last_info, base_delay=base, max_delay=cap, elapsed=time.perf_counter() - started, budget=total_budget)
                if last_info.retryable
                else None
            )
            logger.warning(
                "LLM provider=%s model=%s attempt %s/%s failed %s wait=%s",
                provider,
                model,
                attempt,
                attempts_limit,
                last_info.describe(),
                f"{wait:.1f}s" if wait else "none",
            )
            if wait is None:
                stats.final_error = last_info
                break
            stats.retries += 1
            stats.backoff_ms += wait * 1000.0
            sleep(wait)
            continue

        stats.ok = True
        stats.latency_ms = (time.perf_counter() - started) * 1000.0
        logger.info(stats.line())
        return result, stats

    stats.latency_ms = (time.perf_counter() - started) * 1000.0
    stats.final_error = last_info or ProviderErrorInfo(provider, model, UNKNOWN, message="provider call failed")
    logger.error(stats.line())
    _raise_final(stats.final_error, stats.attempts, last_error)
    raise AssertionError("unreachable")


class ResilientChatCompleter:
    """Async single-provider completion with bounded retries, for a browser-use LLM."""

    def __init__(self, *, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model
        self.stats = ProviderCallStats(provider=provider, model=model, chain=[provider])

    async def complete(self, invoke: Callable[[], Any]) -> Any:
        policy = retry_policy_from_env()
        attempts_limit = int(policy["max_attempts"])
        base = float(policy["base_delay"])
        cap = float(policy["max_delay"])
        total_budget = float(policy["budget"])
        started = time.perf_counter()
        last_info: ProviderErrorInfo | None = None
        last_error: BaseException | None = None

        for attempt in range(1, attempts_limit + 1):
            self.stats.attempts = attempt
            try:
                result = await invoke()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                last_error = error
                last_info = classify_error(error, provider=self.provider, model=self.model)
                wait = (
                    compute_delay(
                        attempt,
                        last_info,
                        base_delay=base,
                        max_delay=cap,
                        elapsed=time.perf_counter() - started,
                        budget=total_budget,
                    )
                    if last_info.retryable
                    else None
                )
                logger.warning(
                    "LLM provider=%s model=%s attempt %s/%s failed %s wait=%s",
                    self.provider,
                    self.model,
                    attempt,
                    attempts_limit,
                    last_info.describe(),
                    f"{wait:.1f}s" if wait else "none",
                )
                if wait is None:
                    break
                self.stats.retries += 1
                self.stats.backoff_ms += wait * 1000.0
                await asyncio.sleep(wait)
                continue

            self.stats.ok = True
            self.stats.latency_ms = (time.perf_counter() - started) * 1000.0
            logger.info(self.stats.line())
            return result

        self.stats.latency_ms = (time.perf_counter() - started) * 1000.0
        self.stats.final_error = last_info or ProviderErrorInfo(self.provider, self.model, UNKNOWN, message="provider call failed")
        logger.error(self.stats.line())
        _raise_final(self.stats.final_error, self.stats.attempts, last_error)
        raise AssertionError("unreachable")


def summarize(stats: Sequence[ProviderCallStats]) -> dict[str, float | int]:
    """Aggregated call counters for run reporting."""
    return {
        "llm_calls": len(stats),
        "llm_retries": sum(item.retries for item in stats),
        "llm_attempts": sum(item.attempts for item in stats),
        "llm_failures": sum(1 for item in stats if not item.ok),
        "llm_rate_limit_failures": sum(1 for item in stats if item.final_error is not None and item.final_error.is_rate_limit),
        "llm_provider_ms": round(sum(item.latency_ms for item in stats), 1),
        "llm_backoff_ms": round(sum(item.backoff_ms for item in stats), 1),
    }
