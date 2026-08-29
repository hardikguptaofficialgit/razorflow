"""Generic human handoff policy."""

from __future__ import annotations

from agent_runtime.observation.browser_state import BrowserPage


def handoff_allowed(page: BrowserPage | None, reason: str) -> bool:
    if page and "login_required" in page.signals:
        return True
    lowered = (reason or "").lower()
    allowed_tokens = (
        "login",
        "log in",
        "sign in",
        "otp",
        "captcha",
        "payment confirmation",
        "confirm payment",
        "human",
        "authenticate",
        "two-factor",
        "2fa",
    )
    return any(token in lowered for token in allowed_tokens)
