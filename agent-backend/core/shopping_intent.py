"""Structured shopping intent parsing for accurate Browser Use decisions."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from core.search_query import extract_search_query


@dataclass(frozen=True)
class ShoppingIntent:
    """Normalized constraints extracted from a natural-language shopping task."""

    raw_task: str
    product: str
    search_query: str
    brand: str | None = None
    budget_max: float | None = None
    budget_currency: str = "INR"
    prefer_cheapest: bool = False
    prefer_discount: bool = False
    min_rating: float | None = None
    quantity: int = 1
    preferences: tuple[str, ...] = ()
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)

    def prompt_block(self) -> str:
        lines = [
            "STRUCTURED SHOPPING INTENT (authoritative — do not invent constraints):",
            f"- product: {self.product}",
            f"- search_query: {self.search_query}",
        ]
        if self.brand:
            lines.append(f"- brand: {self.brand}")
        if self.budget_max is not None:
            lines.append(f"- budget_max: {self.budget_currency} {self.budget_max:g}")
        if self.prefer_cheapest:
            lines.append("- prefer: cheapest matching product")
        if self.prefer_discount:
            lines.append("- prefer: discounted / deal pricing when visible")
        if self.min_rating is not None:
            lines.append(f"- min_rating: {self.min_rating}")
        if self.quantity != 1:
            lines.append(f"- quantity: {self.quantity}")
        if self.preferences:
            lines.append(f"- preferences: {', '.join(self.preferences)}")
        lines.append(f"- parse_confidence: {self.confidence:.2f}")
        return "\n".join(lines)


_BUDGET_PATTERNS = (
    re.compile(
        r"\b(?:under|below|less than|upto|up to|max(?:imum)?)\s*"
        r"(?:₹|rs\.?|inr|\$|usd)?\s*([\d,]+(?:\.\d+)?)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:or less|max|budget)?\b",
        re.I,
    ),
    re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\b", re.I),
)

_RATING_PATTERNS = (
    re.compile(r"\b(?:rating|rated|stars?)\s*(?:of\s*)?(?:at least\s*)?(\d(?:\.\d)?)\+?\b", re.I),
    re.compile(r"\b(\d(?:\.\d)?)\+?\s*stars?\b", re.I),
    re.compile(r"\bgood ratings?\b", re.I),
    re.compile(r"\bhigh(?:ly)?\s*rated\b", re.I),
)

_QTY_PATTERN = re.compile(
    r"\b(?:qty|quantity|buy|get|need|want)?\s*(\d+)\s*(?:x|pcs?|pieces?|items?|units?)?\b",
    re.I,
)

_BRAND_HINTS = frozenset(
    {
        "gucci",
        "nike",
        "adidas",
        "puma",
        "apple",
        "samsung",
        "sony",
        "boat",
        "noise",
        "zara",
        "levi",
        "levis",
        "pantene",
        "sunsilk",
        "dove",
        "himalaya",
        "amul",
        "philips",
        "havells",
        "prestige",
        "cello",
        "patanjali",
        "britannia",
        "kurkure",
        "lays",
    }
)

_PREFERENCE_KEYWORDS = (
    ("discounted", "discount"),
    ("on sale", "sale"),
    ("deal", "deal"),
    ("offer", "offer"),
    ("wireless", "wireless"),
    ("bluetooth", "bluetooth"),
    ("waterproof", "waterproof"),
    ("organic", "organic"),
    ("cotton", "cotton"),
    ("leather", "leather"),
    ("hard shell", "hard shell"),
    ("soft shell", "soft shell"),
    ("carry on", "carry-on"),
    ("party", "party"),
)


def _parse_money(raw: str) -> float:
    return float(raw.replace(",", ""))


def _detect_currency(task: str) -> str:
    lowered = task.lower()
    if "$" in task or "usd" in lowered:
        return "USD"
    return "INR"


def _extract_budget(task: str) -> float | None:
    k_match = re.search(
        r"\b(?:under|below|less than|upto|up to|max(?:imum)?)\s*"
        r"(?:₹|rs\.?|inr|\$|usd)?\s*([\d,]+(?:\.\d+)?)\s*k\b",
        task,
        re.I,
    )
    if k_match:
        try:
            return float(k_match.group(1).replace(",", "")) * 1000
        except ValueError:
            pass

    bare_k = re.search(r"\bunder\s+(\d+)\s*k\b", task, re.I)
    if bare_k:
        try:
            return float(bare_k.group(1)) * 1000
        except ValueError:
            pass

    for pattern in _BUDGET_PATTERNS:
        match = pattern.search(task)
        if match and match.lastindex:
            try:
                return _parse_money(match.group(1))
            except ValueError:
                continue
    return None


def _extract_min_rating(task: str) -> float | None:
    lowered = task.lower()
    for pattern in _RATING_PATTERNS[:2]:
        match = pattern.search(task)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    if re.search(r"\b(good ratings?|high(?:ly)?\s*rated|well[- ]rated)\b", lowered):
        return 4.0
    return None


def _extract_quantity(task: str) -> int:
    match = _QTY_PATTERN.search(task)
    if not match:
        return 1
    try:
        value = int(match.group(1))
    except ValueError:
        return 1
    if value < 1 or value > 20:
        return 1
    # Avoid treating years / prices as quantity when preceded by currency words
    start = match.start()
    prefix = task[max(0, start - 8) : start].lower()
    if any(token in prefix for token in ("₹", "rs", "inr", "$", "under", "below")):
        return 1
    return value


def _extract_brand(task: str, search_query: str) -> str | None:
    tokens = set(re.findall(r"[a-z0-9]+", task.lower()))
    for brand in _BRAND_HINTS:
        if brand in tokens or brand in search_query.lower().split():
            return brand
    return None


def _extract_preferences(task: str) -> tuple[str, ...]:
    lowered = task.lower()
    found: list[str] = []
    for needle, label in _PREFERENCE_KEYWORDS:
        if needle in lowered and label not in found:
            found.append(label)
    return tuple(found)


def parse_shopping_intent(task: str) -> ShoppingIntent:
    """Parse a user shopping task into structured constraints + short search query."""
    raw = task.strip()
    search_query = extract_search_query(raw)
    product = search_query or raw[:40]
    brand = _extract_brand(raw, search_query)
    budget_max = _extract_budget(raw)
    prefer_cheapest = bool(
        re.search(r"\b(cheapest|lowest price|lowest cost|most affordable)\b", raw, re.I)
    )
    prefer_discount = bool(
        re.search(r"\b(discount|discounted|on sale|deal|offer|cheap(?:er)?)\b", raw, re.I)
    )
    min_rating = _extract_min_rating(raw)
    quantity = _extract_quantity(raw)
    preferences = _extract_preferences(raw)

    confidence = 0.35
    if search_query and len(search_query.split()) <= 4:
        confidence += 0.25
    if product and product.lower() not in {"ok", "go", "please", "help"}:
        confidence += 0.15
    if brand:
        confidence += 0.1
    if budget_max is not None or prefer_cheapest or min_rating is not None:
        confidence += 0.1
    confidence = min(confidence, 0.95)

    # Brand should appear in search query when known
    if brand and brand not in search_query.lower().split():
        search_query = f"{brand} {search_query}".strip()
        product = search_query

    return ShoppingIntent(
        raw_task=raw,
        product=product,
        search_query=search_query,
        brand=brand,
        budget_max=budget_max,
        budget_currency=_detect_currency(raw),
        prefer_cheapest=prefer_cheapest,
        prefer_discount=prefer_discount,
        min_rating=min_rating,
        quantity=quantity,
        preferences=preferences,
        confidence=confidence,
    )
