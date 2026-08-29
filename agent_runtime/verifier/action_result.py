"""Action verification — delegates to domain skill."""

from __future__ import annotations

from agent_runtime.executor.actions import AgentAction
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState


def verify_action_result(
    state: RunState,
    action: AgentAction,
    *,
    success: bool,
    verified: bool | None,
    before: BrowserPage | None,
    after: BrowserPage | None,
) -> bool:
    return state.skill().verify_action_result(
        state,
        action,
        success=success,
        verified=verified,
        before=before,
        after=after,
    )


def apply_verified_progress(
    state: RunState,
    action: AgentAction,
    page: BrowserPage | None,
    *,
    ok: bool,
    before: BrowserPage | None = None,
) -> None:
    state.skill().apply_verified_progress(
        state, action, page, ok=ok, before=before
    )
