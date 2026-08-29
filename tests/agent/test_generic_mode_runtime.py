"""Generic-mode tests — AGENT_SHOPPING_DOMAIN=false, no shopping semantics."""

from __future__ import annotations

import pytest

from agent_runtime.config import shopping_domain_enabled
from agent_runtime.domain.registry import resolve_domain_skill
from agent_runtime.executor.actions import AgentAction, ElementTarget
from agent_runtime.executor.translate import translate_action
from agent_runtime.observation.browser_state import (
    BrowserPage,
    ObservedElement,
    ObservedProduct,
    observe_from_page_context,
)
from agent_runtime.observation.signals import infer_generic_page_signals
from agent_runtime.policy.action_gate import classify_action, filter_forbidden_actions
from agent_runtime.policy.goal_guard import action_advances_goal
from agent_runtime.policy.handoff import handoff_allowed
from agent_runtime.recovery.loop_detector import (
    escape_recovery_action,
    loop_nudge,
    record_action_hash,
    record_observation,
)
from agent_runtime.state.run_state import RunState
from agent_runtime.target.resolve import refresh_action_target
from agent_runtime.task.parse import parse_task_spec
from agent_runtime.task.parser import parse_task, parse_task_with_spec
from agent_runtime.verifier.action_result import apply_verified_progress, verify_action_result
from agent_runtime.verifier.goal import approve_completion, is_goal_satisfied
from core.protocol import PageContext, PageElementSummary, PageProductSummary

pytestmark = pytest.mark.usefixtures("generic_mode")


@pytest.fixture
def generic_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_SHOPPING_DOMAIN", "false")


def _state(task: str) -> RunState:
    parsed, spec = parse_task_with_spec(task)
    state = RunState(
        run_id="generic-1",
        task=task,
        parsed_task=parsed,
        task_spec=spec,
        current_phase=spec.target_phase,
    )
    state.bind_skill(resolve_domain_skill(task, shopping_enabled=False))
    assert state.skill().skill_id == "generic"
    return state


def _page(**kwargs) -> BrowserPage:
    defaults = dict(
        title="Example",
        url="https://example.com/page",
        path="/page",
        search_query="",
        elements=[],
        products=[],
        cart_lines=[],
        signals=[],
    )
    defaults.update(kwargs)
    return BrowserPage(**defaults)


# --- parsing ---


def test_generic_mode_flag_off() -> None:
    assert shopping_domain_enabled() is False


def test_natural_language_parsing_uses_achieve_goal() -> None:
    for task in (
        "click the Submit button",
        "fill in the registration form",
        "scroll down and find the contact link",
        "navigate to the settings page",
    ):
        parsed = parse_task(task)
        spec = parse_task_spec(task)
        assert parsed.actionable is True
        assert parsed.goal == "achieve"
        assert spec.goal == "achieve"
        assert spec.target_phase == "complete"
        assert spec.metadata.get("domain") != "shopping"


def test_gibberish_needs_clarification_not_shopping_unknown() -> None:
    parsed = parse_task("wdwd")
    assert parsed.actionable is False
    assert parsed.goal == "clarify"
    assert "cart" not in parsed.summary().lower()


def test_shopping_phrases_do_not_invoke_shopping_parser() -> None:
    """Leakage guard: commerce wording must not produce shopping goals in generic mode."""
    for task in (
        "add shampoo to my cart",
        "buy wireless earbuds",
        "checkout with my items",
        "find the cheapest laptop",
    ):
        parsed, spec = parse_task_with_spec(task)
        assert parsed.goal == "achieve", task
        assert spec.metadata.get("domain") != "shopping"
        assert spec.metadata.get("intent") is None
        assert "cart_updated" not in spec.goal_phases


# --- actions ---


def test_translate_core_action_types() -> None:
    cases = [
        AgentAction(type="click", target=ElementTarget(element_id="e1", role="button"), reason="click", expectedOutcome="ok"),
        AgentAction(type="type", target=ElementTarget(element_id="e2", role="input"), parameters={"text": "hello"}, reason="type", expectedOutcome="ok"),
        AgentAction(type="scroll", parameters={"direction": "down", "amount_px": 400}, reason="scroll", expectedOutcome="ok"),
        AgentAction(type="wait", parameters={"duration_ms": 250}, reason="wait", expectedOutcome="ok"),
        AgentAction(type="go_back", reason="back", expectedOutcome="ok"),
        AgentAction(type="navigate", parameters={"url": "https://example.com/next"}, reason="nav", expectedOutcome="ok"),
    ]
    expected_actions = {
        "click": "click_element",
        "type": "type_in_element",
        "scroll": "scroll_page",
        "wait": "wait",
        "go_back": "go_back",
        "navigate": "navigate_url",
    }
    for action in cases:
        steps = translate_action(action)
        assert len(steps) == 1
        assert steps[0].action == expected_actions[action.type]


# --- target resolution ---


def test_target_resolution_by_element_text_not_product_cart() -> None:
    page = _page(
        elements=[
            ObservedElement(
                element_id="e1",
                index=1,
                role="button",
                tag="button",
                text="Add to cart",
                placeholder="",
                aria_label="",
                clickable=True,
            ),
        ],
        products=[
            ObservedProduct(
                product_id="p1",
                title="Galaxy Buds",
                price_text="₹4999",
                rating_text="",
                add_element_id="e99",
            ),
        ],
    )
    action = AgentAction(
        type="click",
        target=ElementTarget(role="button", description="Add to cart"),
        reason="add",
        expectedOutcome="click",
    )
    resolved = refresh_action_target(action, page)
    assert resolved.target is not None
    assert resolved.target.element_id == "e1"
    assert resolved.target.element_id != "e99"


# --- recovery & loop prevention ---


def test_loop_nudge_on_repeated_actions() -> None:
    state = _state("click the save button")
    action = AgentAction(
        type="click",
        target=ElementTarget(element_id="e1", role="button", description="Save"),
        reason="save",
        expectedOutcome="saved",
    )
    for _ in range(6):
        record_action_hash(state, action)
    nudge = loop_nudge(state)
    assert nudge is not None
    assert "repeated" in nudge.lower() or "oscillat" in nudge.lower()


def test_escape_recovery_scroll_on_stagnant_page() -> None:
    state = _state("scroll to the footer")
    page = _page()
    for _ in range(5):
        record_observation(state, page)
        state.metrics["stagnant_pages"] = int(state.metrics.get("stagnant_pages", 0)) + 1
    state.metrics["stagnant_pages"] = 4
    escape = escape_recovery_action(state)
    assert escape is not None
    assert escape.type == "scroll"


# --- goal verification ---


def test_goal_verification_requires_verified_progress() -> None:
    state = _state("submit the contact form")
    before = _page(url="https://example.com/form", path="/form")
    after = _page(
        url="https://example.com/thanks",
        path="/thanks",
        elements=[
            ObservedElement(
                element_id="e1",
                index=1,
                role="heading",
                tag="h1",
                text="Thank you",
                placeholder="",
                aria_label="",
            ),
        ],
    )
    click = AgentAction(
        type="click",
        target=ElementTarget(element_id="e5", role="button", description="Submit"),
        reason="submit",
        expectedOutcome="submitted",
    )
    ok = verify_action_result(
        state,
        click,
        success=True,
        verified=None,
        before=before,
        after=after,
    )
    assert ok is True
    apply_verified_progress(state, click, after, ok=ok, before=before)
    assert state.verified_progress_count == 1
    assert is_goal_satisfied(state, after)
    assert approve_completion(state, after, source="test")


# --- handoff ---


def test_handoff_allowed_for_login_gate() -> None:
    login_page = _page(signals=["login_required"])
    assert handoff_allowed(login_page, "Please sign in to continue") is True

    plain_page = _page()
    assert handoff_allowed(plain_page, "uncertain click failed") is False
    assert state_skill_handoff(plain_page, "Please complete captcha") is True


def state_skill_handoff(page: BrowserPage, reason: str) -> bool:
    state = _state("complete login")
    state.memory.current_page = page
    return state.skill().handoff_allowed(page, reason)


# --- no shopping leakage ---


def test_generic_signals_exclude_commerce_paths() -> None:
    ctx = PageContext(
        title="Shop",
        url="https://shop.example/cart",
        elements=[
            PageElementSummary(
                index=1,
                role="button",
                tag="button",
                text="Proceed to checkout",
            ),
        ],
        products=[PageProductSummary(title="Item", priceText="₹10")],
        cartLines=[],
    )
    signals = infer_generic_page_signals(ctx)
    assert "cart_page" not in signals
    assert "checkout_page" not in signals
    assert "search_results_page" not in signals

    page = observe_from_page_context(
        ctx,
        signal_infer=resolve_domain_skill(
            "achieve task", shopping_enabled=False
        ).infer_page_signals,
    )
    assert page is not None
    assert "cart_page" not in page.signals
    assert "checkout_page" not in page.signals


def test_classify_action_has_no_shopping_categories() -> None:
    add = AgentAction(
        type="click",
        target=ElementTarget(role="button", description="Add to cart"),
        reason="add to cart",
        expectedOutcome="cart",
    )
    categories = classify_action(add)
    assert "add_to_cart" not in categories
    assert "checkout" not in categories


def test_filter_forbidden_does_not_apply_shopping_phase_rules() -> None:
    spec = parse_task_spec("find documentation")
    allowed, blocked = filter_forbidden_actions(
        spec,
        [
            AgentAction(
                type="click",
                target=ElementTarget(role="link", description="Docs"),
                reason="open docs",
                expectedOutcome="navigate",
            )
        ],
        current_phase="search_results",
    )
    assert allowed
    assert not blocked


def test_planner_nudges_empty_in_generic_mode() -> None:
    state = _state("open the help page")
    state.memory.current_page = _page()
    assert state.skill().planner_nudges(state, state.memory.current_page) == []


def test_resolve_domain_skill_is_generic() -> None:
    assert (
        resolve_domain_skill("add items to cart", shopping_enabled=False).skill_id
        == "generic"
    )


def test_action_advances_goal_allows_scroll_in_generic_mode() -> None:
    state = _state("scroll to the footer")
    state.memory.current_page = _page()
    scroll = AgentAction(type="scroll", reason="scroll", expectedOutcome="more")
    ok, _ = action_advances_goal(state, scroll)
    assert ok is True
