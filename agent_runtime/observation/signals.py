"""Generic page signals — auth/dialog only, no commerce paths."""

from __future__ import annotations

import re

from core.protocol import PageContext

_AUTH_RE = re.compile(
    r"\b(?:sign\s*in|log\s*in|create\s+account|register|password|otp|captcha)\b",
    re.I,
)


def _element_blob(page: PageContext) -> str:
    parts: list[str] = []
    for el in page.elements[:40]:
        parts.extend([el.text, el.aria_label, el.placeholder])
    return " ".join(parts).lower()


def infer_generic_page_signals(page: PageContext) -> list[str]:
    signals: list[str] = []
    blob = _element_blob(page)
    title = (page.title or "").lower()
    combined = f"{title} {blob}"

    if _AUTH_RE.search(combined) and re.search(
        r"\b(?:modal|dialog|form|email|password)\b", combined, re.I
    ):
        signals.append("login_required")
    if re.search(r"close dialog", blob, re.I) and _AUTH_RE.search(blob):
        signals.append("login_required")

    return signals
