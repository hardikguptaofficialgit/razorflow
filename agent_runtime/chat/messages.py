"""User-facing chat copy for the shopping agent."""

from __future__ import annotations

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState


def clarification_message(_task: str = "") -> str:
    return (
        "I'd love to help you shop. What are you looking for — shampoo, snacks, "
        "earbuds, or something else? You can also add a budget, like "
        "\"wireless earbuds under ₹5000\"."
    )


def planning_ack(task: str) -> str:
    trimmed = task.strip()
    if len(trimmed) > 80:
        trimmed = f"{trimmed[:77]}…"
    return f"Got it — I'll help with: {trimmed}"


def completion_message(state: RunState, page: BrowserPage | None) -> str:
    goal = state.parsed_task.goal
    hints = state.parsed_task.product_hints

    if goal == "add_to_cart":
        if hints:
            label = hints[0] if len(hints) == 1 else f"{len(hints)} items"
            return f"All set — I added {label} to your cart. Want checkout or anything else?"
        return "Done — your item is in the cart. Need anything else?"

    if goal == "search":
        query = page.search_query if page else ""
        if query:
            return f"Here are results for “{query}”. Tell me which one to pick or refine the search."
        return "I pulled up matching products. Which one should I go with?"

    if goal in {"checkout", "purchase"}:
        return "You're at checkout. Sign in if prompted, or tell me if you want to change anything."

    if goal == "view_cart":
        return "Your cart is open. Want to add more, remove something, or head to checkout?"

    if goal == "remove":
        target = state.parsed_task.remove_target or "that item"
        return f"Removed {target} from your cart. Anything else?"

    return "Task completed. What should we do next?"
