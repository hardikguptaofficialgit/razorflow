"""LLM provider resilience tests: rate-limit detection, Retry-After, bounded backoff, failover."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.llm_failover import FailoverChatModel, ProviderSlot  # noqa: E402
from utils.llm_resilience import (  # noqa: E402
    AUTH,
    BILLING,
    OUTPUT_INVALID,
    RATE_LIMIT,
    SERVER,
    TRANSPORT,
    ProviderCallFailed,
    ProviderRateLimitExhaustedError,
    call_with_resilience,
    classify_error,
    compute_delay,
    is_rate_limit_failure,
    parse_retry_after,
    retry_after_from_text,
)

GROQ_TPM = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`openai/gpt-oss-120b` on tokens per minute (TPM): Limit 8000, Used 6420, "
    "Requested 3232. Please try again in 12.389999999s.'"
)
GROQ_TPD = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model on tokens per "
    "day (TPD): Limit 200000, Used 198219, Requested 2136. Please try again in 2m33.36s.'"
)


class _OutputModel(BaseModel):
    action: str


def _real_validation_error() -> Exception:
    """The exact exception shape browser-use raises when a model ignores the action schema."""
    try:
        _OutputModel.model_validate({})
    except ValidationError as error:
        return error
    raise AssertionError("expected a validation error")


class _Status(Exception):
    def __init__(self, status_code: int, message: str = "provider said no") -> None:
        super().__init__(message)
        self.status_code = status_code


def test_429_status_is_classified_as_rate_limit() -> None:
    assert classify_error(_Status(429, "slow down")).kind == RATE_LIMIT


def test_groq_per_minute_limit_detected_from_message_alone() -> None:
    info = classify_error(RuntimeError(GROQ_TPM), provider="groq", model="m")
    assert info.kind == RATE_LIMIT
    assert info.is_rate_limit
    assert info.retry_after_s == pytest.approx(12.39, abs=0.01)


def test_groq_daily_limit_detected_and_compound_window_parsed() -> None:
    info = classify_error(RuntimeError(GROQ_TPD), provider="groq", model="m")
    assert info.kind == RATE_LIMIT
    assert info.retry_after_s == pytest.approx(153.36, abs=0.01)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError("OpenRouter HTTP 402: This request requires more credits"), BILLING),
        (RuntimeError("Error code: 401 - invalid api key"), AUTH),
        (RuntimeError("connect timed out to api.example.com"), TRANSPORT),
        (RuntimeError("HTTP 503 Service Unavailable"), SERVER),
        (_real_validation_error(), OUTPUT_INVALID),
    ],
    ids=["billing", "auth", "transport", "server", "agent-output"],
)
def test_non_rate_limit_failures_get_their_own_kind(error: Exception, expected: str) -> None:
    assert classify_error(error, provider="p", model="m").kind == expected


def test_only_transient_kinds_are_replayed_on_the_same_provider() -> None:
    assert classify_error(RuntimeError(GROQ_TPM)).retryable
    assert classify_error(_Status(503)).retryable
    assert classify_error(_Status(429)).failover_eligible
    assert not classify_error(RuntimeError("requires more credits")).retryable
    assert classify_error(RuntimeError("requires more credits")).failover_eligible
    assert not classify_error(_real_validation_error()).failover_eligible


def test_retry_after_header_accepts_seconds_and_http_date() -> None:
    assert parse_retry_after("30") == 30.0
    assert parse_retry_after("Fri, 31 Dec 2100 23:59:59 GMT") > 0
    assert parse_retry_after("not a date") is None
    assert parse_retry_after(None) is None
    assert retry_after_from_text("Please try again in 45 seconds") == 45.0


def test_retry_after_is_respected_when_it_fits_the_budget() -> None:
    info = classify_error(RuntimeError(GROQ_TPM))
    delay = compute_delay(1, info, base_delay=1.0, max_delay=60.0, elapsed=0.0, budget=30.0)
    assert delay is not None
    assert 12.39 <= delay <= 12.39 * 1.25 + 0.01


def test_daily_quota_never_sleeps_when_it_cannot_fit_the_budget() -> None:
    info = classify_error(RuntimeError(GROQ_TPD))
    assert compute_delay(1, info, base_delay=1.0, max_delay=60.0, elapsed=0.0, budget=15.0) is None


def test_backoff_grows_exponentially_but_stays_bounded() -> None:
    info = classify_error(_Status(503))
    delays = [compute_delay(attempt, info, base_delay=1.0, max_delay=4.0, elapsed=0.0, budget=999) for attempt in (1, 2, 3, 9)]
    assert delays[0] is not None and delays[0] <= 2.4
    assert delays[2] is not None and delays[2] <= 4.8
    assert all(delay is not None and delay <= 4.8 for delay in delays)


def test_rate_limit_within_budget_is_retried_then_succeeds() -> None:
    calls: list[int] = []
    slept: list[float] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("Please try again in 0.05s. Rate limit")
        return "plan-json"

    result, stats = call_with_resilience(
        flaky, provider="groq", model="m", base_delay=0.01, max_delay=0.05, budget=5.0, sleep=slept.append
    )
    assert result == "plan-json"
    assert (stats.attempts, stats.retries, stats.ok) == (3, 2, True)
    assert len(slept) == 2


def test_exhausted_rate_limit_raises_typed_provider_error_not_agent_error() -> None:
    with pytest.raises(ProviderRateLimitExhaustedError) as excinfo:
        call_with_resilience(
            lambda: (_ for _ in ()).throw(RuntimeError(GROQ_TPD)),
            provider="groq",
            model="openai/gpt-oss-120b",
            budget=15.0,
        )
    error = excinfo.value
    assert error.info.is_rate_limit
    assert is_rate_limit_failure(error)
    assert "rate_limit" in str(error)
    # A daily cap must not burn wall clock.
    assert error.attempts == 1


def test_billing_failure_costs_a_single_attempt_and_chains_the_cause() -> None:
    def boom() -> str:
        raise ValueError("HTTP 402: requires more credits")

    with pytest.raises(ProviderCallFailed) as excinfo:
        call_with_resilience(boom, provider="openrouter", model="m", budget=15.0)
    assert excinfo.value.attempts == 1
    assert not excinfo.value.info.is_rate_limit
    assert isinstance(excinfo.value.__cause__, ValueError)


class _FakeLLM:
    """Stands in for a browser-use chat model."""

    def __init__(self, provider: str, model: str, outcomes: list[Any]) -> None:
        self.provider = provider
        self.model = model
        self.outcomes = outcomes
        self.calls = 0

    async def ainvoke(self, messages: list[Any], output_format: Any = None, **kwargs: Any) -> str:
        self.calls += 1
        outcome = self.outcomes[min(self.calls, len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _slots(*fakes: _FakeLLM) -> list[ProviderSlot]:
    return [ProviderSlot(provider=fake.provider, model=fake.model, llm=fake) for fake in fakes]


def _retry_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_RETRY_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("LLM_RETRY_BASE_DELAY_SEC", "0.01")
    monkeypatch.setenv("LLM_RETRY_MAX_DELAY_SEC", "0.02")
    monkeypatch.setenv("LLM_RETRY_BUDGET_SEC", "0.05")


def test_rate_limited_primary_falls_over_to_the_next_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _retry_fast(monkeypatch)
    primary = _FakeLLM("groq", "gpt-oss", [RuntimeError(GROQ_TPD), RuntimeError(GROQ_TPD)])
    backup = _FakeLLM("gemini", "gemini-2.5-flash", ["gemini-answer"])
    model = FailoverChatModel(_slots(primary, backup))

    assert asyncio.run(model.ainvoke(["msg"], output_format=object())) == "gemini-answer"
    assert primary.calls == 1, "a daily quota must cost exactly one probe"
    assert backup.calls == 1
    assert model.provider == "gemini"
    assert model.summary()["llm_rate_limit_failures"] >= 1


def test_recovered_provider_stays_active_so_quota_is_not_reprobed_each_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _retry_fast(monkeypatch)
    primary = _FakeLLM("groq", "gpt-oss", [RuntimeError(GROQ_TPD), "unused"])
    backup = _FakeLLM("gemini", "gemini-2.5-flash", ["a", "b"])
    model = FailoverChatModel(_slots(primary, backup))

    assert asyncio.run(model.ainvoke(["m"])) == "a"
    assert primary.calls == 1
    assert asyncio.run(model.ainvoke(["m"])) == "b"
    assert primary.calls == 1, "failed primary must not be retried on later steps"


def test_transient_5xx_is_retried_on_the_same_provider_before_failing_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _retry_fast(monkeypatch)
    primary = _FakeLLM("groq", "gpt-oss", [_Status(503, "overloaded"), "recovered"])
    backup = _FakeLLM("gemini", "gemini-2.5-flash", ["unused"])
    model = FailoverChatModel(_slots(primary, backup))

    assert asyncio.run(model.ainvoke(["m"])) == "recovered"
    assert primary.calls == 2 and backup.calls == 0
    stats = model.last_stats
    assert stats is not None and stats.retries == 1


def test_unparseable_model_output_is_an_agent_problem_not_a_provider_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _retry_fast(monkeypatch)
    primary = _FakeLLM("groq", "gpt-oss", [_real_validation_error()])
    backup = _FakeLLM("gemini", "gemini-2.5-flash", ["would-have-answered"])
    model = FailoverChatModel(_slots(primary, backup))

    with pytest.raises(ProviderCallFailed) as excinfo:
        asyncio.run(model.ainvoke(["m"]))
    assert not excinfo.value.info.failover_eligible
    assert not is_rate_limit_failure(excinfo.value)
    assert backup.calls == 0, "agent output failures must not be masked by another provider"


def test_when_every_provider_is_rate_limited_the_failure_stays_attributable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _retry_fast(monkeypatch)
    first = _FakeLLM("groq", "gpt-oss", [RuntimeError(GROQ_TPD)])
    second = _FakeLLM("gemini", "gemini-2.5-flash", [RuntimeError(GROQ_TPD)])
    model = FailoverChatModel(_slots(first, second))

    with pytest.raises(ProviderRateLimitExhaustedError) as excinfo:
        asyncio.run(model.ainvoke(["m"]))
    assert excinfo.value.info.provider == "groq|gemini"
    assert "2 configured LLM provider(s) failed" in str(excinfo.value)


def test_one_request_never_earns_two_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards the invariant that keeps browser actions from being replayed."""
    _retry_fast(monkeypatch)
    answers = iter(["first", "second"])
    llm = _FakeLLM("gemini", "gemini-2.5-flash", [])
    llm.ainvoke = lambda messages, output_format=None, **kwargs: asyncio.sleep(0, result=next(answers))  # type: ignore[method-assign]
    model = FailoverChatModel([ProviderSlot(provider="gemini", model="gemini-2.5-flash", llm=llm)])

    assert asyncio.run(model.ainvoke(["m"])) == "first"
    assert model.summary()["llm_calls"] == 1
    assert model.summary()["llm_attempts"] == 1
