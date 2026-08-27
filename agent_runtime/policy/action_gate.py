"""Block actions that escalate beyond the user's declared intent."""

from __future__ import annotations

from agent_runtime.executor.actions import AgentAction
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.task.spec import TaskSpec

_CHECKOUT_MARKERS = ("checkout", "proceed to checkout", "pay now", "payment", "place order")
_CART_NAV_MARKERS = ("view cart", "open cart", "go to cart", "my cart", "shopping cart")


def _action_blob(action: AgentAction) -> str:
    parts = [action.reason.lower()]
    if action.target:
        parts.append((action.target.description or "").lower())
        parts.append((action.target.match_text or "").lower())
    url = str(action.parameters.get("url", "")).lower()
    if url:
        parts.append(url)
    return " ".join(parts)


def _is_checkout_action(action: AgentAction) -> bool:
    blob = _action_blob(action)
    if action.type == "navigate" and "/checkout" in blob:
        return True
    return any(marker in blob for marker in _CHECKOUT_MARKERS)


def _is_payment_action(action: AgentAction) -> bool:
    blob = _action_blob(action)
    return "payment" in blob or "pay now" in blob or "razorpay" in blob


def _is_cart_nav_action(action: AgentAction) -> bool:
    blob = _action_blob(action)
    if action.type == "navigate" and "/cart" in blob:
        return True
    if action.type != "click":
        return False
    if "add" in blob and "cart" in blob:
        return False
    return any(marker in blob for marker in _CART_NAV_MARKERS) or (
        "cart" in blob and "checkout" not in blob
    )


def _is_add_to_cart_action(action: AgentAction) -> bool:
    if action.type != "click":
        return False
    blob = _action_blob(action)
    return "add" in blob and "cart" in blob


def _is_search_action(action: AgentAction) -> bool:
    return action.type in {"search", "type"}


def filter_forbidden_actions(
    spec: TaskSpec,
    actions: list[AgentAction],
) -> tuple[list[AgentAction], list[str]]:
    """Return allowed actions and human-readable block reasons."""
    forbidden = spec.forbidden_actions
    if not forbidden:
        return actions, []

    kept: list[AgentAction] = []
    blocked: list[str] = []
    for action in actions:
        reason: str | None = None
        if "checkout" in forbidden and _is_checkout_action(action):
            reason = "checkout is not part of the user goal"
        elif "payment" in forbidden and _is_payment_action(action):
            reason = "payment is not part of the user goal"
        elif "add_to_cart" in forbidden and _is_add_to_cart_action(action):
            reason = "add_to_cart is not part of the user goal"
        elif "cart_nav" in forbidden and _is_cart_nav_action(action):
            reason = "cart navigation is not part of the user goal"
        elif "search" in forbidden and _is_search_action(action):
            reason = "search is not part of the user goal"
        if reason:
            blocked.append(f"{action.type}: {reason}")
            continue
        kept.append(action)
    return kept, blocked


def handoff_allowed(page: BrowserPage | None, reason: str) -> bool:
    """Handoff is only valid for genuine human-only gates."""
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
