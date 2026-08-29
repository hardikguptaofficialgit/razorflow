"""Test that the agent works in generic mode without shopping dependencies."""

import pytest
from core.config import config, AgentConfig
from core.task_interpretation import interpret_task
from core.domain_skills.shopping_skill import ShoppingSkill, get_shopping_skill


def test_generic_mode_config():
    """Test that generic mode can be enabled via configuration."""
    # Default configuration should allow shopping features
    assert config.enable_shopping_guards is True
    assert config.enable_store_fast_path is True

    # But generic mode should be detectable
    # When all shopping features are disabled, it's generic mode
    generic_config = AgentConfig(
        enable_shopping_guards=False,
        enable_store_fast_path=False,
        enable_shopping_heuristics=False,
    )
    assert generic_config.is_generic_mode() is True


def test_generic_task_interpretation():
    """Test that generic tasks are accepted without shopping verb requirements."""
    # These should all be actionable in generic mode
    generic_tasks = [
        "navigate to google.com",
        "fill the registration form",
        "click the submit button",
        "download the PDF file",
        "scroll down to find the contact link",
        "search for python tutorials",
    ]

    for task in generic_tasks:
        result = interpret_task(task)
        assert result.status == "actionable", f"Task '{task}' should be actionable"
        assert result.reason is None, f"Task '{task}' should not need clarification"


def test_shopping_tasks_still_work():
    """Test that shopping tasks still work when shopping features are enabled."""
    shopping_tasks = [
        "buy wireless earbuds",
        "add shampoo to cart",
        "find the cheapest laptop",
        "checkout with my items",
    ]

    for task in shopping_tasks:
        result = interpret_task(task)
        assert result.status == "actionable", f"Shopping task '{task}' should be actionable"


def test_shopping_skill_optional():
    """Test that shopping skill is optional and doesn't break generic tasks."""
    skill = get_shopping_skill()

    # Generic tasks should not be detected as shopping
    generic_task = "navigate to example.com"
    output = skill.detect_shopping_task(generic_task)
    assert output.is_shopping_task is False
    assert output.confidence == 0.0

    # Shopping tasks should be detected
    shopping_task = "buy wireless earbuds"
    output = skill.detect_shopping_task(shopping_task)
    assert output.is_shopping_task is True
    assert output.confidence > 0.0


def test_shopping_skill_url_agnostic():
    """Test that shopping skill doesn't depend on specific URLs."""
    skill = get_shopping_skill()

    shopping_task = "add headphones to cart"

    # Should work for any URL, not just RazorFlow
    test_urls = [
        "https://amazon.com",
        "https://example.com",
        "https://localhost:3000",
        "https://shop.example.com/products",
    ]

    for url in test_urls:
        should_enable = skill.should_enable_guards(url, shopping_task)
        # In the new design, shopping guards depend on task, not URL
        assert should_enable is True, f"Shopping guards should work for {url}"


def test_generic_utils_work():
    """Test that generic utilities work independently."""
    from core.generic_utils import (
        url_origin,
        detect_auth_page,
        looks_like_gibberish,
        normalize_text,
        parse_money_value,
    )

    # URL origin extraction
    assert url_origin("https://example.com/path") == "https://example.com"
    assert url_origin("http://localhost:3000/search?q=test") == "http://localhost:3000"

    # Auth detection
    is_auth, reason = detect_auth_page("https://example.com/login", "Sign In", [])
    assert is_auth is True
    assert reason == "login"

    # Gibberish detection
    assert looks_like_gibberish("!!") is True  # Only special chars
    assert looks_like_gibberish("test") is False
    assert looks_like_gibberish("aaa") is True  # Repeated chars >= 3
    assert looks_like_gibberish("xyz") is False  # Valid chars, not repeated
    assert looks_like_gibberish("ok") is True  # In garbage tokens list

    # Text normalization
    assert normalize_text("  Hello  World  ") == "hello world"

    # Money parsing
    assert parse_money_value("$1,234.56") == 1234.56
    assert parse_money_value("₹500") == 500.0
    assert parse_money_value("invalid") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
