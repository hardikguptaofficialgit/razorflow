"""Shopping-specific task phases and intents (domain layer only)."""

from __future__ import annotations

from typing import Literal

TaskIntent = Literal[
    "search",
    "add_to_cart",
    "view_cart",
    "checkout",
    "purchase",
    "remove",
    "compare",
    "unknown",
]

GoalPhase = Literal[
    "search_results",
    "product_details",
    "cart_updated",
    "cart_visible",
    "checkout",
    "checkout_reached",
    "purchase_reached",
    "item_removed",
]

FORBIDDEN_BY_PHASE: dict[GoalPhase, frozenset[str]] = {
    "search_results": frozenset(
        {"product_details", "add_to_cart", "checkout", "payment", "cart_nav"}
    ),
    "product_details": frozenset({"add_to_cart", "checkout", "payment", "cart_nav"}),
    "cart_updated": frozenset({"checkout", "payment"}),
    "cart_visible": frozenset({"checkout", "payment", "add_to_cart", "search"}),
    "checkout": frozenset({"payment", "search", "add_to_cart", "product_details"}),
    "checkout_reached": frozenset(
        {"payment", "search", "add_to_cart", "product_details"}
    ),
    "purchase_reached": frozenset(),
    "item_removed": frozenset({"checkout", "payment", "add_to_cart", "search"}),
}


def forbidden_for_phase(phase: GoalPhase) -> frozenset[str]:
    return FORBIDDEN_BY_PHASE.get(phase, frozenset())


COMPLETION_BY_PHASE: dict[GoalPhase, str] = {
    "search_results": "Relevant search results are visible; do not open product pages.",
    "product_details": "The selected product details page is open.",
    "cart_updated": "Requested product(s) are verified in the cart.",
    "cart_visible": "Cart page is open and cart contents are visible.",
    "checkout": "Navigate to checkout using a visible checkout control.",
    "checkout_reached": "Checkout page or login gate before checkout is reached.",
    "purchase_reached": "Purchase flow reached per policy.",
    "item_removed": "Requested item is no longer in the cart.",
}

FORBIDDEN_BY_INTENT: dict[TaskIntent, frozenset[str]] = {
    "search": frozenset(),
    "compare": frozenset(),
    "add_to_cart": frozenset(),
    "view_cart": frozenset(),
    "remove": frozenset(),
    "checkout": frozenset(),
    "purchase": frozenset(),
    "unknown": frozenset(),
}


def phase_for_intent(intent: TaskIntent) -> GoalPhase:
    mapping: dict[TaskIntent, GoalPhase] = {
        "search": "search_results",
        "compare": "search_results",
        "add_to_cart": "cart_updated",
        "view_cart": "cart_visible",
        "checkout": "checkout",
        "purchase": "purchase_reached",
        "remove": "item_removed",
        "unknown": "search_results",
    }
    return mapping[intent]
