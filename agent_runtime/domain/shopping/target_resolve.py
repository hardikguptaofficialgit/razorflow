"""Shopping-specific action target resolution."""

from __future__ import annotations

from agent_runtime.domain.shopping.resolve import refresh_shopping_action_target
from agent_runtime.executor.actions import AgentAction
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.target.resolve import refresh_action_target as refresh_generic_action_target


def refresh_action_target(action: AgentAction, page: BrowserPage | None) -> AgentAction:
    return refresh_shopping_action_target(action, page, generic=refresh_generic_action_target)
