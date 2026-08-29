"""Generic entity extraction — preserve the user's semantic product phrases."""

from __future__ import annotations

import re

# Conversational wrappers stripped from the start of a phrase.
_LEADING_WRAPPER = re.compile(
    r"^\s*(?:(?:please|pls|see)\s+)?(?:can\s+you\s+)?(?:could\s+you\s+)?"
    r"(?:find|search|look\s+for|show\s+me|get\s+me|grab|pick|buy|add|i\s+need|i\s+want)\s+"
    r"(?:for\s+)?"
    r"(?:me\s+)?",
    re.I,
)

# Trailing goal clauses (cart, checkout, selection) removed before entity capture.
_TRAILING_GOAL = re.compile(
    r"\s+(?:and\s+)?(?:"
    r"(?:add|put|place).*(?:cart|bag|basket|checkout)|"
    r"(?:proceed\s+to\s+)?checkout|"
    r"show\s+me\s+(?:the\s+)?best(?:\s+one)?|"
    r"open\s+(?:the\s+)?(?:product|details?)"
    r").*$",
    re.I,
)
_TRAILING_SITE = re.compile(r"\s+on\s+(?:this|the)\s+(?:site|page|store)\b.*$", re.I)
_TRAILING_POLITE = re.compile(r"\s+(?:please|pls|thanks?)\s*$", re.I)
_TRAILING_GOAL_TAIL = re.compile(
    r"\s*,\s*(?:inspect|compare|choose|pick|then).*$",
    re.I,
)

_BUDGET_CLAUSE = re.compile(
    r"\b(?:under|below|less\s+than|max(?:imum)?|upto|up\s+to)\s*"
    r"(?:₹|rs\.?|inr)?\s*[\d,]+(?:\.\d+)?\s*(?:k|K)?",
    re.I,
)

# Leading quality/filler words removed; internal modifiers (wireless, noise cancelling) kept.
_QUALITY_PREFIX = re.compile(
    r"^(?:some|any|a|an|the|good|best|nice|great|cheap|cheapest|affordable|decent)\s+",
    re.I,
)

_LIST_SPLIT = re.compile(r"\s*,\s*|\s+and\s+", re.I)

_LIST_FILLER = frozenset(
    {
        "all",
        "everything",
        "anything",
        "etc",
        "stuff",
        "checkout",
        "cart",
        "my",
        "me",
        "one",
    }
)

_ADD_LIST = re.compile(
    r"\badd\b.*\b(?:cart|bag|basket)\b|"
    r"^\s*(?:add|put|place|get|grab|buy(?:\s+me)?)\b",
    re.I,
)


def _strip_wrappers(text: str) -> str:
    cleaned = _BUDGET_CLAUSE.sub(" ", text)
    cleaned = _TRAILING_GOAL.sub("", cleaned)
    cleaned = _TRAILING_GOAL_TAIL.sub("", cleaned)
    cleaned = _TRAILING_SITE.sub("", cleaned)
    cleaned = _TRAILING_POLITE.sub("", cleaned)
    cleaned = re.sub(
        r"\s+(?:into\s+)?(?:to\s+)?(?:in\s+)?(?:my\s+)?(?:cart|bag|basket)\b.*$",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = _LEADING_WRAPPER.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    while True:
        next_val = _QUALITY_PREFIX.sub("", cleaned).strip()
        if next_val == cleaned:
            break
        cleaned = next_val
    return cleaned


def extract_entity_phrase(task: str) -> str:
    """Extract a single semantic product phrase from a task."""
    phrase = _strip_wrappers(task.strip())
    if not phrase:
        return ""
    # Drop stray currency / punctuation noise without token canonicalization.
    phrase = re.sub(r"[^\w\s\-+&'']", " ", phrase, flags=re.UNICODE)
    phrase = re.sub(r"\s+", " ", phrase).strip()
    return phrase


def extract_entity_phrases(task: str) -> tuple[str, ...]:
    """Extract one or more product phrases (comma/and lists for add flows)."""
    raw = task.strip()
    if not raw:
        return ()

    if re.search(r"\bcompare\b", raw, re.I) and re.search(
        r"\badd\b.+\b(?:cart|bag|basket)\b", raw, re.I
    ):
        before_compare = re.split(r"\bcompare\b", raw, maxsplit=1, flags=re.I)[0]
        phrase = extract_entity_phrase(before_compare)
        if phrase:
            return (phrase,)

    if _ADD_LIST.search(raw) and re.search(r",|\band\b", raw, re.I):
        working = raw
        working = re.sub(
            r"^\s*(?:add(?:\s+me)?|put|place|get|grab|buy(?:\s+me)?)\s+",
            "",
            working,
            flags=re.I,
        )
        working = re.sub(
            r"\b(?:into\s+)?(?:to\s+)?(?:in\s+)?(?:my\s+)?(?:cart|bag|basket)\b.*$",
            "",
            working,
            flags=re.I,
        )
        working = re.sub(
            r",\s*(?:inspect|compare|choose|pick).*$",
            "",
            working,
            flags=re.I,
        )
        parts = [p.strip() for p in _LIST_SPLIT.split(working) if p.strip()]
        phrases: list[str] = []
        for part in parts:
            if part.lower() in _LIST_FILLER:
                continue
            phrase = extract_entity_phrase(part)
            if phrase and phrase.lower() not in _LIST_FILLER and phrase not in phrases:
                phrases.append(phrase)
        if len(phrases) >= 2:
            return tuple(phrases)

    if re.search(r"\bfind\b", raw, re.I) and re.search(r"\band\s+add\b", raw, re.I):
        find_clause = re.sub(r"\band\s+add\b.*", "", raw, flags=re.I)
        phrase = extract_entity_phrase(find_clause)
        if phrase:
            return (phrase,)

    if re.search(r"\b(?:find|search|look\s+for)\b", raw, re.I) and re.search(
        r"\band\b", raw, re.I
    ):
        parts = [p.strip() for p in _LIST_SPLIT.split(raw) if p.strip()]
        if len(parts) >= 2:
            phrases = tuple(
                phrase
                for part in parts
                if (phrase := extract_entity_phrase(part))
                and phrase.lower() not in _LIST_FILLER
            )
            if len(phrases) >= 2:
                return phrases

    phrase = extract_entity_phrase(raw)
    return (phrase,) if phrase else ()
