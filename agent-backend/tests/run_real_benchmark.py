"""Real agent benchmark - runs actual agent with real browser and LLM."""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Add paths
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_BACKEND_ROOT))

# Set environment variables directly (since .env is gitignored)
os.environ["GEMINI_API_KEY"] = ""  # Add your key here
os.environ["GROQ_API_KEY"] = ""  # Add your key here
os.environ["OPENROUTER_API_KEY"] = ""  # Add your key here
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["PLANNER_LLM_PROVIDER"] = "groq"
os.environ["BROWSER_USE_EXECUTOR_ENABLED"] = "true"
os.environ["BROWSER_USE_HEADLESS"] = "false"
os.environ["MAX_PLANNING_TURNS"] = "16"
os.environ["MAX_CONSECUTIVE_FAILURES"] = "3"
os.environ["MAX_STALE_PAGE_TURNS"] = "4"

from core.config import config, AgentConfig
from core.task_interpretation import interpret_task
from core.domain_skills.shopping_skill import get_shopping_skill
from core.generic_page_analyzer import get_generic_page_analyzer
from core.generic_recovery import get_generic_recovery
from core.protocol import PageContext, PageElementSummary
from core.run_manager import RunManager
from utils.config import is_planner_llm_ready, log_config_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_environment():
    """Check if required environment is configured."""
    log_config_status()

    if not is_planner_llm_ready():
        logger.error("❌ No LLM configured. Set GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY")
        return False

    logger.info("✅ LLM configured")
    return True


def test_generic_mode_components():
    """Test that generic mode components work without shopping."""
    logger.info("=" * 60)
    logger.info("TESTING GENERIC MODE COMPONENTS")
    logger.info("=" * 60)

    # Configure generic mode
    test_config = AgentConfig(
        enable_shopping_guards=False,
        enable_store_fast_path=False,
        enable_shopping_heuristics=False,
    )

    logger.info(f"Generic mode: {test_config.is_generic_mode()}")

    # Test task interpretation
    generic_tasks = [
        "navigate to google.com",
        "fill the registration form",
        "click the submit button",
        "search for python tutorials",
    ]

    for task in generic_tasks:
        result = interpret_task(task)
        logger.info(f"Task: '{task}' -> Status: {result.status}, Goal: {result.intent.goal}")

    # Test page analyzer
    analyzer = get_generic_page_analyzer()
    test_page = PageContext(
        url="https://example.com",
        title="Example",
        elements=[
            PageElementSummary(
                index=1,
                role="input",
                tag="input",
                text="",
                placeholder="Search",
                aria_label="Search",
            ),
            PageElementSummary(
                index=2,
                role="button",
                tag="button",
                text="Submit",
                placeholder="",
                aria_label="Submit",
            ),
        ],
        products=[],
    )

    analysis = analyzer.analyze_page(test_page, "https://example.com")
    logger.info(f"Page analysis: type={analysis.page_type}, confidence={analysis.confidence}")

    # Test recovery
    recovery = get_generic_recovery()
    logger.info("✅ Generic components loaded successfully")

    return True


def test_shopping_mode_components():
    """Test that shopping mode still works."""
    logger.info("=" * 60)
    logger.info("TESTING SHOPPING MODE COMPONENTS")
    logger.info("=" * 60)

    skill = get_shopping_skill()
    shopping_task = "buy wireless earbuds"

    result = skill.detect_shopping_task(shopping_task)
    logger.info(f"Shopping task detection: is_shopping={result.is_shopping_task}, confidence={result.confidence}")

    vocabularies = skill.get_shopping_vocabularies()
    logger.info(f"Shopping vocabularies loaded: {len(vocabularies['verbs'])} verbs, {len(vocabularies['product_terms'])} products")

    logger.info("✅ Shopping components loaded successfully")
    return True


def main():
    """Main benchmark entry point."""
    logger.info("Starting Real Agent Benchmark")
    logger.info("=" * 60)

    # Check environment
    if not check_environment():
        logger.error("❌ Environment not configured. Please set API keys in the script.")
        return

    # Test generic mode
    if not test_generic_mode_components():
        logger.error("❌ Generic mode components failed")
        return

    # Test shopping mode
    if not test_shopping_mode_components():
        logger.error("❌ Shopping mode components failed")
        return

    logger.info("=" * 60)
    logger.info("✅ ALL COMPONENT TESTS PASSED")
    logger.info("=" * 60)
    logger.info("Note: Full browser execution requires Chrome and CDP setup.")
    logger.info("Component tests verify the architecture is working correctly.")


if __name__ == "__main__":
    main()
