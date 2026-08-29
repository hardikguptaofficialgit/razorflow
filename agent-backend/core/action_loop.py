"""Detect repetitive agent actions (Browser Use ActionLoopDetector-style nudges)."""

from __future__ import annotations

from core.run_manager import RunSession


def action_signature(step) -> str:
    action = getattr(step, "action", "")
    if action == "click_element":
        index = getattr(step, "element_index", None)
        label = (getattr(step, "match_text", "") or "").strip().lower()
        return f"click:{index}:{label}"
    if action == "navigate_url":
        return f"nav:{getattr(step, 'url', '')}"
    if action == "type_in_element":
        return f"type:{(getattr(step, 'text', '') or '').strip().lower()}"
    return str(action)


def consecutive_success_repeats(session: RunSession, signature: str, window: int = 5) -> int:
    repeats = 0
    for entry in reversed(session.history[-window:]):
        if not entry.success:
            break
        if action_signature(entry.step) == signature:
            repeats += 1
        else:
            break
    return repeats


def detect_loop_nudge(session: RunSession) -> str | None:
    """Return planner nudge text when recent actions look stuck in a loop."""
    if len(session.history) < 2:
        return None

    recent = [entry for entry in session.history[-6:] if entry.success]
    if len(recent) < 2:
        return None

    last_sig = action_signature(recent[-1].step)
    repeats = consecutive_success_repeats(session, last_sig)
    if repeats >= 2:
        return (
            "LOOP DETECTED: The last action repeated without progress. "
            "Do NOT repeat the same click or navigation. "
            "Pick a different elementIndex, try the next product query, "
            "or use wait_for_user if the page cannot satisfy the goal."
        )

    navigate_sigs = [
        action_signature(entry.step)
        for entry in recent
        if getattr(entry.step, "action", "") == "navigate_url"
    ]
    if len(navigate_sigs) >= 3 and len(set(navigate_sigs[-3:])) == 1:
        return (
            "LOOP DETECTED: You navigated to the same URL repeatedly. "
            "Re-observe the page and choose a different observed action."
        )

    if session.stale_page_turns >= 2:
        return (
            "STALL DETECTED: The page state is not changing. "
            "Take one decisive action that should change results "
            "(open a product, add to cart, or wait_for_user)."
        )

    return None
