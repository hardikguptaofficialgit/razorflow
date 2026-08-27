"""Parse the user's intended end-state for a shopping task."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

from core.protocol import PlannerChunkOutput, ReadyForPaymentLinkStep
from core.run_manager import RunSession
from core.search_query import extract_product_queries, extract_search_query
from core.step_predicates import (
    is_add_to_cart_step,
    is_cart_nav_step,
    is_checkout_step,
)

TaskGoal = Literal[
    "search",
    "add_to_cart",
    "view_cart",
    "checkout",
    "purchase",
    "compare",
    "update_cart",
    "remove",
]

_CHECKOUT_RE = re.compile(
    r"\b(?:proceed\s+to\s+)?checkout\b|\bcheck\s*out\b",
    re.I,
)
_DEFER_CHECKOUT_RE = re.compile(
    r"\b(?:let\s+me\s+know|tell\s+me|notify\s+me|ask\s+(?:me|before)|before\s+(?:you\s+)?(?:place|placing|doing))\b.*\bcheckout\b"
    r"|\bcheckout\b.*\b(?:let\s+me\s+know|tell\s+me|ask\s+(?:me|before)|notify)\b",
    re.I,
)
_PURCHASE_RE = re.compile(
    r"\b(?:buy|purchase|order|pay(?:\s+for)?|complete\s+(?:the\s+)?(?:order|purchase))\b",
    re.I,
)
_VIEW_CART_RE = re.compile(
    r"\b(?:view|open|show|see|go\s+to)\s+(?:my\s+)?(?:cart|bag|basket)\b",
    re.I,
)
_ADD_TO_CART_RE = re.compile(
    r"\b(?:add(?:\s+me)?|put|place)\b.*\b(?:cart|bag|basket)\b|"
    r"\badd\s+(?:me\s+)?(?:some|a|an|the)?\b",
    re.I,
)
_SEARCH_RE = re.compile(
    r"\b(?:find|search|look\s+for|show\s+me|browse|explore|compare)\b",
    re.I,
)
_COMPARE_RE = re.compile(r"\bcompare\b", re.I)
_REMOVE_ITEM_RE = re.compile(
    r"\b(?:remove|delete)\b[^.]{0,80}\b(?:from\s+(?:my\s+)?cart|cart)\b|"
    r"\bremove\s+(?:the\s+)?(.+?)\s+from\b",
    re.I,
)
_UPDATE_RE = re.compile(r"\b(?:update|change|increase|decrease)\b.*\b(?:qty|quantity)\b", re.I)
_SOME_ITEMS_RE = re.compile(r"\b(?:some|few|couple|several)\b", re.I)
_QTY_ADD_RE = re.compile(r"\badd\s+(\d+)\b", re.I)


@dataclass(frozen=True)
class TaskIntent:
    goal: TaskGoal
    raw_task: str
    add_target_count: int = 1
    product_queries: tuple[str, ...] = ()
    remove_target: str | None = None
    requires_cart_view: bool = False
    requires_checkout: bool = False
    requires_payment: bool = False

    def prompt_block(self) -> str:
        lines = [
            "TASK GOAL (authoritative — do not exceed this scope):",
            f"- goal: {self.goal}",
        ]
        if self.goal == "search":
            lines.append("- stop when relevant search results are visible; do NOT add to cart")
        elif self.goal == "add_to_cart":
            lines.append(
                f"- stop after adding {self.add_target_count} suitable product(s) to cart"
            )
            if self.add_target_count > 1:
                lines.append(
                    f"- quantity target: {self.add_target_count} — you may click Add to cart "
                    "multiple times on the same or different qualifying products"
                )
            if len(self.product_queries) >= 2:
                listed = ", ".join(f"'{query}'" for query in self.product_queries)
                lines.append(
                    f"- multi-item list: search and add ONE product per item ({listed}); "
                    "never combine into a single search query"
                )
            lines.append("- do NOT open cart, checkout, or pay unless explicitly asked")
        elif self.goal == "view_cart":
            lines.append("- stop when the cart page is open")
        elif self.goal == "checkout":
            lines.append("- stop at checkout review; do NOT pay unless asked")
        elif self.goal == "purchase":
            lines.append("- complete the purchase flow through payment when possible")
        elif self.goal == "compare":
            lines.append("- compare visible products; do NOT checkout")
        elif self.goal == "remove":
            lines.append("- remove the named item from cart, then complete")
        lines.append(f"- user_request: {self.raw_task[:120]}")
        return "\n".join(lines)


def parse_task_intent(task: str) -> TaskIntent:
    raw = task.strip()
    lowered = raw.lower()

    requires_checkout = bool(_CHECKOUT_RE.search(raw))
    if _DEFER_CHECKOUT_RE.search(raw):
        requires_checkout = False
    explicit_checkout = requires_checkout
    requires_payment = bool(_PURCHASE_RE.search(raw))
    requires_cart_view = bool(_VIEW_CART_RE.search(raw))

    goal: TaskGoal = "search"
    add_target = 1
    remove_target: str | None = None

    if _REMOVE_ITEM_RE.search(raw):
        goal = "remove"
        remove_match = re.search(
            r"\bremove\s+(?:the\s+)?(.+?)\s+from",
            raw,
            re.I,
        )
        remove_target = remove_match.group(1).strip() if remove_match else None
    elif _UPDATE_RE.search(raw):
        goal = "update_cart"
    elif _COMPARE_RE.search(raw) and not requires_checkout and not requires_payment:
        goal = "compare"
    elif requires_payment:
        goal = "purchase"
        requires_checkout = True
    elif requires_checkout:
        goal = "checkout"
    elif requires_cart_view and not _ADD_TO_CART_RE.search(raw):
        goal = "view_cart"
    elif _ADD_TO_CART_RE.search(raw) or re.search(
        r"\badd\b.*\b(?:snacks?|products?|items?)\b", lowered
    ):
        goal = "add_to_cart"
        if _SOME_ITEMS_RE.search(raw):
            add_target = 2
        qty_match = _QTY_ADD_RE.search(raw)
        if qty_match:
            try:
                add_target = max(1, min(int(qty_match.group(1)), 5))
            except ValueError:
                pass
    elif _SEARCH_RE.search(raw):
        goal = "search"
    elif re.search(r"\b(?:get|grab|pick\s+up)\b", lowered):
        goal = "add_to_cart"

    if goal == "add_to_cart" and requires_checkout:
        goal = "checkout"
    if goal == "checkout" and requires_payment:
        goal = "purchase"

    product_queries = tuple(extract_product_queries(raw))
    if len(product_queries) >= 2:
        add_target = max(add_target, len(product_queries))
        # "buy me butter, chips, cooker" is a shopping list — add items, not full payment.
        if not explicit_checkout:
            requires_payment = False
            requires_checkout = False
            if goal == "purchase":
                goal = "add_to_cart"

    return TaskIntent(
        goal=goal,
        raw_task=raw,
        add_target_count=add_target,
        product_queries=product_queries,
        remove_target=remove_target,
        requires_cart_view=requires_cart_view or goal in {"view_cart", "checkout", "purchase", "remove"},
        requires_checkout=requires_checkout or goal in {"checkout", "purchase"},
        requires_payment=requires_payment or goal == "purchase",
    )


def goal_allows_checkout(goal: TaskGoal) -> bool:
    return goal in {"checkout", "purchase"}


def goal_allows_cart_nav(goal: TaskGoal) -> bool:
    return goal in {"view_cart", "checkout", "purchase", "update_cart", "remove"}


def goal_allows_payment(goal: TaskGoal) -> bool:
    return goal == "purchase"


def goal_allows_add_to_cart(goal: TaskGoal) -> bool:
    return goal in {"add_to_cart", "checkout", "purchase"}


def count_successful_adds(session: RunSession) -> int:
    count = 0
    for entry in session.history:
        if not entry.success:
            continue
        step = entry.step
        if getattr(step, "action", "") != "click_element":
            continue
        label = (getattr(step, "match_text", "") or "").lower()
        if "add to cart" in label or "buy now" in label:
            count += 1
    return count


def used_add_element_indices(session: RunSession) -> set[int]:
    indices: set[int] = set()
    for entry in session.history:
        if not entry.success:
            continue
        step = entry.step
        if getattr(step, "action", "") != "click_element":
            continue
        label = (getattr(step, "match_text", "") or "").lower()
        if "add to cart" not in label and "buy now" not in label:
            continue
        index = getattr(step, "element_index", None)
        if index:
            indices.add(index)
    return indices


def get_active_product_query(intent: TaskIntent, session: RunSession) -> str:
    """Return the search query for the next product to add in a multi-item task."""
    if intent.product_queries:
        adds = count_successful_adds(session)
        index = min(
            adds + session.skipped_product_queries,
            len(intent.product_queries) - 1,
        )
        return intent.product_queries[index]
    return extract_search_query(intent.raw_task)


def is_goal_satisfied(session: RunSession, intent: TaskIntent, page) -> bool:
    if page is None:
        return False

    path = urlparse(page.url).path.lower()

    if intent.goal == "search":
        return path.startswith("/search") and bool(page.products)

    if intent.goal == "add_to_cart":
        return count_successful_adds(session) >= intent.add_target_count

    if intent.goal == "view_cart":
        return path.startswith("/cart")

    if intent.goal in {"checkout", "purchase"}:
        url = (page.url or "").lower()
        path = urlparse(page.url).path.lower()
        if path.startswith("/checkout"):
            return True
        if "auth=login" in url and "next=/checkout" in url.replace("%2f", "/"):
            return True
        if any(
            getattr(el, "tag", "") in {"data-rf-auth-required", "data-rf-checkout-gate"}
            for el in page.elements
        ):
            return True
        return False

    if intent.goal == "compare":
        return path.startswith("/search") and len(page.products) >= 2

    if intent.goal == "remove":
        if not path.startswith("/cart"):
            return False
        if not intent.remove_target:
            return True
        target = intent.remove_target.lower()
        return not any(target in line.title.lower() for line in page.cart_lines)

    return False


def complete_chunk() -> PlannerChunkOutput:
    return PlannerChunkOutput(steps=[], terminal="complete")


def filter_steps_for_goal(
    steps: list,
    intent: TaskIntent,
) -> list:
    filtered: list = []
    for step in steps:
        if is_checkout_step(step) and not goal_allows_checkout(intent.goal):
            continue
        if isinstance(step, ReadyForPaymentLinkStep) and not goal_allows_payment(intent.goal):
            continue
        if is_cart_nav_step(step) and not goal_allows_cart_nav(intent.goal):
            continue
        if is_add_to_cart_step(step) and not goal_allows_add_to_cart(intent.goal):
            continue
        filtered.append(step)
    return filtered
