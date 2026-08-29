"""Test-only LLM fixture provider (set AGENT_LLM_TEST_FIXTURE to a JSON file)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_runtime.executor.actions import PlannerOutput
from agent_runtime.planner.llm_provider import _parse_planner_output


class FixtureSequenceProvider:
    """Returns scripted planner responses for E2E failure/recovery tests."""

    def __init__(self, fixture_path: Path) -> None:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        self._responses: list[str] = list(data.get("responses", []))
        self._index = 0

    def plan(
        self,
        system: str,
        user: str,
        *,
        screenshot_data_url: str | None = None,
    ) -> PlannerOutput:
        if not self._responses:
            return PlannerOutput(actions=[])
        raw = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return _parse_planner_output(raw)

    def health_check(self) -> bool:
        return True


def fixture_provider_from_env() -> FixtureSequenceProvider | None:
    raw = os.getenv("AGENT_LLM_TEST_FIXTURE", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_file():
        return None
    return FixtureSequenceProvider(path)
