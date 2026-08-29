"""Behavioral loop detection inspired by autonomous browser agents (soft nudges only)."""

from __future__ import annotations

import hashlib

from agent_runtime.executor.actions import AgentAction
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.planner.planner import action_signature
from agent_runtime.state.run_state import RunState

_WINDOW = 20
_STAGNANT_THRESHOLD = 4
_REPEAT_THRESHOLD = 5
_MAX_AUTO_ESCAPES = 2


def page_fingerprint(page: BrowserPage | None) -> str:
    if page is None:
        return ""
    sample = "|".join(
        f"{el.element_id}:{(el.text or el.aria_label)[:24]}"
        for el in page.elements[:24]
    )
    digest = hashlib.sha1(sample.encode("utf-8")).hexdigest()[:10]
    return f"{page.url}|{page.signature()}|{digest}"


def record_observation(state: RunState, page: BrowserPage | None) -> None:
    fp = page_fingerprint(page)
    if not fp:
        return
    history: list[str] = state.metrics.setdefault("page_fingerprints", [])
    if history and history[-1] == fp:
        state.metrics["stagnant_pages"] = int(state.metrics.get("stagnant_pages", 0)) + 1
    else:
        state.metrics["stagnant_pages"] = 0
    history.append(fp)
    if len(history) > 8:
        state.metrics["page_fingerprints"] = history[-8:]


def record_action_hash(state: RunState, action) -> None:
    sig = action_signature(action)
    if not sig:
        return
    hashes: list[str] = state.metrics.setdefault("action_hashes", [])
    hashes.append(sig)
    if len(hashes) > _WINDOW:
        state.metrics["action_hashes"] = hashes[-_WINDOW:]


def loop_nudge(state: RunState) -> str | None:
    hashes: list[str] = state.metrics.get("action_hashes", [])
    if hashes:
        last = hashes[-1]
        repeats = sum(1 for h in hashes[-12:] if h == last)
        if repeats >= _REPEAT_THRESHOLD:
            return (
                f"Action '{last}' was repeated {repeats} times. "
                "The page may not be changing. Scroll, navigate, or pick a different element."
            )
        if len(hashes) >= 8:
            unique = len(set(hashes[-8:]))
            if unique <= 2:
                return (
                    "Oscillating between the same actions. "
                    "Re-observe the page, scroll if controls are off-screen, "
                    "or try a different strategy."
                )

    stagnant = int(state.metrics.get("stagnant_pages", 0))
    if stagnant >= _STAGNANT_THRESHOLD:
        return (
            "The page has not changed across several steps. "
            "Scroll to reveal more content, dismiss overlays, or navigate elsewhere."
        )
    return None


def _is_stagnant(state: RunState) -> bool:
    stagnant = int(state.metrics.get("stagnant_pages", 0))
    if stagnant >= _STAGNANT_THRESHOLD:
        return True
    hashes: list[str] = state.metrics.get("action_hashes", [])
    if not hashes:
        return False
    last = hashes[-1]
    repeats = sum(1 for h in hashes[-12:] if h == last)
    if repeats >= _REPEAT_THRESHOLD:
        return True
    if len(hashes) >= 8 and len(set(hashes[-8:])) <= 2:
        return True
    return False


def escape_recovery_action(state: RunState) -> AgentAction | None:
    """Deterministic recovery scroll when the page is stagnant (no LLM call)."""
    escapes = int(state.metrics.get("auto_escapes", 0))
    if escapes >= _MAX_AUTO_ESCAPES or not _is_stagnant(state):
        return None
    state.metrics["auto_escapes"] = escapes + 1
    direction = "down" if escapes % 2 == 0 else "up"
    return AgentAction(
        type="scroll",
        parameters={"direction": direction, "amount_px": 700},
        reason="Auto-scroll after stagnant page to reveal off-screen controls",
        expected_outcome="Page fingerprint or visible element set changes",
    )
