"""Task interpretation — actionable vs needs clarification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from core.search_query import extract_search_query
from core.task_intent import TaskIntent, parse_task_intent

TaskStatus = Literal["actionable", "needs_clarification"]

_SHOP_VERB_RE = re.compile(
    r"\b("
    r"search|find|look\s+for|show\s+me|browse|buy|purchase|order|shop|"
    r"add|put|place|cart|checkout|check\s*out|remove|delete|view|open|see|"
    r"compare|get|grab|pick\s+up|earbuds?|snacks?|shampoo|product|checkout"
    r")\b",
    re.I,
)
_GIBBERISH_RE = re.compile(r"^[^a-zA-Z0-9]*$")


@dataclass(frozen=True)
class TaskInterpretation:
    intent: TaskIntent
    status: TaskStatus
    reason: str | None = None

    @property
    def actionable(self) -> bool:
        return self.status == "actionable"


def _looks_gibberish(task: str) -> bool:
    cleaned = re.sub(r"\s+", "", task.strip().lower())
    if len(cleaned) < 2:
        return True
    if _GIBBERISH_RE.match(cleaned):
        return True
    if len(set(cleaned)) == 1 and len(cleaned) >= 3:
        return True
    if len(cleaned) <= 4 and not _SHOP_VERB_RE.search(task):
        return True
    return False


def interpret_task(task: str) -> TaskInterpretation:
    raw = task.strip()
    intent = parse_task_intent(raw)

    if not raw:
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason="Please describe what you want to search, add, or buy.",
        )

    if _looks_gibberish(raw):
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason=(
                "I could not understand that request. Try something like "
                "'search for wireless earbuds' or 'add snacks under ₹200'."
            ),
        )

    if not _SHOP_VERB_RE.search(raw):
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason=(
                "That does not look like a shopping task. "
                "Ask me to search, add to cart, view cart, or checkout."
            ),
        )

    query = extract_search_query(raw)
    if intent.goal in {"search", "add_to_cart", "compare"} and len(query) < 2:
        return TaskInterpretation(
            intent=intent,
            status="needs_clarification",
            reason="Please name a product or category to search for.",
        )

    return TaskInterpretation(intent=intent, status="actionable")
