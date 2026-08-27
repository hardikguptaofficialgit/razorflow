"""Convert Browser Use state into RazorFlow PageContext for timeline/handoffs."""

from __future__ import annotations

import re

from browser_use.browser.views import BrowserStateSummary
from browser_use.dom.views import EnhancedDOMTreeNode

from core.protocol import PageContext, PageElementSummary, PageProductSummary, TargetRole

_PRICE_IN_TEXT = re.compile(
    r"(?:₹|rs\.?\s*|inr\s*|\$)\s*[\d,]+(?:\.\d+)?|[\d,]+(?:\.\d+)?\s*(?:₹|rs\.?)",
    re.I,
)
_RATING_IN_TEXT = re.compile(r"\b([1-5](?:\.\d)?)\s*(?:out of 5|/\s*5|stars?)?\b", re.I)
_AVAIL_IN_TEXT = re.compile(
    r"out of stock|unavailable|sold out|in stock|only \d+ left|available",
    re.I,
)
_CTA_ONLY = re.compile(
    r"^(add to cart|buy now|see options|unavailable|max in cart)$",
    re.I,
)
_CTA_HEAVY = re.compile(r"\b(add to cart|buy now|max in cart)\b", re.I)


def _infer_role(tag: str, attributes: dict[str, str], text: str) -> TargetRole:
    input_type = attributes.get("type", "").lower()
    role = attributes.get("role", "").lower()
    combined = f"{text} {attributes.get('placeholder', '')} {attributes.get('aria-label', '')}".lower()

    if tag == "a" and attributes.get("href"):
        return "link"
    if tag == "button" or role == "button" or input_type in {"button", "submit"}:
        return "button"
    if input_type == "search" or role == "searchbox" or "search" in combined:
        return "search"
    return "input"


def _node_text(node: EnhancedDOMTreeNode, max_depth: int = 2) -> str:
    if hasattr(node, "get_all_children_text"):
        return (node.get_all_children_text(max_depth=max_depth) or "")[:240]
    return (node.node_value or "")[:240]


def _ancestor_blob(node: EnhancedDOMTreeNode, depth: int = 4) -> str:
    parts: list[str] = []
    current: EnhancedDOMTreeNode | None = node
    for _ in range(depth):
        if current is None:
            break
        parts.append(_node_text(current, max_depth=3))
        aria = ""
        if current.attributes:
            aria = str(current.attributes.get("aria-label", ""))
        if aria:
            parts.append(aria)
        current = current.parent_node
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:400]


def _split_product_fields(text: str) -> tuple[str, str, str, str]:
    price_match = _PRICE_IN_TEXT.search(text)
    price_text = price_match.group(0) if price_match else ""
    rating_text = ""
    rating_match = _RATING_IN_TEXT.search(text)
    if rating_match:
        try:
            value = float(rating_match.group(1))
            if 0 < value <= 5:
                rating_text = rating_match.group(0)
        except ValueError:
            rating_text = ""
    avail_match = _AVAIL_IN_TEXT.search(text)
    availability_text = avail_match.group(0) if avail_match else ""
    title = text
    for fragment in (price_text, rating_text, availability_text):
        if fragment:
            title = re.sub(re.escape(fragment), " ", title, flags=re.I)
    title = re.sub(
        r"\b(add to cart|buy now|see options|unavailable)\b",
        " ",
        title,
        flags=re.I,
    )
    title = re.sub(r"\s+", " ", title).strip()[:80]
    return title, price_text[:40], rating_text[:40], availability_text[:40]


def _is_usable_product_title(title: str) -> bool:
    cleaned = title.strip()
    if len(cleaned) < 4:
        return False
    if _CTA_ONLY.match(cleaned):
        return False
    if _CTA_HEAVY.search(cleaned) and len(cleaned) < 24:
        return False
    if cleaned.lower() in {"search", "cart", "login", "home", "sign in", "sign up"}:
        return False
    if _PRICE_IN_TEXT.fullmatch(cleaned.replace(" ", "")):
        return False
    return True


def page_context_from_browser_state(state: BrowserStateSummary) -> PageContext:
    elements: list[PageElementSummary] = []
    products: list[PageProductSummary] = []
    seen_titles: set[str] = set()

    selector_map = state.dom_state.selector_map
    for index, node in list(selector_map.items())[:120]:
        attributes = {str(k): str(v) for k, v in node.attributes.items()}
        text = _node_text(node, max_depth=2)
        role = _infer_role(node.tag_name.lower(), attributes, text)
        elements.append(
            PageElementSummary(
                index=index,
                role=role,
                tag=node.tag_name.lower(),
                text=text[:80],
                placeholder=attributes.get("placeholder", "")[:80],
                aria_label=attributes.get("aria-label", "")[:80],
            ),
        )

        blob = _ancestor_blob(node)
        has_price = bool(_PRICE_IN_TEXT.search(blob))
        if not has_price:
            continue

        is_cart_cta = "add to cart" in text.lower() or "buy now" in text.lower()
        title, price_text, rating_text, availability_text = _split_product_fields(blob)
        if not _is_usable_product_title(title):
            if is_cart_cta:
                for existing in products:
                    if existing.add_to_cart_element_index is None:
                        existing.add_to_cart_element_index = index
                        break
            continue

        key = title.lower()
        if key in seen_titles:
            for existing in products:
                if existing.title.lower() == key and is_cart_cta:
                    existing.add_to_cart_element_index = index
                    break
            continue
        seen_titles.add(key)

        products.append(
            PageProductSummary(
                title=title,
                price_text=price_text,
                rating_text=rating_text,
                availability_text=availability_text,
                element_index=index,
                add_to_cart_element_index=index if is_cart_cta else None,
            ),
        )

    return PageContext(
        title=state.title[:80],
        url=state.url,
        elements=elements[:40],
        products=products[:12],
    )
