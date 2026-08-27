"""Sync task memory from current browser observation (goal-driven, site-agnostic)."""

from __future__ import annotations

from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState


def _cart_count(page: BrowserPage) -> int:
    return sum(line.quantity for line in page.cart_lines)


def sync_memory_from_observation(state: RunState, page: BrowserPage | None) -> None:
    if page is None:
        return

    memory = state.memory
    memory.current_page = page
    memory.current_url = page.url

    if page.products:
        memory.note_fact(f"{len(page.products)} product listing(s) visible")
    if page.cart_lines:
        memory.note_fact(f"Cart has {len(page.cart_lines)} line(s), qty={_cart_count(page)}")
    if page.search_query:
        memory.note_fact(f"Active search query: {page.search_query}")
    if "login_required" in page.signals:
        memory.note_fact("Login or auth gate detected on page")
    if "checkout_page" in page.signals:
        memory.note_fact("Checkout page detected")

    spec = state.task_spec
    intent = spec.intent if spec else state.parsed_task.goal
    cart_count = _cart_count(page)

    if not memory.remaining_items and spec and spec.remaining_items:
        memory.remaining_items = list(spec.remaining_items)

    if intent == "checkout":
        add_needed = state.parsed_task.item_count
        if cart_count >= add_needed or memory.items_added >= add_needed:
            memory.remaining_work = ["Navigate to checkout and verify checkout page or login gate"]
        else:
            if memory.remaining_items:
                memory.remaining_work = [f"Add: {item}" for item in memory.remaining_items]
                memory.remaining_work.append("Then proceed to checkout")
            else:
                memory.remaining_work = [
                    f"Find and add qualifying product(s) ({add_needed} needed)",
                    "Then proceed to checkout",
                ]

    elif intent == "add_to_cart":
        target = state.parsed_task.item_count
        if memory.items_added >= target or cart_count >= target:
            memory.remaining_work = ["Goal satisfied — verify cart and stop"]
            memory.remaining_items = []
        elif memory.remaining_items:
            memory.remaining_work = [f"Add: {item}" for item in memory.remaining_items]
            memory.current_target = memory.remaining_items[0]
        elif state.parsed_task.product_hints:
            memory.remaining_work = [
                f"Add: {hint}" for hint in state.parsed_task.product_hints
            ]
            memory.current_target = state.parsed_task.product_hints[0]
        else:
            memory.remaining_work = [f"Add {target} suitable item(s) to cart"]

    elif intent in {"search", "compare"}:
        if page.products or page.search_query or "/search" in page.path:
            memory.remaining_work = ["Verify relevant results are visible, then stop"]
        else:
            memory.remaining_work = ["Search and display relevant products"]

    elif intent == "view_cart":
        if "/cart" in page.path:
            memory.remaining_work = ["Cart is open — goal satisfied"]
        else:
            memory.remaining_work = ["Open cart page"]

    elif intent == "remove":
        target = state.parsed_task.remove_target or "item"
        memory.remaining_work = [f"Remove {target} from cart"]

    elif intent == "purchase":
        if "checkout_page" in page.signals or "login_required" in page.signals:
            memory.remaining_work = ["Complete purchase or hand off for login/payment"]
        elif cart_count > 0:
            memory.remaining_work = ["Proceed to checkout/payment"]
        else:
            memory.remaining_work = ["Select product and reach checkout"]
