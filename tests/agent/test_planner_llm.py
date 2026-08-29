"""Planner LLM fallback chain tests."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.planner_llm import (  # noqa: E402
    PlannerConfigurationError,
    PlannerLlmError,
    _groq_complete,
    _openrouter_complete,
    complete_planner_json,
)


def test_planner_defaults_to_openrouter_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLANNER_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("PLANNER_LLM_PROVIDERS", raising=False)
    from utils import config

    assert config.get_planner_llm_provider() == "openrouter"
    assert config.get_planner_llm_fallback_chain() == (
        "openrouter",
        "groq",
        "vercel_ai_gateway",
        "gemini",
    )


def test_planner_provider_order_can_be_explicitly_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLANNER_LLM_PROVIDERS", "openrouter,groq,gemini")
    from utils import config

    assert config.get_planner_llm_fallback_chain() == (
        "openrouter",
        "groq",
        "gemini",
    )


def test_openrouter_collects_backup_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "key-1")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "key-2")
    monkeypatch.setenv("OPENROUTER_API_KEY_3", "key-3")
    from utils import config

    assert config.get_openrouter_api_keys() == ("key-1", "key-2", "key-3")


def test_openrouter_rotates_to_second_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "bad-key")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "good-key")

    with patch(
        "core.planner_llm._openrouter_complete_with_key",
        side_effect=[RuntimeError("HTTP 401"), '{"ok":true}'],
    ) as complete:
        result = _openrouter_complete("system", "user")

    assert result == '{"ok":true}'
    assert complete.call_count == 2


def test_openrouter_cools_down_limited_key_before_failing_over(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core import planner_llm

    planner_llm._KEY_COOLDOWNS.clear()
    monkeypatch.setenv("OPENROUTER_API_KEY", "limited-key")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "working-key")
    with patch(
        "core.planner_llm._openrouter_complete_with_key",
        side_effect=[RuntimeError("HTTP 429 rate limit"), '{"ok":true}'],
    ):
        assert _openrouter_complete("system", "user") == '{"ok":true}'

    assert any(provider == "OpenRouter" for provider, _ in planner_llm._KEY_COOLDOWNS)


def test_groq_collects_backup_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "key-1")
    monkeypatch.setenv("GROQ_API_KEY_2", "key-2")
    monkeypatch.setenv("GROQ_API_KEY_3", "key-3")
    from utils import config

    assert config.get_groq_api_keys() == ("key-1", "key-2", "key-3")


def test_groq_rotates_to_second_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "bad-key")
    monkeypatch.setenv("GROQ_API_KEY_2", "good-key")

    with patch(
        "core.planner_llm._groq_complete_with_key",
        side_effect=[RuntimeError("HTTP 401"), '{"ok":true}'],
    ) as complete:
        result = _groq_complete("system", "user")

    assert result == '{"ok":true}'
    assert complete.call_count == 2


def test_planner_falls_back_from_openrouter_to_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLANNER_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")

    with patch(
        "core.planner_llm._openrouter_complete",
        side_effect=RuntimeError("openrouter down"),
    ):
        with patch(
            "core.planner_llm._groq_complete",
            return_value='{"steps":[],"terminal":"complete"}',
        ) as groq:
            result = complete_planner_json("system", "user")

    assert result == '{"steps":[],"terminal":"complete"}'
    groq.assert_called_once()


def test_planner_uses_groq_after_openrouter_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLANNER_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")

    with patch(
        "core.planner_llm._openrouter_complete",
        side_effect=RuntimeError("openrouter down"),
    ):
        with patch(
            "core.planner_llm._groq_complete",
            return_value='{"steps":[],"terminal":"continue"}',
        ) as groq:
            result = complete_planner_json("system", "user")

    assert result == '{"steps":[],"terminal":"continue"}'
    groq.assert_called_once()


def test_planner_does_not_fallback_to_disabled_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLANNER_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("PLANNER_LLM_PROVIDERS", "openrouter,groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")

    with patch(
        "core.planner_llm._openrouter_complete",
        side_effect=RuntimeError("openrouter down"),
    ):
        with patch("core.planner_llm._groq_complete", side_effect=RuntimeError("groq down")):
            with pytest.raises(PlannerLlmError):
                complete_planner_json("system", "user")


def test_planner_requires_any_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY_2", "")
    monkeypatch.setenv("GROQ_API_KEY_3", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "")
    monkeypatch.setenv("OPENROUTER_API_KEY_3", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEYS", "")
    monkeypatch.setenv("GROQ_API_KEYS", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "")
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "")

    with pytest.raises(PlannerConfigurationError):
        complete_planner_json("system", "user")


def test_planner_raises_when_all_configured_providers_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "AI_GATEWAY_API_KEY", "VERCEL_OIDC_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    with patch(
        "core.planner_llm._openrouter_complete",
        side_effect=RuntimeError("openrouter down"),
    ):
        with patch("core.planner_llm._groq_complete", side_effect=RuntimeError("groq down")):
            with pytest.raises(PlannerLlmError):
                complete_planner_json("system", "user")
