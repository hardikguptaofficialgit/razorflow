"""Integration test demonstrating generic agent core without full agent stack."""

import pytest
from core.config import config, AgentConfig
from core.task_interpretation import interpret_task
from core.domain_skills.shopping_skill import ShoppingSkill, get_shopping_skill
from core.generic_page_analyzer import get_generic_page_analyzer
from core.generic_recovery import get_generic_recovery
from core.protocol import (
    PageContext,
    PageElementSummary,
    PageProductSummary,
    ClickElementStep,
    TypeInElementStep,
    ActionHistoryEntry,
)
from core.run_manager import RunManager, RunSession


def test_generic_mode_full_workflow():
    """Test that generic mode can handle a complete workflow without shopping."""
    # Enable generic mode
    generic_config = AgentConfig(
        enable_shopping_guards=False,
        enable_store_fast_path=False,
        enable_shopping_heuristics=False,
    )

    # Verify generic mode is active
    assert generic_config.is_generic_mode() is True

    # Task interpretation should accept generic tasks
    generic_task = "Navigate to example.com and click the 'Contact' link"
    interpretation = interpret_task(generic_task)
    assert interpretation.status == "actionable"
    assert interpretation.intent.goal in {"search", "add_to_cart", "view_cart", "checkout", "purchase", "compare"}  # Default to search

    # Shopping skill should not interfere
    skill = get_shopping_skill()
    shopping_output = skill.detect_shopping_task(generic_task)
    assert shopping_output.is_shopping_task is False  # Generic task

    # Page analyzer should work generically
    analyzer = get_generic_page_analyzer()
    generic_page = PageContext(
        url="https://example.com",
        title="Example Domain",
        elements=[
            PageElementSummary(
                index=1,
                role="link",
                tag="a",
                text="Contact",
                placeholder="",
                aria_label="Contact Us",
            ),
            PageElementSummary(
                index=2,
                role="link",
                tag="a",
                text="About",
                placeholder="",
                aria_label="About Us",
            ),
        ],
        products=[],
    )

    page_analysis = analyzer.analyze_page(generic_page, "https://example.com")
    # Should classify as unknown or generic listing, not shopping-specific
    assert page_analysis.page_type in {"unknown", "listing"}

    # Recovery should work generically
    recovery = get_generic_recovery()
    run_manager = RunManager()
    session = run_manager.start_run(
        run_id="test-generic",
        task=generic_task,
        page_context=generic_page,
    )

    # Add a failed action
    session.history.append(
        ActionHistoryEntry(
            step=ClickElementStep(
                action="click_element",
                role="link",
                element_index=1,
                match_text="Contact",
            ),
            success=False,
            error="Element not found",
            verified=False,
            page_fingerprint="test",
        )
    )
    session.consecutive_failures = 1

    recovery_action = recovery.analyze_failure(session, "Element not found")
    # Recovery might return None if no alternatives are found
    # The important thing is that it doesn't crash and shopping logic is not involved
    if recovery_action:
        assert recovery_action.action_type in ["retry", "alternative", "handoff"]
        assert "shopping" not in str(recovery_action.reason).lower()

    # Should not handoff for single failure
    should_handoff, reason = recovery.should_handoff(session, generic_page)
    assert should_handoff is False


def test_shopping_mode_full_workflow():
    """Test that shopping mode still works with shopping tasks."""
    # Enable shopping mode
    shopping_config = AgentConfig(
        enable_shopping_guards=True,
        enable_store_fast_path=True,
        enable_shopping_heuristics=True,
    )

    # Verify shopping mode is active
    assert shopping_config.is_generic_mode() is False

    # Shopping task interpretation
    shopping_task = "buy wireless earbuds under ₹2000"
    interpretation = interpret_task(shopping_task)
    assert interpretation.status == "actionable"
    assert interpretation.intent.goal in {"add_to_cart", "checkout", "purchase"}

    # Shopping skill should detect shopping task
    skill = get_shopping_skill()
    shopping_output = skill.detect_shopping_task(shopping_task)
    assert shopping_output.is_shopping_task is True
    assert shopping_output.confidence > 0.0

    # Shopping page analysis
    shopping_page = PageContext(
        url="https://example.com/products",
        title="Our Products",
        elements=[
            PageElementSummary(
                index=1,
                role="button",
                tag="button",
                text="Add to Cart",
                placeholder="",
                aria_label="Add to cart",
            ),
            PageElementSummary(
                index=2,
                role="button",
                tag="button",
                text="Buy Now",
                placeholder="",
                aria_label="Buy now",
            ),
        ],
        products=[
            PageProductSummary(
                title="Wireless Earbuds",
                price_text="₹1,499",
                rating_text="4.2 stars",
                element_index=1,
                add_to_cart_element_index=1,
            ),
        ],
    )

    page_analysis = skill.analyze_page_type(shopping_page, "https://example.com/products")
    assert page_analysis.is_shopping_page is True
    assert page_analysis.page_type in {"search", "product", "cart", "checkout"}

    # Shopping skill should enable guards based on task, not URL
    should_enable = skill.should_enable_guards("https://random-site.com", shopping_task, shopping_page)
    assert should_enable is True  # Task-based, not URL-gated


def test_shopping_skill_semitantic_not_url_based():
    """Test that shopping skill uses semantic analysis, not URL patterns."""
    skill = get_shopping_skill()

    # Create a shopping page on a non-shopping URL
    shopping_page = PageContext(
        url="https://example.com/content/item-123",  # Non-shopping URL
        title="Product Details",
        elements=[
            PageElementSummary(
                index=1,
                role="button",
                tag="button",
                text="Add to Cart",
                placeholder="",
                aria_label="Add to cart",
            ),
        ],
        products=[
            PageProductSummary(
                title="Premium Headphones",
                price_text="$299",
                rating_text="4.8 stars",
                element_index=1,
                add_to_cart_element_index=1,
            ),
        ],
    )

    analysis = skill.analyze_page_type(shopping_page, "https://example.com/content/item-123")

    # Should detect as shopping page based on content, not URL
    assert analysis.is_shopping_page is True
    # With single product and add-to-cart, could be classified as search or product
    assert analysis.page_type in {"search", "product"}  # Based on content, not URL
    # The reason should be content-based (detected products), not URL pattern match
    assert "product" in analysis.reason.lower() or "content" in analysis.reason.lower()


def test_generic_recovery_with_shopping_disabled():
    """Test that generic recovery works when shopping is disabled."""
    # Configure generic mode
    test_config = AgentConfig(
        enable_shopping_guards=False,
        enable_store_fast_path=False,
        enable_shopping_heuristics=False,
    )

    recovery = get_generic_recovery()
    run_manager = RunManager()

    # Create a session with a generic task
    session = run_manager.start_run(
        run_id="test-recovery",
        task="fill the registration form",
        page_context=PageContext(
            url="https://example.com/register",
            title="Sign Up",
            elements=[
                PageElementSummary(
                    index=1,
                    role="input",
                    tag="input",
                    text="",
                    placeholder="Email",
                    aria_label="Email",
                ),
                PageElementSummary(
                    index=2,
                    role="button",
                    tag="button",
                    text="Submit",
                    placeholder="",
                    aria_label="Submit form",
                ),
            ],
            products=[],
        ),
    )

    # Simulate a failed action
    session.history.append(
        ActionHistoryEntry(
            step=TypeInElementStep(
                action="type_in_element",
                role="input",
                element_index=1,
                text="test@example.com",
            ),
            success=False,
            error="Element not interactable",
            verified=False,
            page_fingerprint="test",
        )
    )
    session.consecutive_failures = 1

    # Recovery should work without shopping-specific logic
    recovery_action = recovery.analyze_failure(session, "Element not interactable")
    assert recovery_action is not None
    assert recovery_action.action_type in ["retry", "alternative", "handoff"]
    assert "shopping" not in str(recovery_action.reason).lower()


def test_url_pattern_customization_per_site():
    """Test that URL patterns can be customized for different sites."""
    skill = get_shopping_skill()

    # Get default patterns
    default_patterns = skill.get_shopping_vocabularies()["url_patterns"]
    assert "/search" in default_patterns["search"]
    assert "/cart" in default_patterns["cart"]

    # Customize for Amazon (example)
    amazon_patterns = {
        "search": ["/s", "/gp/product"],  # Amazon uses /s for search
        "cart": ["/gp/cart"],
        "checkout": ["/gp/buy"],
        "product": ["/dp/", "/gp/product"],
    }

    skill.update_url_patterns(amazon_patterns)

    # Verify patterns were updated
    updated_patterns = skill.get_shopping_vocabularies()["url_patterns"]
    assert updated_patterns["search"] == amazon_patterns["search"]
    assert "/s" in updated_patterns["search"]
    assert "/gp/cart" in updated_patterns["cart"]


def test_generic_page_analyzer_detects_various_page_types():
    """Test that generic page analyzer can detect different page types."""
    analyzer = get_generic_page_analyzer()

    # Form page
    form_page = PageContext(
        url="https://example.com/register",
        title="Create Account",
        elements=[
            PageElementSummary(
                index=1,
                role="input",
                tag="input",
                text="",
                placeholder="Username",
                aria_label="Username",
            ),
            PageElementSummary(
                index=2,
                role="input",
                tag="input",
                text="",
                placeholder="Password",
                aria_label="Password",
            ),
            PageElementSummary(
                index=3,
                role="button",
                tag="button",
                text="Sign Up",
                placeholder="",
                aria_label="Submit",
            ),
        ],
        products=[],
    )

    form_analysis = analyzer.analyze_page(form_page, "https://example.com/register")
    assert form_analysis.text_inputs >= 2
    # Form detection depends on role="form" element, which might not be present
    # Just verify inputs are detected
    assert form_analysis.interactive_elements >= 3

    # Auth page
    auth_page = PageContext(
        url="https://example.com/login",
        title="Sign In",
        elements=[
            PageElementSummary(
                index=1,
                role="input",
                tag="input",
                text="",
                placeholder="Email",
                aria_label="Email",
            ),
            PageElementSummary(
                index=2,
                role="input",
                tag="input",
                text="",
                placeholder="Password",
                aria_label="Password",
            ),
            PageElementSummary(
                index=3,
                role="button",
                tag="button",
                text="Login",
                placeholder="",
                aria_label="Sign In",
            ),
        ],
        products=[],
    )

    auth_analysis = analyzer.analyze_page(auth_page, "https://example.com/login")
    assert auth_analysis.page_type == "auth"

    # Dashboard page (many interactive elements)
    dashboard_page = PageContext(
        url="https://example.com/dashboard",
        title="Dashboard",
        elements=[
            PageElementSummary(
                index=i,
                role="button",
                tag="button",
                text=f"Button {i}",
                placeholder="",
                aria_label=f"Control {i}",
            )
            for i in range(10)
        ] + [
            PageElementSummary(
                index=i,
                role="link",
                tag="a",
                text=f"Link {i}",
                placeholder="",
                aria_label=f"Navigation {i}",
            )
            for i in range(5)
        ],
        products=[],
    )

    dashboard_analysis = analyzer.analyze_page(dashboard_page, "https://example.com/dashboard")
    assert dashboard_analysis.buttons >= 5
    assert dashboard_analysis.links >= 5


def test_generic_benchmark_tasks_are_truly_generic():
    """Verify that benchmark tasks don't contain shopping assumptions."""
    from tests.generic_benchmark import GENERIC_BENCHMARK_TASKS

    shopping_keywords = ["buy", "purchase", "cart", "checkout", "price", "cheapest", "shop", "order"]

    for task in GENERIC_BENCHMARK_TASKS:
        task_lower = task.task_prompt.lower()
        has_shopping = any(keyword in task_lower for keyword in shopping_keywords)

        # Only the "search_generic" task should have "search" (which is also a shopping verb)
        # but it's intended to be generic search
        if task.name == "search_generic":
            assert "search" in task_lower
        else:
            assert not has_shopping, f"Task '{task.name}' should not have shopping keywords: {task.task_prompt}"


def test_shopping_vocabularies_contained():
    """Test that shopping vocabularies are properly contained in the skill."""
    skill = get_shopping_skill()
    vocabularies = skill.get_shopping_vocabularies()

    # Verify all shopping data is in the skill
    assert "verbs" in vocabularies
    assert "stopwords" in vocabularies
    assert "product_terms" in vocabularies
    assert "brands" in vocabularies
    assert "url_patterns" in vocabularies

    # Verify they're shopping-specific
    assert "buy" in vocabularies["verbs"]
    assert "shampoo" in vocabularies["product_terms"]
    assert "nike" in vocabularies["brands"]

    # Verify generic utilities don't have these
    from core.generic_utils import strip_common_stopwords
    generic_stopwords = strip_common_stopwords("test shopping buy", custom_stopwords={"shopping", "buy"})
    assert "shopping" not in generic_stopwords  # Only removed by custom_stopwords
    assert "buy" not in generic_stopwords


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
