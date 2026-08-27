"""Tests for LLM provider factory selection (OSS BYO only)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from browser_use.llm.groq.chat import ChatGroq
from browser_use.llm.openai.chat import ChatOpenAI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))


def test_paid_browser_use_llm_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "browser_use")
    monkeypatch.setenv("BROWSER_USE_API_KEY", "bu-test-key")

    from core import llm_factory
    from utils import config

    # Config remaps paid provider away from ChatBrowserUse.
    assert config.get_llm_provider() == "gemini"

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    # Direct factory call still refuses paid aliases if somehow requested.
    monkeypatch.setattr(llm_factory, "get_llm_provider", lambda: "browser_use")
    with pytest.raises(RuntimeError, match="disabled"):
        llm_factory.create_browser_use_llm()


def test_create_browser_use_llm_llamacpp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "llamacpp")
    monkeypatch.setenv("LLAMACPP_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("LLAMACPP_MODEL", "qwen2.5-7b-instruct")

    from core import llm_factory

    llm = llm_factory.create_browser_use_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model == "qwen2.5-7b-instruct"
    assert str(llm.base_url).rstrip("/") == "http://127.0.0.1:8080/v1"
    assert llm.add_schema_to_system_prompt is True
    assert llm.dont_force_structured_output is True


def test_create_browser_use_llm_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    from browser_use.llm.google.chat import ChatGoogle
    from core import llm_factory

    llm = llm_factory.create_browser_use_llm()
    assert isinstance(llm, ChatGoogle)
    assert llm.model == "gemini-2.5-flash-lite"
    assert llm.api_key == "test-gemini-key"


def test_create_browser_use_llm_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite:nitro")

    from browser_use.llm.openrouter.chat import ChatOpenRouter
    from core import llm_factory

    llm = llm_factory.create_browser_use_llm()
    assert isinstance(llm, ChatOpenRouter)
    assert llm.model == "google/gemini-2.5-flash-lite:nitro"


def test_create_browser_use_llm_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")

    from core import llm_factory

    llm = llm_factory.create_browser_use_llm()
    assert isinstance(llm, ChatGroq)
    assert llm.model == "openai/gpt-oss-120b"
