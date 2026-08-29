"""Generic page analysis - semantic page type detection without domain assumptions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

from core.protocol import PageContext, PageElementSummary
from core.generic_utils import normalize_text

logger = logging.getLogger(__name__)


@dataclass
class GenericPageAnalysis:
    """Analysis of a page's semantic content."""
    page_type: Literal["form", "search", "listing", "detail", "dashboard", "auth", "unknown"]
    confidence: float
    key_elements: dict[str, int]
    interactive_elements: int
    text_inputs: int
    forms: int
    buttons: int
    links: int
    reason: str


class GenericPageAnalyzer:
    """
    Generic page analyzer that detects page types from DOM content.
    Works without domain-specific assumptions (no shopping rules).
    """

    def __init__(self):
        pass

    def analyze_page(self, page: PageContext, url: str) -> GenericPageAnalysis:
        """Analyze page type based on semantic DOM content."""
        if not page:
            return GenericPageAnalysis(
                page_type="unknown",
                confidence=0.0,
                key_elements={},
                interactive_elements=0,
                text_inputs=0,
                forms=0,
                buttons=0,
                links=0,
                reason="No page context available"
            )

        # Count element types
        element_counts = {
            "form": 0,
            "input": 0,
            "button": 0,
            "link": 0,
            "text": 0,
            "search": 0,
            "submit": 0,
            "cancel": 0,
            "auth": 0,
        }

        for element in page.elements:
            role = element.role or ""
            text = normalize_text(element.text or "")
            placeholder = normalize_text(element.placeholder or "")
            combined = f"{text} {placeholder}"

            if role == "form":
                element_counts["form"] += 1
            elif role in {"input", "search"}:
                element_counts["input"] += 1
                if "search" in combined:
                    element_counts["search"] += 1
            elif role == "button":
                element_counts["button"] += 1
                if "submit" in combined or "sign" in combined or "login" in combined:
                    element_counts["submit"] += 1
                if "cancel" in combined:
                    element_counts["cancel"] += 1
            elif role == "link":
                element_counts["link"] += 1

            # Auth detection
            if any(word in combined for word in ["login", "signin", "sign in", "auth", "password"]):
                element_counts["auth"] += 1

        # Determine page type
        page_type, confidence, reason = self._classify_page_type(
            element_counts, page, url
        )

        return GenericPageAnalysis(
            page_type=page_type,
            confidence=confidence,
            key_elements=element_counts,
            interactive_elements=len(page.elements),
            text_inputs=element_counts["input"],
            forms=element_counts["form"],
            buttons=element_counts["button"],
            links=element_counts["link"],
            reason=reason,
        )

    def _classify_page_type(
        self,
        element_counts: dict[str, int],
        page: PageContext,
        url: str,
    ) -> tuple[Literal["form", "search", "listing", "detail", "dashboard", "auth", "unknown"], float, str]:
        """Classify page type based on element counts and content."""

        # Auth pages
        if element_counts["auth"] >= 2 or (
            element_counts["input"] >= 2
            and element_counts["submit"] >= 1
            and any(word in url.lower() for word in ["login", "signin", "auth"])
        ):
            return "auth", 0.8, "Detected authentication elements"

        # Search pages
        if element_counts["search"] >= 1 or (
            element_counts["input"] >= 1
            and any(word in url.lower() for word in ["search", "query", "find"])
        ):
            return "search", 0.7, "Detected search functionality"

        # Form pages
        if element_counts["form"] >= 1 and element_counts["input"] >= 2:
            return "form", 0.7, "Detected form with multiple inputs"

        # Listing pages (multiple similar items)
        if page.products and len(page.products) >= 3:
            return "listing", 0.8, "Detected multiple product-like items"

        # Detail pages (single focused item)
        if page.products and len(page.products) == 1:
            return "detail", 0.7, "Detected single product-like item"

        # Dashboard pages (many controls, varied content)
        if element_counts["button"] >= 5 and element_counts["link"] >= 5:
            return "dashboard", 0.6, "Detected many interactive elements"

        # Default: unknown
        return "unknown", 0.0, "Could not classify page type"

    def find_actionable_elements(
        self,
        page: PageContext,
        action_types: list[str] | None = None,
    ) -> list[tuple[int, str, str]]:
        """
        Find elements that can be acted upon.
        Returns list of (index, role, text) tuples.
        """
        if not page:
            return []

        actionable = []
        action_types = action_types or ["button", "link", "input"]

        for position, element in enumerate(page.elements, start=1):
            if element.role in action_types:
                index = element.index if element.index > 0 else position
                text = normalize_text(element.text or "")
                actionable.append((index, element.role, text))

        return actionable

    def find_elements_by_text(
        self,
        page: PageContext,
        text_pattern: str,
        case_sensitive: bool = False,
    ) -> list[tuple[int, str, str]]:
        """Find elements matching a text pattern."""
        if not page:
            return []

        matches = []
        pattern = text_pattern if case_sensitive else text_pattern.lower()

        for position, element in enumerate(page.elements, start=1):
            text = element.text or ""
            placeholder = element.placeholder or ""
            aria_label = element.aria_label or ""

            search_text = f"{text} {placeholder} {aria_label}"
            if not case_sensitive:
                search_text = search_text.lower()

            if pattern in search_text:
                index = element.index if element.index > 0 else position
                matches.append((index, element.role, text))

        return matches

    def detect_scroll_needed(
        self,
        page: PageContext,
        target_text: str,
    ) -> tuple[bool, str]:
        """
        Detect if scrolling is needed to find an element.
        Returns (needs_scroll, reason).
        """
        if not page:
            return False, "No page context"

        # Check if target is immediately visible
        matches = self.find_elements_by_text(page, target_text)
        if matches:
            return False, "Target element already visible"

        # Heuristic: if page has many elements but target not found, might need scroll
        if len(page.elements) > 20:
            return True, "Many elements but target not found - likely below fold"

        return False, "Unable to determine if scroll needed"


# Singleton instance
_generic_page_analyzer = GenericPageAnalyzer()


def get_generic_page_analyzer() -> GenericPageAnalyzer:
    """Get the generic page analyzer singleton."""
    return _generic_page_analyzer
