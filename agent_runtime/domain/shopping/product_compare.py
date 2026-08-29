"""Deterministic product ranking for autonomous compare-and-buy flows."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent_runtime.domain.shopping.helpers import budget_inr, prefer_best
from agent_runtime.domain.shopping.search_state import entity_search_tokens, search_entity
from agent_runtime.observation.browser_state import BrowserPage, ObservedProduct
from agent_runtime.state.run_state import RunState


_PRICE_RE = re.compile(
    r"(?:₹|rs\.?|inr|\$)\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*(?:₹|rs\.?|inr)",
    re.I,
)
_RATING_RE = re.compile(r"(\d(?:\.\d)?)\s*(?:out of|/)?\s*5?|(\d(?:\.\d)?)\s*stars?", re.I)


@dataclass(frozen=True)
class CompareCriteria:
    query: str
    budget_max: float | None = None
    prefer_cheapest: bool = False
    prefer_best_rating: bool = True


@dataclass(frozen=True)
class RankedProduct:
    title: str
    price: float | None
    rating: float | None
    add_element_id: str | None
    product_id: str


def criteria_from_state(state: RunState) -> CompareCriteria:
    spec = state.task_spec
    query = search_entity(state) or (spec.entities[0] if spec and spec.entities else "")
    lowered = state.task.lower()
    prefer_cheap = (
        "cheapest" in lowered
        or "best price" in lowered
        or "lowest price" in lowered
        or "at the best price" in lowered
        or bool(spec and spec.metadata.get("prefer_cheapest"))
    )
    return CompareCriteria(
        query=query,
        budget_max=budget_inr(spec),
        prefer_cheapest=prefer_cheap,
        prefer_best_rating=prefer_best(spec) and not prefer_cheap,
    )


def parse_price(text: str) -> float | None:
    if not text:
        return None
    match = _PRICE_RE.search(text.replace(",", ""))
    if not match:
        bare = re.search(r"\b(\d+(?:\.\d+)?)\b", text.replace(",", ""))
        if not bare:
            return None
        try:
            return float(bare.group(1))
        except ValueError:
            return None
    raw = match.group(1) or match.group(2)
    try:
        return float(str(raw).replace(",", ""))
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
    return value if 0 <= value <= 5 else None


def _matches_query(title: str, query: str) -> bool:
    title_l = title.lower()
    if title_l in {"add to cart", "buy now", "see options", "unavailable"}:
        return False
    tokens = entity_search_tokens(query)
    if not tokens:
        return True
    title_tokens = set(re.findall(r"[a-z0-9]+", title_l))
    overlap = sum(
        1
        for token in tokens
        if any(token in word or word in token for word in title_tokens)
    )
    return overlap >= max(1, (len(tokens) + 1) // 2)


def _score_key(
    price: float | None,
    rating: float | None,
    criteria: CompareCriteria,
) -> tuple[float, float, float]:
    price_sort = price if price is not None else 1e18
    rating_sort = -(rating or 0.0)
    if criteria.prefer_cheapest:
        return (price_sort, rating_sort, 0.0)
    if criteria.prefer_best_rating:
        return (rating_sort, price_sort, 0.0)
    return (price_sort, rating_sort, 0.0)


def eligible_products(
    page: BrowserPage | None,
    criteria: CompareCriteria,
) -> list[RankedProduct]:
    if page is None or not page.products:
        return []
    ranked = [
        RankedProduct(
            title=product.title,
            price=parse_price(product.price_text),
            rating=parse_rating(product.rating_text),
            add_element_id=product.add_element_id,
            product_id=product.product_id,
        )
        for product in page.products
        if product.title
    ]
    relevant = [p for p in ranked if _matches_query(p.title, criteria.query)]
    pool = relevant if relevant else ranked
    return [
        item
        for item in pool
        if criteria.budget_max is None
        or item.price is None
        or item.price <= criteria.budget_max
    ]


def rank_products(
    page: BrowserPage | None,
    criteria: CompareCriteria,
) -> tuple[RankedProduct | None, list[RankedProduct], str]:
    if page is None or not page.products:
        return None, [], "No product listings visible to compare."

    ranked: list[RankedProduct] = []
    for product in page.products:
        if not product.title:
            continue
        ranked.append(
            RankedProduct(
                title=product.title,
                price=parse_price(product.price_text),
                rating=parse_rating(product.rating_text),
                add_element_id=product.add_element_id,
                product_id=product.product_id,
            )
        )

    relevant = [p for p in ranked if _matches_query(p.title, criteria.query)]
    pool = relevant if relevant else ranked
    eligible: list[RankedProduct] = []
    for item in pool:
        if criteria.budget_max is not None and item.price is not None:
            if item.price > criteria.budget_max:
                continue
        eligible.append(item)

    if not eligible:
        return (
            None,
            pool,
            f"No products matched budget/query ({criteria.query}, max={criteria.budget_max}).",
        )

    winner = min(eligible, key=lambda p: _score_key(p.price, p.rating, criteria))
    mode = "lowest price" if criteria.prefer_cheapest else "best value"
    reason = (
        f"{mode}: {winner.title} "
        f"(₹{winner.price if winner.price is not None else '?'}, "
        f"rating {winner.rating if winner.rating is not None else 'n/a'}) "
        f"from {len(eligible)} option(s)"
    )
    return winner, pool, reason


def apply_comparison_to_state(state: RunState, page: BrowserPage | None) -> bool:
    """Rank visible products and store the autonomous pick. Returns True if set."""
    spec = state.task_spec
    if page is None or not page.products or spec is None:
        return False
    if not prefer_best(spec) and not spec.metadata.get("prefer_cheapest"):
        return False
    if "verified_comparison" in state.milestones:
        return False
    if state.current_phase not in {"search_results", "cart_updated"}:
        return False

    criteria = criteria_from_state(state)
    winner, candidates, reason = rank_products(page, criteria)
    if winner is None:
        state.memory.note_fact(reason)
        return False

    state.milestones.add("verified_comparison")
    state.metrics["selected_product_title"] = winner.title
    if winner.add_element_id:
        state.metrics["selected_product_add_id"] = winner.add_element_id
    state.memory.current_target = winner.title
    if state.memory.remaining_items and len(state.memory.remaining_items) == 1:
        state.memory.remaining_items = [winner.title]
    state.memory.note_fact(reason)
    if len(candidates) > 1:
        summary = ", ".join(
            f"{c.title} (₹{c.price or '?'})" for c in candidates[:5]
        )
        state.memory.note_fact(f"Compared: {summary}")
    return True
