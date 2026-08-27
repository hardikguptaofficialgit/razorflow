"""LLM provider abstraction for Agent Runtime V2."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from agent_runtime.executor.actions import PlannerOutput
from core.planner_llm import PlannerConfigurationError, complete_planner_json

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


class LLMProvider(Protocol):
    def plan(self, system: str, user: str, *, screenshot_data_url: str | None = None) -> PlannerOutput:
        ...

    def health_check(self) -> bool:
        ...


class ChainLLMProvider:
    """Groq → OpenRouter → Gemini via existing planner_llm infrastructure."""

    def plan(
        self,
        system: str,
        user: str,
        *,
        screenshot_data_url: str | None = None,
    ) -> PlannerOutput:
        raw = complete_planner_json(
            system_prompt=system,
            user_prompt=user,
            screenshot_data_url=screenshot_data_url,
        )
        return _parse_planner_output(raw)

    def health_check(self) -> bool:
        try:
            from utils.config import is_planner_llm_ready

            return is_planner_llm_ready()
        except Exception:
            return False


def _parse_planner_output(raw: str) -> PlannerOutput:
    text = raw.strip()
    block = _JSON_BLOCK_RE.search(text)
    if block:
        text = block.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        data: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Planner returned invalid JSON: {error}") from error
    _normalize_roles(data)
    return PlannerOutput.model_validate(data)


def _normalize_roles(data: dict[str, Any]) -> None:
    for action in data.get("actions", []):
        if not isinstance(action, dict):
            continue
        target = action.get("target")
        if not isinstance(target, dict):
            continue
        role = target.get("role")
        if role in {"searchbox", "textbox", "combobox"}:
            target["role"] = "search" if role == "searchbox" else "input"


def get_default_llm_provider() -> LLMProvider:
    if not ChainLLMProvider().health_check():
        raise PlannerConfigurationError(
            "No planner LLM configured. Set GROQ_API_KEY, OPENROUTER_API_KEY, or GEMINI_API_KEY."
        )
    return ChainLLMProvider()
