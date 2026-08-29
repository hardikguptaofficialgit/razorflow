"""Post-action verification."""

from __future__ import annotations

from agent_runtime.executor.actions import AgentAction
from agent_runtime.domain.shopping.action_gate import _is_add_to_cart_action
from agent_runtime.domain.shopping.action_gate import _is_checkout_action
from agent_runtime.domain.shopping.checkout_flow import is_checkout_flow_page
from agent_runtime.domain.shopping.helpers import goal_item_phrase, multi_distinct_item_goal
from agent_runtime.domain.shopping.page_semantics import is_cart_page, is_search_results_page
from agent_runtime.domain.shopping.search_state import entity_search_tokens, search_entity
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.state.run_state import RunState


def _word_tokens(text: str) -> tuple[str, ...]:
    import re

    return tuple(re.findall(r"[a-z0-9]+", text.lower()))


def _matches_requested_item(title: str, requested: str) -> bool:
    """Use observed product names, not an LLM-provided button label, for cart credit."""
    for candidate in (requested, goal_item_phrase(requested)):
        title_tokens = set(title.lower().split())
        requested_tokens = set(candidate.lower().split())
        if title_tokens and requested_tokens and title_tokens & requested_tokens:
            return True
        tokens = entity_search_tokens(candidate)
        if tokens:
            title_words = _word_tokens(title)
            overlap = sum(
                1
                for token in tokens
                if any(token in word or word in token for word in title_words)
            )
            if overlap >= max(1, (len(tokens) + 1) // 2):
                return True
    return False


def _add_click_label(action: AgentAction) -> str:
    if action.type != "click" or action.target is None:
        return ""
    return (action.target.description or action.target.match_text or "").lower()


def _is_add_to_cart_click(action: AgentAction) -> bool:
    return _is_add_to_cart_action(action)


def _current_add_target(state: RunState) -> str:
    if state.memory.remaining_items:
        return state.memory.remaining_items[0]
    if state.memory.current_target:
        return state.memory.current_target
    return search_entity(state)


def _product_for_target(
    target_id: str | None,
    *pages: BrowserPage | None,
) -> str | None:
    if not target_id:
        return None
    for page in pages:
        if page is None:
            continue
        for product in page.products:
            if product.add_element_id == target_id:
                return product.title
    return None


def _add_targets_wrong_product(
    state: RunState,
    action: AgentAction,
    *,
    before: BrowserPage | None,
    after: BrowserPage | None,
) -> bool:
    if not _is_add_to_cart_click(action):
        return False
    target = _current_add_target(state)
    if not target:
        return False
    added_title = _product_for_target(
        action.target.element_id if action.target else None,
        before,
        after,
    )
    if added_title and not _matches_requested_item(added_title, target):
        return True
    if added_title and state.memory.verified_items:
        if multi_distinct_item_goal(state):
            for verified in state.memory.verified_items:
                if _matches_requested_item(added_title, verified) and not _matches_requested_item(
                    verified, target
                ):
                    return True
    return False


def verify_action_result(
    state: RunState,
    action: AgentAction,
    *,
    success: bool,
    verified: bool | None,
    before: BrowserPage | None,
    after: BrowserPage | None,
) -> bool:
    if after is None:
        return False

    if not success or verified is False:
        if _default_verify(state, action, before, after):
            return True
    if not success:
        return False
    if verified is True:
        if action.type == "scroll" and not _default_verify(state, action, before, after):
            return False
        if _is_checkout_action(action) and not is_checkout_flow_page(after):
            return False
        return True

    verification = action.verification
    if verification is None:
        ok = _default_verify(state, action, before, after)
        if ok and _add_targets_wrong_product(state, action, before=before, after=after):
            return False
        return ok

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
    state: RunState,
    action: AgentAction,
    before: BrowserPage | None,
    after: BrowserPage | None,
) -> bool:
    if after is None:
        return False
    if action.type == "navigate":
        url = str(action.parameters.get("url", ""))
        return bool(url) and url in after.url
    is_search_action = action.type == "search" or (
        action.type == "type"
        and action.target is not None
        and (
            action.target.role == "search"
            or "search" in (
                f"{action.reason} "
                f"{action.target.description} "
                f"{action.target.match_text}"
            ).lower()
        )
    )
    if is_search_action:
        query = str(action.parameters.get("text", "") or action.parameters.get("query", "")).lower()
        if query and query in after.url.lower():
            return True
        return bool(
            after.search_query or after.products or is_search_results_page(after)
        )
    if action.type == "type":
        text = str(action.parameters.get("text", "") or action.parameters.get("query", "")).strip()
        if not text:
            return False
        target = action.target
        for element in after.elements:
            if target and target.element_id and element.element_id != target.element_id:
                continue
            if target and target.role and element.role != target.role:
                continue
            labels = " ".join(
                (element.text, element.placeholder, element.aria_label)
            ).lower()
            if target and target.match_text and target.match_text.lower() not in labels:
                continue
            if element.value.strip() == text:
                return True
        return False
    if action.type == "scroll":
        if before is None:
            return False
        if before.url != after.url:
            return True
        from agent_runtime.recovery.loop_detector import page_fingerprint

        if page_fingerprint(before) != page_fingerprint(after):
            return True
        before_products = {p.title for p in before.products}
        after_products = {p.title for p in after.products}
        if after_products - before_products:
            return True
        before_ids = {el.element_id for el in before.elements[:40]}
        after_ids = {el.element_id for el in after.elements[:40]}
        if after_ids - before_ids:
            return True
        return before.signature() != after.signature()
    if action.type == "wait":
        return True
    if action.type == "go_back":
        return before is not None and before.url != after.url
    if action.type == "click":
        label = _add_click_label(action)
        if "remove" in label:
            return _cart_items(after) < _cart_items(before)
        if _is_add_to_cart_click(action):
            if _cart_items(after) <= _cart_items(before):
                return False
            if _add_targets_wrong_product(state, action, before=before, after=after):
                return False
            return True
        if _cart_items(after) > _cart_items(before):
            return True
        if _is_checkout_action(action):
            return is_checkout_flow_page(after)
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
    before: BrowserPage | None = None,
) -> bool:
    """Apply verified progress. Returns True when goal-relevant state advanced."""
    if not ok:
        return False
    if action.type == "scroll" and "verified_search" not in state.milestones:
        spec = state.task_spec
        intent = spec.intent if spec else state.parsed_task.goal
        if intent in {"search", "compare"} and page and not is_search_results_page(page):
            return False
    state.verified_progress_count += 1
    if page is None:
        return True

    if action.type == "search" or (
        action.type == "type"
        and action.target is not None
        and (
            action.target.role == "search"
            or "search" in (
                f"{action.reason} "
                f"{action.target.description} "
                f"{action.target.match_text}"
            ).lower()
        )
    ):
        entity = search_entity(state)
        if entity and page and entity_in_search(page, entity):
            state.milestones.add("verified_search")
        elif page and is_search_results_page(page):
            state.milestones.add("verified_search")
        if page.search_query:
            state.memory.note_fact(f"Searched: {page.search_query}")
        elif page and is_search_results_page(page):
            state.memory.note_fact("Navigated to search results")
        state.memory.note_completed("search")

    if action.type == "click":
        label = _add_click_label(action)
        if _is_add_to_cart_click(action):
            added_title = _product_for_target(
                action.target.element_id if action.target else None, before, page
            )
            requested_items = state.memory.remaining_items or list(
                state.parsed_task.product_hints
            )
            if requested_items and (
                not added_title
                or not any(
                    _matches_requested_item(added_title, item)
                    for item in requested_items
                )
            ):
                if added_title:
                    state.memory.note_fact(
                        f"Ignored unrelated cart addition: {added_title}"
                    )
                return False
            state.milestones.add("verified_add_to_cart")
            state.memory.items_added += 1
            state.memory.note_completed("add_to_cart")
            state.memory.note_fact(f"Cart items: {_cart_items(page)}")
            if action.target:
                found_item = False
                for observed_page in (page, before):
                    if observed_page is None:
                        continue
                    for product in observed_page.products:
                        target_matches = (
                            product.add_element_id == action.target.element_id
                            or (
                                product.title
                                and product.title.lower() in label
                            )
                        )
                        if (
                            target_matches
                            and product.title not in state.memory.verified_items
                        ):
                            state.memory.verified_items.append(product.title)
                            found_item = True
                            break
                    if found_item:
                        break
            if added_title and added_title not in state.memory.verified_items:
                state.memory.verified_items.append(added_title)
            if multi_distinct_item_goal(state) and state.memory.remaining_items:
                state.memory.remaining_items.pop(0)
            elif (
                not multi_distinct_item_goal(state)
                and state.memory.items_added >= state.parsed_task.item_count
            ):
                state.memory.remaining_items = []
            elif state.memory.remaining_items:
                pass
            elif state.parsed_task.product_hints and state.memory.items_added <= len(
                state.parsed_task.product_hints
            ):
                done = state.parsed_task.product_hints[state.memory.items_added - 1]
                state.memory.note_fact(f"Added: {done}")
        if "remove" in label:
            state.milestones.add("verified_remove")
            state.memory.note_completed("remove_from_cart")

    if page and is_cart_page(page):
        state.milestones.add("reached_cart")
    if page and is_checkout_flow_page(page):
        state.milestones.add("reached_checkout")
    return True
