"""Unit tests for checkout login handoff detection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent_runtime.observation.browser_state import BrowserPage, observe_from_page_context
from core.protocol import PageContext, PageElementSummary
from agent_runtime.runtime import _completion_or_handoff
from agent_runtime.state.run_state import RunState
from agent_runtime.task.parse import parse_task_spec
from agent_runtime.task.parser import parse_task
from agent_runtime.memory.task_memory import TaskMemory
from agent_runtime.verifier.checkout_flow import checkout_requires_handoff


def test_checkout_auth_redirect_requires_handoff() -> None:
    page = BrowserPage(
        title="Demo",
        url="http://localhost:3001/demo?auth=login&next=%2Fdemo%2Fcheckout",
        path="/demo",
        search_query="",
        signals=["login_required", "checkout_auth_gate"],
    )
    assert checkout_requires_handoff(page)


def test_header_sign_in_does_not_require_checkout_handoff() -> None:
    page = BrowserPage(
        title="Demo",
        url="http://localhost:3001/demo",
        path="/demo",
        search_query="",
        signals=[],
        elements=[],
    )
    assert not checkout_requires_handoff(page)


def test_checkout_login_modal_on_current_page_requires_handoff() -> None:
    page = observe_from_page_context(
        PageContext(
            title="Demo",
            url="http://localhost:3001/demo",
            elements=[
                PageElementSummary(
                    index=1,
                    role="button",
                    tag="button",
                    text="Sign in to checkout",
                    placeholder="",
                    aria_label="",
                )
            ],
        )
    )
    assert page is not None
    assert checkout_requires_handoff(page)


def test_truncated_sign_in_to_checkout_requires_handoff() -> None:
    page = observe_from_page_context(
        PageContext(
            title="Demo",
            url="http://localhost:3001/demo",
            elements=[
                PageElementSummary(
                    index=1,
                    role="button",
                    tag="button",
                    text="Sign in to check",
                    placeholder="",
                    aria_label="",
                )
            ],
        )
    )
    assert page is not None
    assert checkout_requires_handoff(page)


def test_completion_or_handoff_returns_handoff_on_login_gate() -> None:
    parsed = parse_task("add snacks and checkout")
    spec = parse_task_spec(parsed.raw)
    state = RunState(
        run_id="h1",
        task=parsed.raw,
        parsed_task=parsed,
        task_spec=spec,
        memory=TaskMemory(goal=parsed.goal, items_target=1),
        current_phase="checkout",
    )
    page = BrowserPage(
        title="Demo",
        url="http://localhost:3001/demo?auth=login&next=/demo/checkout",
        path="/demo",
        search_query="",
        signals=["login_required", "checkout_auth_gate"],
    )
    result = _completion_or_handoff(state, page, source="post_action")
    assert result.kind == "handoff"
