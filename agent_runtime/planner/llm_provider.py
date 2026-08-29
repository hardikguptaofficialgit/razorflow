"""LLM provider abstraction for Agent Runtime V2."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from pydantic import ValidationError

from agent_runtime.executor.actions import PlannerOutput, TargetRole
from core.planner_llm import PlannerConfigurationError, complete_planner_json

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


class LLMProvider(Protocol):
    def plan(self, system: str, user: str, *, screenshot_data_url: str | None = None) -> PlannerOutput:
        ...

    def health_check(self) -> bool:
        ...


class ChainLLMProvider:
    """OpenRouter → Groq planner chain via existing planner_llm infrastructure."""

    def plan(
        self,
        system: str,
        user: str,
        *,
        screenshot_data_url: str | None = None,
        run_config: object | None = None,
    ) -> PlannerOutput:
        raw = complete_planner_json(
            system_prompt=system,
            user_prompt=user,
            screenshot_data_url=screenshot_data_url,
            run_config=run_config,
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
    try:
        return PlannerOutput.model_validate(data)
    except ValidationError:
        _coerce_planner_payload(data)
        return PlannerOutput.model_validate(data)


def _canonical_role(role: Any, *, action_type: str | None = None) -> TargetRole | None:
    if not isinstance(role, str):
        return None
    normalized = role.strip().lower().replace("_", " ").replace("-", " ")
    aliases: dict[str, TargetRole] = {
        "search": "search",
        "searchbox": "search",
        "search input": "search",
        "textbox": "input",
        "combobox": "input",
        "input": "input",
        "button": "button",
        "btn": "button",
        "link": "link",
        "anchor": "link",
    }
    if normalized in aliases:
        return aliases[normalized]
    if "/" in normalized:
        for part in normalized.split("/"):
            canonical = _canonical_role(part.strip(), action_type=action_type)
            if canonical:
                return canonical
    if "search" in normalized:
        return "search"
    if "input" in normalized or "text" in normalized:
        return "input"
    if "button" in normalized:
        return "button"
    if "link" in normalized:
        return "link"
    if action_type == "search":
        return "search"
    if action_type in {"click", "select"}:
        return "button"
    return None


def _normalize_roles(data: dict[str, Any]) -> None:
    for action in data.get("actions", []):
        if not isinstance(action, dict):
            continue
        action_type = action.get("type") if isinstance(action.get("type"), str) else None
        target = action.get("target")
        if not isinstance(target, dict):
            continue
        canonical = _canonical_role(target.get("role"), action_type=action_type)
        if canonical:
            target["role"] = canonical


def _coerce_planner_payload(data: dict[str, Any]) -> None:
    _normalize_roles(data)
    for action in data.get("actions", []):
        if not isinstance(action, dict):
            continue
        action_type = action.get("type") if isinstance(action.get("type"), str) else None
        target = action.get("target")
        if isinstance(target, dict) and not target.get("role"):
            fallback = _canonical_role(None, action_type=action_type)
            if fallback:
                target["role"] = fallback


def get_default_llm_provider() -> LLMProvider:
    from agent_runtime.planner.fixture_provider import fixture_provider_from_env

    fixture = fixture_provider_from_env()
    if fixture is not None:
        return fixture
    if not ChainLLMProvider().health_check():
        raise PlannerConfigurationError(
            "No planner LLM configured. Set OPENROUTER_API_KEY or GROQ_API_KEY."
        )
    return ChainLLMProvider()
