"""Shopping domain skill - optional e-commerce intelligence."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from core.protocol import PageContext, PlannerChunkOutput
from core.run_manager import RunSession
from core.search_query import extract_search_query
from core.shopping_intent import parse_shopping_intent
from core.task_intent import parse_task_intent

logger = logging.getLogger(__name__)

# Shopping-specific data - kept within the domain skill
_SHOPPING_VERBS = {
    "buy", "purchase", "order", "shop", "cart", "checkout",
    "add to cart", "price", "cheapest", "rating", "product",
    "search", "find", "compare"
}

# Shopping vocabularies for query extraction
_SHOPPING_STOPWORDS = {
    "add", "cart", "checkout", "rating", "ratings", "rated", "stars",
    "reviews", "under", "rs", "inr", "rupees", "price", "prices"
}

_PRODUCT_TERMS = (
    "shampoo", "chocolates", "chocolate", "chips", "cookies", "dress",
    "dresses", "shoes", "sneakers", "headphones", "earbuds", "earbud",
    "wireless", "watch", "watches", "smartwatch", "beauty", "bar", "bars",
    "tshirt", "t-shirt", "shirt", "trimmer", "facewash", "face-wash",
    "butter", "bulb", "cooker", "snacks", "care", "bag", "bags"
)

_BRAND_HINTS = {
    "gucci", "nike", "adidas", "puma", "apple", "samsung", "sony",
    "boat", "noise", "zara", "levi", "levis", "pantene", "sunsilk",
    "dove", "himalaya", "amul", "philips", "havells", "prestige"
}

# Shopping URL patterns (configurable, not hardcoded in core)
_SHOPPING_URL_PATTERNS = {
    "search": ["/search", "/s", "/catalog", "/products"],
    "cart": ["/cart", "/bag", "/basket", "/gp/cart"],
    "checkout": ["/checkout", "/buy", "/payment", "/spc/"],
    "product": ["/product/", "/p/", "/item/", "/dp/", "/gp/product"],
}


@dataclass
class ShoppingSkillOutput:
    """Output from shopping skill analysis."""
    is_shopping_task: bool
    intent: object | None  # ShoppingIntent if shopping
    confidence: float
    suggested_actions: list[str] | None = None
    reason: str | None = None
    detected_page_type: str | None = None  # "search", "cart", "checkout", "product"


@dataclass
class ShoppingPageAnalysis:
    """Analysis of a page for shopping-related content."""
    is_shopping_page: bool
    page_type: Literal["search", "product", "cart", "checkout", "unknown"]
    confidence: float
    detected_elements: dict[str, int]  # Element type counts
    reason: str


class ShoppingSkill:
    """
    Optional shopping domain skill.
    Provides e-commerce-specific intelligence when enabled.
    The core agent works without this skill.
    """

    def __init__(self):
        self.enabled = True
        # Configurable URL patterns (can be updated per site)
        self.url_patterns = _SHOPPING_URL_PATTERNS.copy()

    def detect_shopping_task(self, task: str) -> ShoppingSkillOutput:
        """Detect if a task is shopping-related."""
        task_lower = task.lower()

        has_shopping_keyword = any(keyword in task_lower for keyword in _SHOPPING_VERBS)

        if not has_shopping_keyword:
            return ShoppingSkillOutput(
                is_shopping_task=False,
                intent=None,
                confidence=0.0,
                reason="No shopping keywords detected"
            )

        # Parse shopping intent
        try:
            intent = parse_shopping_intent(task)
            return ShoppingSkillOutput(
                is_shopping_task=True,
                intent=intent,
                confidence=intent.confidence,
                reason="Shopping intent parsed successfully"
            )
        except Exception as e:
            logger.warning(f"Failed to parse shopping intent: {e}")
            return ShoppingSkillOutput(
                is_shopping_task=True,
                intent=None,
                confidence=0.3,
                reason="Shopping keywords detected but intent parsing failed"
            )

    def analyze_page_type(self, page: PageContext, url: str) -> ShoppingPageAnalysis:
        """
        Analyze page type based on DOM content, not just URL patterns.
        This makes the skill work on any e-commerce site.
        """
        if not page:
            return ShoppingPageAnalysis(
                is_shopping_page=False,
                page_type="unknown",
                confidence=0.0,
                detected_elements={},
                reason="No page context available"
            )

        # Count shopping-related elements
        element_counts = {
            "add_to_cart": 0,
            "buy_now": 0,
            "cart_link": 0,
            "checkout": 0,
            "price": 0,
            "product": 0,
        }

        for element in page.elements:
            text = (element.text or "").lower()
            role = element.role or ""

            if "add to cart" in text or "add to basket" in text:
                element_counts["add_to_cart"] += 1
            if "buy now" in text:
                element_counts["buy_now"] += 1
            if role == "link" and ("cart" in text or "bag" in text or "basket" in text):
                element_counts["cart_link"] += 1
            if "checkout" in text or "proceed to checkout" in text:
                element_counts["checkout"] += 1
            if element.role == "button" and ("checkout" in text or "place order" in text):
                element_counts["checkout"] += 1

        # Check for price patterns in elements
        for element in page.elements:
            text = element.text or ""
            if re.search(r"[\$₹€£]\s*[\d,]+(?:\.\d{2})?", text):
                element_counts["price"] += 1

        # Count product-like items
        if page.products:
            element_counts["product"] = len(page.products)

        # Determine page type based on content, not URL
        if element_counts["checkout"] > 0:
            return ShoppingPageAnalysis(
                is_shopping_page=True,
                page_type="checkout",
                confidence=0.8,
                detected_elements=element_counts,
                reason="Detected checkout elements"
            )

        if element_counts["cart_link"] > 0 or element_counts["product"] > 0:
            # Distinguish cart vs product page by cart items
            if page.cart_lines:
                return ShoppingPageAnalysis(
                    is_shopping_page=True,
                    page_type="cart",
                    confidence=0.8,
                    detected_elements=element_counts,
                    reason="Detected cart items and cart links"
                )
            elif element_counts["product"] > 0:
                return ShoppingPageAnalysis(
                    is_shopping_page=True,
                    page_type="search",
                    confidence=0.7,
                    detected_elements=element_counts,
                    reason="Detected multiple products with prices"
                )

        if element_counts["add_to_cart"] > 0 or element_counts["buy_now"] > 0:
            return ShoppingPageAnalysis(
                is_shopping_page=True,
                page_type="product",
                confidence=0.7,
                detected_elements=element_counts,
                reason="Detected add-to-cart or buy-now buttons"
            )

        # Fallback: use URL patterns if content is unclear
        url_lower = url.lower()
        for page_type, patterns in self.url_patterns.items():
            if any(pattern in url_lower for pattern in patterns):
                return ShoppingPageAnalysis(
                    is_shopping_page=True,
                    page_type=page_type,
                    confidence=0.5,
                    detected_elements=element_counts,
                    reason=f"URL pattern matched: {page_type}"
                )

        return ShoppingPageAnalysis(
            is_shopping_page=False,
            page_type="unknown",
            confidence=0.0,
            detected_elements=element_counts,
            reason="No shopping-specific content detected"
        )

    def suggest_product_actions(
        self,
        page: PageContext,
        task: str,
    ) -> ShoppingSkillOutput:
        """Suggest actions for product pages based on shopping intent."""
        shopping_output = self.detect_shopping_task(task)

        if not shopping_output.is_shopping_task:
            return shopping_output

        # Analyze page type
        page_analysis = self.analyze_page_type(page, page.url if page else "")

        if not page_analysis.is_shopping_page:
            return ShoppingSkillOutput(
                is_shopping_task=True,
                intent=shopping_output.intent,
                confidence=shopping_output.confidence,
                suggested_actions=None,
                detected_page_type="unknown",
                reason="Shopping task but page doesn't appear to be shopping-related"
            )

        if not page.products and page_analysis.page_type != "checkout":
            return ShoppingSkillOutput(
                is_shopping_task=True,
                intent=shopping_output.intent,
                confidence=shopping_output.confidence,
                suggested_actions=None,
                detected_page_type=page_analysis.page_type,
                reason=f"No products detected on {page_analysis.page_type} page"
            )

        # Basic suggestions based on shopping intent and page type
        task_intent = parse_task_intent(task)
        suggestions = []

        if page_analysis.page_type == "search":
            if task_intent.goal in {"add_to_cart", "checkout", "purchase"}:
                suggestions.append("select_product")
                suggestions.append("add_to_cart")
            elif task_intent.goal == "search":
                suggestions.append("analyze_results")
            elif task_intent.goal == "compare":
                suggestions.append("compare_products")

        elif page_analysis.page_type == "product":
            if task_intent.goal in {"add_to_cart", "checkout", "purchase"}:
                suggestions.append("add_to_cart")
            elif task_intent.goal == "compare":
                suggestions.append("note_product_details")

        elif page_analysis.page_type == "cart":
            if task_intent.goal in {"checkout", "purchase"}:
                suggestions.append("proceed_to_checkout")
            elif task_intent.goal == "remove":
                suggestions.append("remove_item")

        elif page_analysis.page_type == "checkout":
            if task_intent.goal == "purchase":
                suggestions.append("confirm_payment")
            else:
                suggestions.append("review_order")

        return ShoppingSkillOutput(
            is_shopping_task=True,
            intent=shopping_output.intent,
            confidence=shopping_output.confidence,
            suggested_actions=suggestions,
            detected_page_type=page_analysis.page_type,
            reason=f"Shopping task on {page_analysis.page_type} page with goal: {task_intent.goal}"
        )

    def extract_search_query(self, task: str) -> str:
        """Extract search query from shopping task using shopping-specific vocabularies."""
        # This is shopping-specific - uses shopping stopwords and product terms
        return extract_search_query(task)

    def should_enable_guards(self, url: str, task: str, page: PageContext | None = None) -> bool:
        """
        Determine if shopping guards should be enabled for this URL/task.
        Now based on task content and page analysis, not URL gating.
        """
        shopping_output = self.detect_shopping_task(task)

        if not shopping_output.is_shopping_task:
            return False

        # If we have page context, verify it's actually a shopping page
        if page:
            page_analysis = self.analyze_page_type(page, url)
            return page_analysis.is_shopping_page

        # Without page context, enable based on task alone
        return True

    def get_shopping_vocabularies(self) -> dict:
        """Get shopping-specific vocabularies (for configuration/inspection)."""
        return {
            "verbs": list(_SHOPPING_VERBS),
            "stopwords": list(_SHOPPING_STOPWORDS),
            "product_terms": list(_PRODUCT_TERMS),
            "brands": list(_BRAND_HINTS),
            "url_patterns": self.url_patterns,
        }

    def update_url_patterns(self, patterns: dict[str, list[str]]) -> None:
        """Update URL patterns for site-specific customization."""
        self.url_patterns.update(patterns)


# Singleton instance
_shopping_skill = ShoppingSkill()


def get_shopping_skill() -> ShoppingSkill:
    """Get the shopping skill singleton."""
    return _shopping_skill
