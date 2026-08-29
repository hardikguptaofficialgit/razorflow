"""Task interpretation — actionable vs needs clarification (generic)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from core.generic_utils import looks_like_gibberish
from core.search_query import extract_search_query
from core.task_intent import TaskIntent, parse_task_intent

TaskStatus = Literal["actionable", "needs_clarification"]

# Generic action verbs - not shopping-specific
_ACTION_VERB_RE = re.compile(
    r"\b("
    r"search|find|look\s+for|show\s+me|browse|click|open|go\s+to|navigate|"
    r"type|enter|fill|submit|scroll|select|choose|compare|get|download|"
    r"add|remove|delete|view|check|verify|confirm"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class TaskInterpretation:
    intent: TaskIntent
    status: TaskStatus
    reason: str | None = None

    @property
    def actionable(self) -> bool:
        return self.status == "actionable"


def _looks_gibberish(task: str) -> bool:
    """Use generic gibberish detection from utilities."""
    return looks_like_gibberish(task)


def interpret_task(task: str) -> TaskInterpretation:
    """Generic task interpretation - accepts any browser automation task."""
    raw = task.strip()
    intent = parse_task_intent(raw)

    if not raw:
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason="Please describe what you want to do (e.g., 'search for X', 'click the button', 'fill the form').",
        )

    if _looks_gibberish(raw):
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason=(
                "I could not understand that request. "
                "Please provide a clear task description."
            ),
        )

    # Optional: Check for action verbs (not required, but helps with unclear tasks)
    if len(raw.split()) < 3 and not _ACTION_VERB_RE.search(raw):
        # Very short tasks without action verbs might be unclear
        # But we still allow them - LLM can figure it out from context
        pass

    return TaskInterpretation(intent=intent, status="actionable")
