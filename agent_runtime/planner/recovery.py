"""Planner empty/invalid response recovery nudges."""

from __future__ import annotations

from agent_runtime.state.run_state import RunState


def empty_plan_nudge(
    state: RunState,
    *,
    last_blocked: list[str] | None = None,
) -> str:
    phase = state.current_phase
    base = (
        "The previous planner response contained no executable action. "
        "Re-observe the CURRENT PAGE and select exactly ONE valid action "
        f"to advance CURRENT PHASE ({phase}). "
    )
    blocked_note = ""
    if last_blocked:
        blocked_note = f" Blocked proposals: {'; '.join(last_blocked[:4])}."

    if phase == "checkout":
        return (
            base
            + "Cart requirement is already verified. Click a checkout-capable control "
            "(see Checkout-capable controls in observation) using its elementId. "
            "Do NOT add products, search, or use header Sign in."
            + blocked_note
        )
    if phase == "search_results":
        return (
            base
            + "Use type/search on the search input with the user's query. "
            "Do NOT click product links or add to cart."
            + blocked_note
        )
    if phase == "cart_updated":
        return (
            base
            + "Add the requested product using an Add to cart control elementId."
            + blocked_note
        )
    return base + "Return one concrete click, type, or navigate action." + blocked_note
