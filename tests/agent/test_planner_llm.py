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
    _openrouter_complete,
    complete_planner_json,
)


def test_planner_defaults_to_openrouter_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLANNER_LLM_PROVIDER", raising=False)
    from utils import config

    assert config.get_planner_llm_provider() == "openrouter"
    assert config.get_planner_llm_fallback_chain() == ("openrouter", "groq", "gemini")


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


def test_planner_falls_back_to_gemini_when_openrouter_and_groq_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLANNER_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")

    with patch(
        "core.planner_llm._openrouter_complete",
        side_effect=RuntimeError("openrouter down"),
    ):
        with patch("core.planner_llm._groq_complete", side_effect=RuntimeError("groq down")):
            with patch(
                "core.planner_llm._gemini_complete",
                return_value='{"steps":[],"terminal":"continue"}',
            ) as gemini:
                result = complete_planner_json("system", "user")

    assert result == '{"steps":[],"terminal":"continue"}'
    gemini.assert_called_once()


def test_planner_requires_any_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "")
    monkeypatch.setenv("OPENROUTER_API_KEY_3", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")

    with pytest.raises(PlannerConfigurationError):
        complete_planner_json("system", "user")


def test_planner_raises_when_all_configured_providers_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")

    with patch(
        "core.planner_llm._openrouter_complete",
        side_effect=RuntimeError("openrouter down"),
    ):
        with patch("core.planner_llm._groq_complete", side_effect=RuntimeError("groq down")):
            with patch(
                "core.planner_llm._gemini_complete",
                side_effect=RuntimeError("gemini down"),
            ):
                with pytest.raises(PlannerLlmError):
                    complete_planner_json("system", "user")
