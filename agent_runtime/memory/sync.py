"""Memory sync — delegates to domain skill."""

from __future__ import annotations

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState


def sync_memory_from_observation(state: RunState, page: BrowserPage | None) -> None:
    state.skill().sync_memory(state, page)
