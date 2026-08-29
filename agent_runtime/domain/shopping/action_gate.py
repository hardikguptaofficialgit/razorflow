"""Block actions that escalate beyond the user's declared intent."""

from __future__ import annotations

from agent_runtime.domain.shopping.checkout_controls import is_checkout_control_element
from agent_runtime.observation.browser_state import ObservedElement
from agent_runtime.domain.shopping.helpers import allows_add_to_cart
from agent_runtime.domain.shopping.spec import GoalPhase, forbidden_for_phase
from agent_runtime.task.spec import TaskSpec

_CHECKOUT_MARKERS = (
    "checkout",
    "proceed to checkout",
    "proceed to check",
    "pay now",
    "payment",
    "place order",
)
_CART_NAV_MARKERS = ("view cart", "open cart", "go to cart", "my cart", "shopping cart")
_PRODUCT_NAV_MARKERS = (
    "product details",
    "view product",
    "open product",
    "see details",
    "learn more",
)


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
    if any(marker in blob for marker in _CHECKOUT_MARKERS):
        return True
    if action.target:
        el = ObservedElement(
            element_id=action.target.element_id or "",
            index=0,
            role=action.target.role or "",
            tag="",
            text=action.target.description or action.target.match_text or "",
            placeholder="",
            aria_label=action.target.description or "",
            href=str(action.parameters.get("url", "")),
        )
        if is_checkout_control_element(el):
            return True
    return False


def _is_payment_action(action: AgentAction) -> bool:
    blob = _action_blob(action)
    return "payment" in blob or "pay now" in blob or "razorpay" in blob


def _is_cart_nav_action(action: AgentAction) -> bool:
    if _is_checkout_action(action):
        return False
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
    return action.type == "search" or (
        action.type == "type"
        and action.target is not None
        and (
            action.target.role == "search"
            or "search" in _action_blob(action)
        )
    )


def _is_product_details_action(action: AgentAction) -> bool:
    if _is_checkout_action(action):
        return False
    blob = _action_blob(action)
    if action.type == "navigate" and "/product" in blob:
        return True
    if action.type != "click":
        return False
    if "add" in blob and "cart" in blob:
        return False
    if any(marker in blob for marker in _PRODUCT_NAV_MARKERS):
        return True
    # Product title/link click on search results (link role, not add-to-cart).
    if action.target and action.target.role == "link":
        if "add" not in blob and "cart" not in blob:
            return True
    return False


def classify_action(action: AgentAction) -> set[str]:
    """Return semantic action categories for auditing."""
    categories: set[str] = set()
    if _is_search_action(action):
        categories.add("search")
    if _is_product_details_action(action):
        categories.add("product_details")
    if _is_add_to_cart_action(action):
        categories.add("add_to_cart")
    if _is_cart_nav_action(action):
        categories.add("cart_nav")
    if _is_checkout_action(action):
        categories.add("checkout")
    if _is_payment_action(action):
        categories.add("payment")
    return categories


def _is_login_nav_action(action: AgentAction) -> bool:
    blob = _action_blob(action)
    return any(token in blob for token in ("sign in", "log in", "login", "sign up"))


def active_forbidden(spec: TaskSpec, current_phase: GoalPhase) -> frozenset[str]:
    return forbidden_for_phase(current_phase)


def filter_forbidden_actions(
    spec: TaskSpec,
    actions: list[AgentAction],
    *,
    current_phase: GoalPhase | None = None,
    state: RunState | None = None,
) -> tuple[list[AgentAction], list[str]]:
    """Return allowed actions and human-readable block reasons."""
    phase: GoalPhase = current_phase or spec.target_phase
    forbidden = active_forbidden(spec, phase)
    if not allows_add_to_cart(spec):
        forbidden = forbidden | frozenset({"add_to_cart", "checkout", "payment"})
    if state is not None:
        if state.memory.items_added >= state.parsed_task.item_count and state.parsed_task.item_count > 0:
            forbidden = forbidden | frozenset({"add_to_cart"})

    kept: list[AgentAction] = []
    blocked: list[str] = []
    for action in actions:
        reason: str | None = None
        if "checkout" in forbidden and _is_checkout_action(action):
            reason = "checkout is not allowed in the current goal phase"
        elif "payment" in forbidden and _is_payment_action(action):
            reason = "payment is not allowed in the current goal phase"
        elif "add_to_cart" in forbidden and _is_add_to_cart_action(action):
            reason = "add_to_cart is not allowed in the current goal phase"
        elif "cart_nav" in forbidden and _is_cart_nav_action(action):
            reason = "cart navigation is not allowed in the current goal phase"
        elif "search" in forbidden and _is_search_action(action):
            reason = "search is not allowed in the current goal phase"
        elif "product_details" in forbidden and _is_product_details_action(action):
            reason = "opening product details is not allowed in the current goal phase"
        elif phase in {"checkout", "checkout_reached"} and _is_login_nav_action(action) and not _is_checkout_action(action):
            reason = (
                "header sign-in is not checkout — use a checkout navigation control from observation"
            )
        if reason and phase in {"checkout", "checkout_reached"}:
            reason = (
                f"{reason} — CURRENT_PHASE=checkout; cart is ready; advance to checkout only"
            )
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
