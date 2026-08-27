"""Extract short store search queries from conversational user goals."""

from __future__ import annotations

import re

from core.protocol import ActionStep, TypeInElementStep

_SEARCH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "to",
        "of",
        "for",
        "in",
        "on",
        "at",
        "with",
        "from",
        "by",
        "my",
        "me",
        "i",
        "im",
        "i'm",
        "you",
        "u",
        "ur",
        "your",
        "please",
        "pls",
        "hey",
        "hi",
        "hello",
        "can",
        "could",
        "would",
        "will",
        "should",
        "help",
        "find",
        "search",
        "look",
        "looking",
        "show",
        "get",
        "buy",
        "purchase",
        "order",
        "want",
        "need",
        "like",
        "some",
        "any",
        "good",
        "best",
        "nice",
        "great",
        "cheap",
        "cheapest",
        "lowest",
        "affordable",
        "budget",
        "online",
        "tonight",
        "today",
        "now",
        "asap",
        "add",
        "cart",
        "checkout",
        "rating",
        "ratings",
        "rated",
        "stars",
        "reviews",
        "highly",
        "under",
        "above",
        "below",
        "rs",
        "inr",
        "rupees",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "also",
        "just",
        "really",
        "very",
        "too",
        "then",
        "than",
        "into",
        "about",
        "across",
        "packs",
        "pack",
        "pieces",
        "piece",
        "items",
        "item",
        "products",
        "product",
        "something",
        "stuff",
        "ok",
        "okay",
        "go",
        "yes",
        "no",
        "continue",
        "resume",
        "discounted",
        "discount",
        "sale",
        "deal",
        "price",
        "prices",
    }
)

# Tokens that look like ASR / filler noise and must never become search queries alone.
_GARBAGE_TOKENS = frozenset({"ok", "okay", "go", "um", "uh", "hmm", "ya", "yeah", "nah"})

_MODIFIER_WORDS = frozenset(
    {
        "wireless",
        "bluetooth",
        "portable",
        "rechargeable",
        "smart",
        "digital",
        "electric",
        "online",
        "new",
        "latest",
        "premium",
        "affordable",
    }
)

_CANONICAL_FORMS = {
    "earbud": "earbuds",
    "earbuds": "earbuds",
    "headphone": "headphones",
    "headphones": "headphones",
    "chocolate": "chocolates",
    "chocolates": "chocolates",
    "dress": "dresses",
    "bag": "bags",
    "watch": "watches",
    "watches": "watches",
    "smartwatch": "watches",
}

_TERM_SYNONYMS = {
    "earbud": ("earbud", "earbuds", "buds", "tws"),
    "earbuds": ("earbud", "earbuds", "buds", "tws"),
    "buds": ("buds", "earbuds", "earbud"),
    "headphone": ("headphone", "headphones", "headset", "rockerz"),
    "headphones": ("headphone", "headphones", "headset", "rockerz"),
    "watch": ("watch", "watches", "smartwatch"),
    "watches": ("watch", "watches", "smartwatch"),
    "smartwatch": ("watch", "watches", "smartwatch"),
    "beauty": ("beauty", "moisturizing", "dove"),
    "bar": ("bar", "bars", "beauty"),
    "bars": ("bar", "bars", "beauty"),
    "chocolates": ("chocolate", "chocolates", "cadbury", "ferrero"),
    "chocolate": ("chocolate", "chocolates", "cadbury", "ferrero"),
}

_PRODUCT_TERMS = (
    "shampoo",
    "chocolates",
    "chocolate",
    "chips",
    "cookies",
    "dress",
    "dresses",
    "shoes",
    "sneakers",
    "headphones",
    "earbuds",
    "earbud",
    "wireless",
    "watch",
    "watches",
    "smartwatch",
    "beauty",
    "bar",
    "bars",
    "tshirt",
    "t-shirt",
    "shirt",
    "trimmer",
    "facewash",
    "face-wash",
    "butter",
    "bulb",
    "cooker",
    "dinner",
    "party",
    "fashion",
    "electronics",
    "snacks",
    "care",
    "bag",
    "bags",
    "handbag",
    "handbags",
    "purse",
    "luggage",
    "duffel",
    "duffle",
    "backpack",
    "tote",
    "wallet",
    "gucci",
    "nike",
    "adidas",
    "puma",
)


def _canonicalize_token(token: str) -> str:
    return _CANONICAL_FORMS.get(token, token)


def _is_product_term(token: str) -> bool:
    stem = token.rstrip("s")
    return token in _PRODUCT_TERMS or stem in _PRODUCT_TERMS or f"{token}s" in _PRODUCT_TERMS


def _strip_budget_fragments(text: str) -> str:
    text = re.sub(
        r"\b(?:under|below|less than|upto|up to|max(?:imum)?)\s*"
        r"(?:₹|rs\.?|inr|\$|usd)?\s*[\d,]+(?:\.\d+)?\s*k\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b(?:under|below|less than|upto|up to|max(?:imum)?)\s*"
        r"(?:₹|rs\.?|inr|\$|usd)?\s*[\d,]+(?:\.\d+)?\b",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b[\d,]+(?:\.\d+)?\s*k\b", " ", text, flags=re.I)
    text = re.sub(
        r"\b(?:₹|rs\.?|inr|\$|usd)\s*[\d,]+(?:\.\d+)?\b",
        " ",
        text,
        flags=re.I,
    )
    return text


def expand_search_token(token: str) -> tuple[str, ...]:
    forms = {token, _canonicalize_token(token)}
    synonyms = _TERM_SYNONYMS.get(token) or _TERM_SYNONYMS.get(token.rstrip("s"))
    if synonyms:
        forms.update(synonyms)
    return tuple(forms)


def search_queries_equivalent(left: str, right: str) -> bool:
    """True when two search strings target the same catalog intent."""
    a = extract_search_query(left).lower().strip()
    b = extract_search_query(right).lower().strip()
    if not a or not b:
        return False
    if a == b:
        return True

    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if tokens_a == tokens_b:
        return True

    expanded_a = {form for token in tokens_a for form in expand_search_token(token)}
    expanded_b = {form for token in tokens_b for form in expand_search_token(token)}

    primary_a = [token for token in tokens_a if token not in _MODIFIER_WORDS] or list(tokens_a)
    primary_b = [token for token in tokens_b if token not in _MODIFIER_WORDS] or list(tokens_b)

    a_hits_b = any(
        form in expanded_b for token in primary_a for form in expand_search_token(token)
    )
    b_hits_a = any(
        form in expanded_a for token in primary_b for form in expand_search_token(token)
    )
    return a_hits_b and b_hits_a


_LIST_FILLER_PARTS = frozenset(
    {
        "all",
        "everything",
        "anything",
        "etc",
        "stuff",
        "pjust",
        "just",
        "checkout",
        "check out",
        "pay",
        "payment",
        "order",
    }
)

_QUERY_ALIASES = {
    "bars": "beauty bar",
    "bar": "beauty bar",
    "buds": "earbuds",
    "bud": "earbuds",
    "chcolates": "chocolates",
    "choclate": "chocolates",
    "choclates": "chocolates",
    "chocolate": "chocolates",
    "watch": "smartwatch",
    "watches": "smartwatch",
}


def _normalize_list_part(part: str) -> str:
    cleaned = part.strip().lower()
    if cleaned in _LIST_FILLER_PARTS:
        return ""
    if cleaned in _QUERY_ALIASES:
        return _QUERY_ALIASES[cleaned]
    return extract_search_query(part)


def _strip_trailing_checkout_clause(text: str) -> str:
    return re.sub(
        r"\s+and\s+(?:(?:proceed\s+to\s+)?checkout|check\s*out|pay(?:ment)?|place\s+(?:the\s+)?order)\b.*$",
        "",
        text,
        flags=re.I,
    )


def _strip_add_to_cart_wrapper(task: str) -> str:
    """Remove leading add-verb and trailing cart phrases from a task."""
    text = re.sub(r"^task:\s*", "", task.strip(), flags=re.I)
    text = re.sub(r"\band\s+all\b", "", text, flags=re.I)
    text = _strip_trailing_checkout_clause(text)
    text = re.sub(
        r"\b(?:in\s+)?(?:to\s+)?(?:my\s+)?(?:cart|bag|basket)\b.*$",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"^\s*(?:add(?:\s+me)?|put|place|get|grab|buy(?:\s+me)?)\s+",
        "",
        text,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", text).strip()


def extract_product_queries(task: str) -> list[str]:
    """Split comma/and-separated shopping lists into per-item search queries."""
    raw = task.strip()
    is_add_list = bool(
        re.search(r"\badd\b.*\b(?:cart|bag|basket)\b", raw, re.I)
        or re.search(
            r"^\s*(?:task:\s*)?(?:add|put|place|get|grab|buy(?:\s+me)?)\b",
            raw,
            re.I,
        )
    )
    if not is_add_list:
        return [extract_search_query(task)]

    working = _strip_add_to_cart_wrapper(task)
    working = _strip_trailing_checkout_clause(working)
    if not working:
        return [extract_search_query(task)]

    if not re.search(r",|\band\b", working, re.I):
        return [extract_search_query(task)]

    parts = [part.strip() for part in re.split(r"\s*,\s*|\s+and\s+", working) if part.strip()]
    if len(parts) < 2:
        return [extract_search_query(task)]

    queries: list[str] = []
    for part in parts:
        if part.strip().lower() in _LIST_FILLER_PARTS:
            continue
        query = _normalize_list_part(part)
        if not query:
            continue
        if query not in queries:
            queries.append(query)

    return queries if len(queries) >= 2 else [extract_search_query(task)]


def alternate_search_query(query: str) -> str | None:
    """Return a fallback catalog query when the primary search returns no products."""
    lowered = query.strip().lower()
    alternates = {
        "watches": "smartwatch",
        "watch": "smartwatch",
        "bars": "beauty bar",
        "bar": "beauty bar",
        "buds": "earbuds",
        "bud": "earbuds",
        "chcolates": "chocolates",
        "choclates": "chocolates",
    }
    alt = alternates.get(lowered)
    if alt and alt != lowered:
        return alt
    return None


def extract_search_query(task: str) -> str:
    """Turn chatty user goals into a short store search query."""
    text = task.strip().lower()
    text = re.sub(r"[^\w\s\-+&]", " ", text)
    text = _strip_budget_fragments(text)
    text = re.sub(
        r"\b(add\s+to\s+(cart|bag|basket)|buy\s+now|check\s*out)\b.*$",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+", " ", text).strip()

    tokens = [
        token
        for token in text.split(" ")
        if token
        and token not in _SEARCH_STOPWORDS
        and token not in _GARBAGE_TOKENS
        and len(token) > 1
    ]
    if not tokens:
        tokens = [
            token
            for token in text.split(" ")
            if len(token) > 2 and token not in _GARBAGE_TOKENS
        ][:3]

    product_tokens = [token for token in tokens if _is_product_term(token)]
    chosen = product_tokens if product_tokens else tokens
    chosen = [token for token in chosen if token not in _MODIFIER_WORDS] or chosen

    brands = [t for t in chosen if t in {"gucci", "nike", "adidas", "puma", "boat", "noise"}]
    nouns = [t for t in chosen if t not in brands]
    ordered = [_canonicalize_token(token) for token in brands + nouns]
    deduped: list[str] = []
    for token in ordered:
        if token not in deduped:
            deduped.append(token)

    query = " ".join(deduped[:4]).strip()
    if len(query) > 40:
        query = " ".join(deduped[:2]).strip()
    if not query or all(part in _GARBAGE_TOKENS for part in query.split()):
        return " ".join(tokens[:3]) or task.strip()[:40]
    return query


def looks_like_chatty_search(text: str) -> bool:
    """True when text is too conversational to paste into a search box."""
    cleaned = text.strip()
    if len(cleaned.split()) >= 6:
        return True
    return bool(re.search(r"\b(hey|help me|can u|can you|please)\b", cleaned, re.I))


def sanitize_search_type_step(step: ActionStep, task: str) -> ActionStep:
    """Force search typing steps to use a short keyword query."""
    if not isinstance(step, TypeInElementStep):
        return step
    if step.role not in {"search", "input"}:
        return step

    good_query = extract_search_query(task)
    current = step.text.strip()
    if not current:
        return step.model_copy(update={"text": good_query})

    if looks_like_chatty_search(current) or current.lower() != good_query.lower():
        return step.model_copy(update={"text": good_query})

    return step


def sanitize_plan_steps(steps: list[ActionStep], task: str) -> list[ActionStep]:
    return [sanitize_search_type_step(step, task) for step in steps]
