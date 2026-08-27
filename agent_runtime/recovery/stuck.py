"""Detect stuck loops and repeated failures."""

from __future__ import annotations

from agent_runtime.planner.planner import action_signature
from agent_runtime.state.run_state import RunState


def detect_stuck(state: RunState) -> str | None:
    history = state.action_history
    if len(history) < 2:
        return None

    # Checkout goal: block redundant add-to-cart spam (not cart/checkout navigation)
    if state.parsed_task.goal == "checkout" and "ADD_PHASE_COMPLETE" in " ".join(
        state.memory.constraints
    ):
        last_click = history[-1]
        label = ""
        if last_click.action.target:
            label = (
                (last_click.action.target.description or "")
                + (last_click.action.target.match_text or "")
            ).lower()
        if last_click.action.type == "click" and "add" in label and last_click.verified:
            state.blocked_signatures.add(last_click.signature)
            return (
                "Add phase is complete. Cart already has items. "
                "Do NOT add more products. Use cart or checkout navigation controls."
            )

    last = history[-1]
    if not last.success or last.verified is False:
        repeats = sum(
            1
            for entry in history[-4:]
            if entry.signature == last.signature
        )
        if repeats >= 2:
            state.blocked_signatures.add(last.signature)
            return (
                f"Action '{last.signature}' was attempted {repeats} times without "
                "verified progress. Do not repeat it. Re-observe and choose a new strategy."
            )

    signatures = [entry.signature for entry in history[-6:] if entry.signature]
    if len(signatures) >= 4 and len(set(signatures)) <= 2:
        return (
            "The agent is oscillating between the same actions. "
            "Try a different approach — navigate, scroll, or pick another element."
        )

    if len(history) >= 3:
        urls = [entry.page_url for entry in history[-3:]]
        if len(set(urls)) == 1 and not history[-1].success:
            return (
                "Multiple failures on the same page. Inspect alternative elements or "
                "use search/navigation before clicking again."
            )

    return None


def record_action(
    state: RunState,
    *,
    action,
    page_url: str,
    success: bool,
    verified: bool | None,
    error: str | None,
    state_before: str,
    state_after: str,
    duration_ms: int = 0,
) -> None:
    from agent_runtime.state.run_state import ActionRecord

    sig = action_signature(action)
    state.action_history.append(
        ActionRecord(
            step=state.step,
            action=action,
            page_url=page_url,
            success=success,
            verified=verified,
            error=error,
            state_before=state_before,
            state_after=state_after,
            signature=sig,
            duration_ms=duration_ms,
        )
    )
    if not success or verified is False:
        state.consecutive_failures += 1
        state.memory.note_failure(
            f"{action.type} on {page_url}: {error or 'no verified change'}"
        )
    else:
        state.consecutive_failures = 0
