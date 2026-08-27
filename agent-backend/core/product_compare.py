"""Deterministic product candidate comparison against shopping constraints."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from core.protocol import PageContext, PageProductSummary
from core.search_query import expand_search_token
from core.shopping_intent import ShoppingIntent

logger = logging.getLogger(__name__)

_PRICE_RE = re.compile(
    r"(?:₹|rs\.?|inr|\$)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:₹|rs\.?|inr)",
    re.I,
)
_RATING_RE = re.compile(r"(\d(?:\.\d)?)\s*(?:out of|/)?\s*5?|(\d(?:\.\d)?)\s*stars?", re.I)


@dataclass(frozen=True)
class NormalizedProduct:
    title: str
    price: float | None
    rating: float | None
    available: bool | None
    element_index: int | None
    add_to_cart_element_index: int | None
    raw: PageProductSummary

    def score_key(self, intent: ShoppingIntent) -> tuple:
        """Lower is better for sorting under shopping constraints."""
        rating_ok = 0
        if intent.min_rating is not None:
            if self.rating is None:
                rating_ok = 1  # unknown worse than known-pass
            elif self.rating < intent.min_rating:
                rating_ok = 2

        over_budget = 0
        if intent.budget_max is not None and self.price is not None:
            over_budget = 1 if self.price > intent.budget_max else 0
        elif intent.budget_max is not None and self.price is None:
            over_budget = 1

        unavailable = 0 if self.available is not False else 1
        price_sort = self.price if self.price is not None else 1e18
        # Prefer higher rating when not optimizing cheapest-only
        rating_sort = -(self.rating or 0.0)
        if intent.prefer_cheapest:
            return (unavailable, over_budget, rating_ok, price_sort, rating_sort)
        return (unavailable, over_budget, rating_ok, rating_sort, price_sort)


def parse_price(text: str) -> float | None:
    if not text:
        return None
    match = _PRICE_RE.search(text.replace(",", ""))
    if not match:
        # bare number fallback
        bare = re.search(r"\b(\d+(?:\.\d+)?)\b", text.replace(",", ""))
        if not bare:
            return None
        try:
            return float(bare.group(1))
        except ValueError:
            return None
    raw = match.group(1) or match.group(2)
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def parse_rating(text: str) -> float | None:
    if not text:
        return None
    match = _RATING_RE.search(text)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    try:
        value = float(raw)
    except ValueError:
        return None
    if value < 0 or value > 5:
        return None
    return value


def parse_availability(text: str) -> bool | None:
    lowered = (text or "").lower()
    if not lowered:
        return None
    if any(token in lowered for token in ("out of stock", "unavailable", "sold out")):
        return False
    if any(token in lowered for token in ("in stock", "available", "only")):
        return True
    return None


def normalize_product(product: PageProductSummary) -> NormalizedProduct:
    return NormalizedProduct(
        title=product.title.strip(),
        price=parse_price(product.price_text),
        rating=parse_rating(product.rating_text),
        available=parse_availability(product.availability_text),
        element_index=product.element_index,
        add_to_cart_element_index=product.add_to_cart_element_index,
        raw=product,
    )


def matches_product_intent(title: str, intent: ShoppingIntent) -> bool:
    title_l = title.lower().strip()
    if title_l in {"add to cart", "buy now", "see options", "unavailable"}:
        return False
    tokens = [t for t in intent.search_query.lower().split() if len(t) > 1]
    if not tokens:
        return True
    for token in tokens:
        forms = expand_search_token(token)
        if any(form in title_l for form in forms):
            return True
    return False


def select_best_product(
    page: PageContext | None,
    intent: ShoppingIntent,
    *,
    exclude_element_indices: set[int] | None = None,
) -> tuple[NormalizedProduct | None, list[NormalizedProduct], str]:
    """Pick the best visible product. Returns (winner, candidates, reason)."""
    if page is None or not page.products:
        return None, [], "No visible product cards extracted from page."

    candidates = [normalize_product(item) for item in page.products]
    relevant = [item for item in candidates if matches_product_intent(item.title, intent)]
    pool = relevant if relevant else candidates

    eligible: list[NormalizedProduct] = []
    any_ratings = any(item.rating is not None for item in pool)
    enforce_rating = intent.min_rating is not None and any_ratings

    for item in pool:
        if item.available is False:
            continue
        if (
            enforce_rating
            and item.rating is not None
            and intent.min_rating is not None
            and item.rating < intent.min_rating
        ):
            continue
        if intent.budget_max is not None and item.price is not None and item.price > intent.budget_max:
            continue
        eligible.append(item)

    if not eligible:
        reason = (
            "No product satisfied constraints "
            f"(min_rating={intent.min_rating if enforce_rating else 'n/a (not visible)'}, "
            f"budget_max={intent.budget_max}). "
            "Need handoff or broaden search — do not guess."
        )
        logger.info("product_compare no_eligible candidates=%s intent=%s", len(pool), intent.search_query)
        return None, pool, reason

    winner = None
    for item in sorted(eligible, key=lambda entry: entry.score_key(intent)):
        index = item.add_to_cart_element_index or item.element_index
        if exclude_element_indices and index in exclude_element_indices:
            continue
        winner = item
        break

    if winner is None:
        reason = (
            "No unused product satisfied constraints "
            f"(min_rating={intent.min_rating if enforce_rating else 'n/a (not visible)'}, "
            f"budget_max={intent.budget_max})."
        )
        logger.info("product_compare no_unused_eligible candidates=%s intent=%s", len(pool), intent.search_query)
        return None, pool, reason

    rating_note = (
        f"min_rating={intent.min_rating}"
        if enforce_rating
        else "ratings not visible — ignored min_rating"
    )
    reason = (
        f"Selected '{winner.title}' price={winner.price} rating={winner.rating} "
        f"from {len(eligible)} eligible / {len(pool)} candidates ({rating_note})."
    )
    logger.info("product_compare %s", reason)
    return winner, pool, reason
