"""Planner configuration tests."""

from __future__ import annotations

import pytest

from core.planner import _plan_next_chunk_with_llm
from core.planner_llm import PlannerConfigurationError
from core.run_manager import RunSession


def test_plan_next_chunk_requires_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("PLANNER_LLM_PROVIDER", "groq")
    session = RunSession(run_id="run-1", task="find shampoo")

    with pytest.raises(PlannerConfigurationError):
        _plan_next_chunk_with_llm(session, None, "page_context_only")
