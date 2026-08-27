"""Repair common LLM planner output defects before validation."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from core.protocol import PageContext, TargetRole


def _infer_role_from_match(match_text: str | None, action: str) -> TargetRole:
    label = (match_text or "").lower()
    if action == "type_in_element":
        return "search"
    if "cart" in label and "add" not in label:
        return "link"
    if label in {"search", "submit"} or "search" in label:
        return "button"
    if "add to cart" in label or "buy now" in label or "remove" in label:
        return "button"
    return "button"


def _role_from_page(page: PageContext, element_index: int | None) -> TargetRole | None:
    if element_index is None:
        return None
    for element in page.elements:
        if element.index == element_index:
            return element.role
    if 1 <= element_index <= len(page.elements):
        return page.elements[element_index - 1].role
    return None


def repair_planner_step(step: dict[str, Any], page: PageContext | None) -> dict[str, Any]:
    if not isinstance(step, dict):
        return step

    action = step.get("action")
    if action in {"click_element", "type_in_element", "highlight_element"}:
        if not step.get("role"):
            role = None
            if page is not None:
                role = _role_from_page(page, step.get("elementIndex"))
            step["role"] = role or _infer_role_from_match(
                step.get("matchText"),
                action,
            )

    if action == "navigate_url" and page is not None:
        url = step.get("url") or ""
        if url.startswith("/"):
            parsed = urlparse(page.url)
            if parsed.scheme and parsed.netloc:
                step["url"] = f"{parsed.scheme}://{parsed.netloc}{url}"

    return step


def repair_planner_payload(
    payload: dict[str, Any],
    page: PageContext | None,
) -> dict[str, Any]:
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return payload
    repaired = [repair_planner_step(step, page) for step in steps]
    return {**payload, "steps": repaired}
