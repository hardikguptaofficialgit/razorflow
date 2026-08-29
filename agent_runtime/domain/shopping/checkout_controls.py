"""Semantically detect checkout navigation controls on any page."""

from __future__ import annotations

import re

from core.protocol import PageContext

from agent_runtime.observation.browser_state import BrowserPage, ObservedElement

_CHECKOUT_CONTROL_RE = re.compile(
    r"\b(?:"
    r"checkout|proceed\s+to\s+(?:checkout|check|pay)|continue\s+to\s+checkout|"
    r"go\s+to\s+checkout|continue\s+checkout|place\s+order"
    r")\b",
    re.I,
)


def is_checkout_control_element(element: ObservedElement) -> bool:
    blob = " ".join(
        part
        for part in (element.text, element.aria_label, element.href, element.placeholder)
        if part
    ).lower()
    if _CHECKOUT_CONTROL_RE.search(blob):
        return True
    if "/checkout" in element.href.lower():
        return True
    return False


def discover_checkout_controls(page: BrowserPage) -> list[ObservedElement]:
    return [el for el in page.elements if is_checkout_control_element(el)]


def format_checkout_controls_section(page: BrowserPage) -> str:
    controls = discover_checkout_controls(page)
    if not controls:
        return ""
    lines = ["Checkout-capable controls (semantically detected):"]
    for el in controls[:8]:
        label = el.text or el.aria_label or el.tag
        href = f" href={el.href}" if el.href else ""
        enabled = "enabled" if el.enabled else "disabled"
        lines.append(
            f"- [{el.element_id}] {el.role}/{el.tag} \"{label[:80]}\" ({enabled}){href}"
        )
    return "\n".join(lines)


def detect_store_checkout_auth_gate(page: PageContext) -> bool:
    """Demo-store auth gate marker — optional commerce extension, not generic web."""
    if not (page.cart_lines or page.products):
        return False
    for el in page.elements[:40]:
        if el.tag == "data-rf-checkout-auth-gate":
            return True
        if "checkout-login-gate" in (el.aria_label or "").lower():
            return True
    return False
