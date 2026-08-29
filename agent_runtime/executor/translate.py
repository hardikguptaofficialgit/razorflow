"""Translate V2 actions to legacy wire ActionStep types."""

from __future__ import annotations

import re

from agent_runtime.executor.actions import AgentAction
from core.protocol import (
    ActionStep,
    ClickElementStep,
    GoBackStep,
    HighlightElementStep,
    NavigateUrlStep,
    ScrollPageStep,
    TypeInElementStep,
    WaitForUserStep,
    WaitStep,
)

_ELEMENT_ID_RE = re.compile(r"^e(\d+)$", re.I)


def _element_index(action: AgentAction) -> int | None:
    if action.target is None or not action.target.element_id:
        return None
    match = _ELEMENT_ID_RE.match(action.target.element_id.strip())
    if not match:
        return None
    return int(match.group(1))


def _role(action: AgentAction) -> str:
    if action.target and action.target.role:
        return action.target.role
    if action.type == "search":
        return "search"
    if action.type == "type":
        return "input"
    return "button"


def _match_text(action: AgentAction) -> str | None:
    if action.target is None:
        return None
    if action.target.match_text:
        return action.target.match_text
    if action.target.description:
        return action.target.description
    return None


def translate_action(action: AgentAction) -> list[ActionStep]:
    idx = _element_index(action)
    role = _role(action)
    match = _match_text(action)

    if action.type == "handoff":
        return [WaitForUserStep(action="wait_for_user")]

    if action.type == "finish":
        return []

    if action.type == "navigate":
        url = str(action.parameters.get("url", "")).strip()
        if not url:
            return []
        return [NavigateUrlStep(action="navigate_url", url=url)]

    if action.type == "go_back":
        return [GoBackStep(action="go_back")]

    if action.type == "wait":
        duration = action.parameters.get("duration_ms") or action.parameters.get("ms") or 500
        try:
            ms = int(duration)
        except (TypeError, ValueError):
            ms = 500
        ms = max(100, min(5000, ms))
        return [WaitStep(action="wait", durationMs=ms)]

    if action.type in {"search", "type"}:
        text = str(
            action.parameters.get("query")
            or action.parameters.get("text")
            or ""
        ).strip()
        if not text:
            return []
        return [
            TypeInElementStep(
                action="type_in_element",
                role=role if role in {"search", "input"} else "search",
                text=text,
                elementIndex=idx,
                matchText=match,
            )
        ]

    if action.type == "click":
        return [
            ClickElementStep(
                action="click_element",
                role=role if role in {"search", "input", "button", "link"} else "button",
                elementIndex=idx,
                matchText=match,
            )
        ]

    if action.type == "scroll":
        direction = str(action.parameters.get("direction", "down")).lower()
        if direction not in {"up", "down", "top", "bottom"}:
            direction = "down"
        amount = action.parameters.get("amount_px") or action.parameters.get("amount") or 600
        try:
            amount_px = int(amount)
        except (TypeError, ValueError):
            amount_px = 600
        amount_px = max(100, min(2000, amount_px))
        if idx is not None:
            return [
                HighlightElementStep(
                    action="highlight_element",
                    role="button",
                    elementIndex=idx,
                    matchText=match,
                )
            ]
        return [
            ScrollPageStep(
                action="scroll_page",
                direction=direction,  # type: ignore[arg-type]
                amountPx=amount_px,
            )
        ]

    return []
