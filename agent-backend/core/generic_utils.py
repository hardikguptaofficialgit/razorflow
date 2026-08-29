"""Generic browser automation utilities - domain-independent."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


def url_origin(url: str) -> str:
    """Extract origin (scheme://netloc) from URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def extract_url_query(url: str, query_keys: tuple[str, ...] = ("q", "k", "query", "search")) -> str:
    """Extract search query from URL parameters."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return ""
    query = parse_qs(parsed.query)
    for key in query_keys:
        values = query.get(key)
        if values and values[0].strip():
            return values[0].strip()
    return ""


def looks_like_gibberish(text: str) -> bool:
    """Detect obviously invalid input (ASR noise, random characters)."""
    _GIBBERISH_RE = re.compile(r"^[^a-zA-Z0-9]*$")
    _GARBAGE_TOKENS = {"ok", "okay", "go", "um", "uh", "hmm", "ya", "yeah", "nah"}

    cleaned = re.sub(r"\s+", "", text.strip().lower())
    if len(cleaned) < 2:
        return True
    if _GIBBERISH_RE.match(cleaned):
        return True
    if len(set(cleaned)) == 1 and len(cleaned) >= 3:
        return True
    if cleaned in _GARBAGE_TOKENS:
        return True
    return False


def normalize_text(text: str) -> str:
    """Normalize text for comparison (lowercase, strip, collapse whitespace)."""
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_money_value(text: str) -> float | None:
    """Parse numeric value from currency text (removes commas, symbols)."""
    if not text:
        return None
    # Remove currency symbols and commas
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def detect_auth_page(url: str, title: str, elements: list) -> tuple[bool, str]:
    """
    Detect pages requiring user authentication/intervention.
    Returns (is_auth_page, reason).
    """
    url_lower = (url or "").lower()
    title_lower = (title or "").lower()
    blob = f"{url_lower} {title_lower}"

    # URL patterns
    if re.search(r"sign[\s-]?in|log[\s-]?in|/login|/signin|auth", url_lower):
        return True, "login"

    # Title patterns
    if re.search(r"sign[\s-]?in|log[\s-]?in", title_lower):
        return True, "login"

    # OTP/CAPTCHA in title
    if re.search(r"otp|captcha|verify.*(code|identity)", title_lower):
        return True, "verification"

    # Custom data attributes (site-specific)
    for element in elements:
        tag = getattr(element, "tag", "")
        if isinstance(tag, str) and tag in ("data-auth-required", "data-rf-auth-required"):
            return True, "auth_required"

    return False, ""


def normalize_element_label(element) -> str:
    """Extract normalized label from element (text + placeholder + aria-label)."""
    parts = [
        getattr(element, "text", "") or "",
        getattr(element, "placeholder", "") or "",
        getattr(element, "aria_label", "") or "",
    ]
    return normalize_text(" ".join(parts))


def get_element_index(element: object, position: int) -> int:
    """Get element index, using position as fallback if index <= 0."""
    index = getattr(element, "index", 0)
    return index if index > 0 else position


def strip_common_stopwords(text: str, custom_stopwords: set[str] | None = None) -> list[str]:
    """
    Remove common stopwords from text.
    Custom stopwords can be provided for domain-specific filtering.
    """
    _COMMON_STOPWORDS = {
        "a", "an", "the", "and", "or", "to", "of", "for", "in", "on", "at",
        "with", "from", "by", "my", "me", "i", "im", "i'm", "you", "u", "ur",
        "your", "please", "pls", "hey", "hi", "hello", "can", "could", "would",
        "will", "should", "help", "want", "need", "like", "some", "any", "ok",
        "okay", "go", "yes", "no", "continue", "resume", "this", "that", "these",
        "those", "there", "here", "also", "just", "really", "very", "too", "then",
        "than", "into", "about", "across",
    }

    stopwords = _COMMON_STOPWORDS | (custom_stopwords or set())
    tokens = text.split()
    return [token for token in tokens if token.lower() not in stopwords]


def urls_equivalent(url1: str, url2: str) -> bool:
    """Check if two URLs are equivalent (ignoring query params, fragments, trailing slashes)."""
    try:
        parsed1 = urlparse(url1)
        parsed2 = urlparse(url2)
    except ValueError:
        return False

    return (
        parsed1.scheme == parsed2.scheme
        and parsed1.netloc == parsed2.netloc
        and parsed1.path.rstrip("/") == parsed2.path.rstrip("/")
    )


def detect_url_pattern(url: str, patterns: tuple[str, ...]) -> bool:
    """Check if URL matches any of the given path patterns."""
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return False
    return any(pattern.lower() in path for pattern in patterns)


def extract_number(text: str) -> int | None:
    """Extract first integer from text."""
    match = re.search(r"\b(\d+)\b", text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return None


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max_length, adding suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
