"""Post-action verification."""

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
    if not success:
        return False
    if verified is False:
        return False
    if verified is True:
        return True

    if after is None:
        return False

    verification = action.verification
    if verification is None:
        return _default_verify(action, before, after)

    if verification.url_contains and verification.url_contains not in after.url:
        return False
    if verification.results_visible and not after.products:
        return False
    if verification.cart_count_increased:
        before_count = _cart_items(before)
        after_count = _cart_items(after)
        return after_count > before_count

    if before and verification.url_changed and before.signature() == after.signature():
        return False

    return True


def _cart_items(page: BrowserPage | None) -> int:
    if page is None:
        return 0
    return sum(line.quantity for line in page.cart_lines)


def _default_verify(
    action: AgentAction,
    before: BrowserPage | None,
    after: BrowserPage | None,
) -> bool:
    if after is None:
        return False
    if action.type == "navigate":
        url = str(action.parameters.get("url", ""))
        return bool(url) and url in after.url
    if action.type in {"search", "type"}:
        return bool(after.search_query or after.products)
    if action.type == "click":
        label = ""
        if action.target:
            label = (action.target.description or action.target.match_text or "").lower()
        if "add to cart" in label or "add" in label:
            return _cart_items(after) > _cart_items(before)
        if before and before.signature() != after.signature():
            return True
        return False
    if before and before.signature() != after.signature():
        return True
    return False


def apply_verified_progress(
    state: RunState,
    action: AgentAction,
    page: BrowserPage | None,
    *,
    ok: bool,
) -> None:
    if not ok:
        return
    state.verified_progress_count += 1
    if page is None:
        return

    if action.type in {"search", "type"}:
        state.milestones.add("verified_search")
        if page.search_query:
            state.memory.note_fact(f"Searched: {page.search_query}")
        elif "/search" in page.path:
            state.memory.note_fact("Navigated to search results")
        state.memory.note_completed("search")

    if action.type == "click":
        label = ""
        if action.target:
            label = (action.target.description or action.target.match_text or "").lower()
        if "add" in label and "cart" in label:
            state.milestones.add("verified_add_to_cart")
            state.memory.items_added += 1
            state.memory.note_completed("add_to_cart")
            state.memory.note_fact(f"Cart items: {_cart_items(page)}")
            if state.memory.remaining_items:
                state.memory.remaining_items.pop(0)
            elif state.parsed_task.product_hints and state.memory.items_added <= len(
                state.parsed_task.product_hints
            ):
                done = state.parsed_task.product_hints[state.memory.items_added - 1]
                state.memory.note_fact(f"Added: {done}")

    if "/cart" in page.path:
        state.milestones.add("reached_cart")
    if "/checkout" in page.path or "login_required" in page.signals:
        state.milestones.add("reached_checkout")
