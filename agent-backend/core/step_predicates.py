"""Shared predicates for planner steps — used by intent filtering and action policy."""

from __future__ import annotations

import re

from core.protocol import ClickElementStep, ReadyForPaymentLinkStep

_STORE_CATEGORY_LABELS = frozenset(
    {
        "all",
        "electronics",
        "personal care",
        "snacks",
        "home",
        "fashion",
    }
)


def is_add_to_cart_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").lower()
    return "add to cart" in label or "buy now" in label


def is_cart_nav_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    if is_add_to_cart_step(step):
        return False
    label = (step.match_text or "").lower().strip()
    if label in {"cart", "go to cart", "view cart", "bag", "basket"}:
        return True
    return "cart" in label and "add" not in label


def is_checkout_step(step) -> bool:
    if isinstance(step, ReadyForPaymentLinkStep):
        return True
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").lower()
    return bool(
        re.search(
            r"proceed to checkout|proceed to buy|checkout|place order|pay now",
            label,
        )
    )


def is_category_nav_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").strip().lower()
    return label in _STORE_CATEGORY_LABELS


def is_remove_step(step) -> bool:
    if not isinstance(step, ClickElementStep):
        return False
    label = (step.match_text or "").lower()
    return "remove" in label
