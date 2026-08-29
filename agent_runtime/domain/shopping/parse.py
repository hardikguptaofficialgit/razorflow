"""Parse natural-language tasks into explicit TaskSpec + legacy ParsedTask."""

from __future__ import annotations

import re

from agent_runtime.task.entities import extract_entity_phrase, extract_entity_phrases
from agent_runtime.domain.shopping.spec import (
    COMPLETION_BY_PHASE,
    GoalPhase,
    TaskIntent,
    forbidden_for_phase,
    phase_for_intent,
)
from agent_runtime.domain.shopping.helpers import pack_shopping_metadata
from agent_runtime.task.spec import TaskSpec

_CHECKOUT = re.compile(r"\b(?:proceed\s+to\s+)?checkout\b|\bcheck\s*out\b", re.I)
_CHECKOUT_NEGATED = re.compile(
    r"(?:not|don't|dont|do\s+not|no|without|skip|avoid)[^.!?]{0,40}"
    r"(?:checkout|check\s*out)\b",
    re.I,
)
_VIEW_CART = re.compile(
    r"\b(?:view|open|see|go\s+to|show(?:\s+me)?)\s+(?:my\s+)?(?:cart|bag|basket)\b",
    re.I,
)
_ADD_TO_CART = re.compile(
    r"\b(?:add|put|place)\b[^.]{0,80}\b(?:cart|bag|basket)\b",
    re.I,
)
_INSPECT_ONLY = re.compile(
    r"\b(?:inspect|examine)\b|"
    r"\bchoose\s+(?:the\s+)?best\b|"
    r"\bpick\s+(?:the\s+)?best\b|"
    r"\bshow\s+me\s+(?:the\s+)?best\b",
    re.I,
)
_COMPARE_ADD_BEST = re.compile(
    r"\bcompare\b.+\badd\b.+\b(?:best|one)\b|"
    r"\badd\b.+\b(?:best)\b[^.]{0,40}\b(?:cart|bag|basket)\b",
    re.I,
)
_SEARCH = re.compile(
    r"\b(?:find|search|look\s+for|show\s+me|browse|explore|compare|cheapest|best)\b",
    re.I,
)
_BUY = re.compile(r"\b(?:buy|purchase|order)\b", re.I)
_WANT_NEED = re.compile(r"\b(?:i\s+want|i\s+need|get\s+me|grab|pick)\b", re.I)
_REMOVE = re.compile(
    r"\b(?:remove|delete)\b[^.]{0,80}\b(?:from\s+(?:my\s+)?cart|cart)\b|"
    r"\bremove\s+(?:the\s+)?(.+?)\s+from\b",
    re.I,
)
_CLEAR_CART = re.compile(
    r"\b(?:clear|empty|remove\s+all|delete\s+all)\b[^.]{0,80}"
    r"\b(?:my\s+)?(?:cart|bag|basket)\b",
    re.I,
)
_OPEN_CART = re.compile(
    r"\b(?:open|view|see|go\s+to|show(?:\s+me)?)\s+(?:my\s+)?(?:cart|bag|basket)\b",
    re.I,
)
_PRODUCT_DETAILS = re.compile(
    r"\b(?:show\s+(?:me\s+)?(?:the\s+)?best(?:\s+one)?|"
    r"open\s+(?:the\s+)?(?:product|details?)|"
    r"view\s+(?:the\s+)?(?:product|details?)|"
    r"pick\s+(?:the\s+)?best)\b",
    re.I,
)
_FIND_AND_ADD = re.compile(
    r"\bfind\b.+\band\s+add\b",
    re.I,
)
_ON_THIS_PAGE = re.compile(r"\bon\s+(?:this|the)\s+page\b", re.I)
_CLICK_UI = re.compile(r"^\s*click\b", re.I)
_SUBMIT_ORDER = re.compile(r"\bsubmit\s+order\b", re.I)
_GIBBERISH = re.compile(r"^[a-z]{1,4}$|^(?:wdwd|asdf|test|hello|hi)$", re.I)
_VAGUE = re.compile(r"\b(something|anything|stuff|whatever)\b", re.I)
_VAGUE_ENTITY = frozenset({"see", "show", "cart", "show cart", "something", "anything"})
_QTY = re.compile(r"\badd\s+(\d+)\b", re.I)
_BUDGET = re.compile(
    r"(?:under|below|less\s+than|max(?:imum)?|upto|up\s+to)\s*"
    r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:k|K)?",
    re.I,
)


def _extract_budget(text: str) -> float | None:
    match = _BUDGET.search(text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    if "k" in text[match.start() : match.end() + 2].lower():
        value *= 1000
    return value


def _entity_usable(entity: str) -> bool:
    cleaned = entity.strip().lower()
    if len(cleaned) < 2:
        return False
    if cleaned in _VAGUE_ENTITY:
        return False
    if _VAGUE.search(cleaned):
        return False
    return True


def _usable_entities(entities: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(entity for entity in entities if _entity_usable(entity))


def _extract_remove_target(raw: str) -> str | None:
    match = re.search(r"\bremove\s+(?:the\s+)?(.+?)\s+from\b", raw, re.I)
    if not match:
        return None
    target = (match.group(1) or "").strip()
    return target or None


def _task_allows_add(raw: str) -> bool:
    if _ADD_TO_CART.search(raw):
        return True
    if _FIND_AND_ADD.search(raw):
        return True
    if re.search(r"\band\s+add\b", raw, re.I):
        return True
    return False


def _resolve_search_phase(raw: str, lowered: str) -> GoalPhase:
    if _FIND_AND_ADD.search(raw) or (_SEARCH.search(raw) and _ADD_TO_CART.search(raw)):
        return "cart_updated"
    if _PRODUCT_DETAILS.search(raw):
        return "product_details"
    if _INSPECT_ONLY.search(raw) and not _task_allows_add(raw):
        return "search_results"
    return "search_results"


def _build_spec(
    *,
    raw: str,
    intent: TaskIntent,
    objective: str,
    target_phase: GoalPhase | None = None,
    entities: tuple[str, ...] = (),
    quantity: int = 1,
    budget_inr: float | None = None,
    prefer_best: bool = False,
    prefer_cheapest: bool = False,
    remove_target: str | None = None,
    requires_checkout: bool = False,
    allows_add_to_cart: bool = True,
    actionable: bool = True,
    clarification_reason: str = "",
    remaining_items: tuple[str, ...] = (),
    goal_phases: tuple[GoalPhase, ...] = (),
    clear_cart: bool = False,
) -> TaskSpec:
    phases = goal_phases if goal_phases else ((target_phase or phase_for_intent(intent)),)
    phase = target_phase or phases[0]
    forbidden = forbidden_for_phase(phase)
    target = COMPLETION_BY_PHASE.get(phase, "")
    completion = (target,) if target else ()
    return TaskSpec(
        raw=raw,
        goal=intent,
        objective=objective,
        target_phase=phase,
        entities=() if clear_cart else entities,
        quantity=quantity,
        actionable=actionable,
        clarification_reason=clarification_reason,
        remaining_items=remaining_items or (() if clear_cart else entities),
        goal_phases=phases,
        forbidden_actions=forbidden,
        target_state=target,
        completion_conditions=completion,
        metadata=pack_shopping_metadata(
            intent=intent,
            allows_add_to_cart=allows_add_to_cart,
            requires_checkout=requires_checkout,
            prefer_best=prefer_best,
            prefer_cheapest=prefer_cheapest,
            budget_inr=budget_inr,
            remove_target=remove_target,
            clear_cart=clear_cart,
        ),
    )


def parse_task_spec(task: str) -> TaskSpec:
    raw = task.strip()
    if not raw or len(raw) < 3 or _GIBBERISH.match(raw):
        return _build_spec(
            raw=raw,
            intent="unknown",
            objective="Clarify what the user wants.",
            actionable=False,
            clarification_reason="Please describe what you want to search, add, or buy.",
        )

    lowered = raw.lower()
    budget = _extract_budget(raw)
    prefer_cheapest = (
        "cheapest" in lowered
        or "best price" in lowered
        or "lowest price" in lowered
        or "at the best price" in lowered
    )
    prefer_best = prefer_cheapest or "best" in lowered
    checkout_negated = bool(_CHECKOUT_NEGATED.search(raw))
    requires_checkout = bool(_CHECKOUT.search(raw)) and not checkout_negated
    entities = _usable_entities(extract_entity_phrases(raw))
    primary = entities[0] if entities else extract_entity_phrase(raw)
    if not _entity_usable(primary):
        primary = ""

    if checkout_negated and not (
        _ADD_TO_CART.search(raw)
        or _SEARCH.search(raw)
        or _BUY.search(raw)
        or _VIEW_CART.search(raw)
        or _REMOVE.search(raw)
    ):
        return _build_spec(
            raw=raw,
            intent="unknown",
            objective="Do not proceed to checkout.",
            actionable=False,
            clarification_reason="Okay — I will not proceed to checkout.",
        )

    if _VAGUE.search(raw) and not entities:
        return _build_spec(
            raw=raw,
            intent="unknown",
            objective="Clarify the product or category.",
            actionable=False,
            clarification_reason="Please name what you want (e.g. snacks, earbuds, cooker).",
        )

    qty_match = _QTY.search(raw)
    quantity = int(qty_match.group(1)) if qty_match else 1

    remove_target = _extract_remove_target(raw)
    clear_cart = bool(_CLEAR_CART.search(raw))
    if clear_cart or _REMOVE.search(raw) or remove_target:
        return _build_spec(
            raw=raw,
            intent="remove",
            objective=(
                "Clear all items from the cart."
                if clear_cart
                else f"Remove {remove_target or 'item'} from cart."
            ),
            entities=() if clear_cart else entities,
            remove_target="all" if clear_cart else remove_target,
            clear_cart=clear_cart,
        )

    if _VIEW_CART.search(raw) and not _ADD_TO_CART.search(raw):
        return _build_spec(
            raw=raw,
            intent="view_cart",
            objective="Open and show the shopping cart.",
            entities=(),
        )

    if lowered.strip() in {"checkout", "check out", "proceed to checkout"}:
        return _build_spec(
            raw=raw,
            intent="checkout",
            objective="Reach checkout.",
            requires_checkout=True,
        )

    if requires_checkout:
        add_part = (
            _ADD_TO_CART.search(raw)
            or _BUY.search(raw)
            or bool(entities)
            or bool(primary)
        )
        if add_part and not _VIEW_CART.search(raw):
            qty = max(quantity, len(entities) or 1)
            return _build_spec(
                raw=raw,
                intent="checkout",
                objective="Add suitable items to cart, then reach checkout.",
                target_phase="cart_updated",
                goal_phases=("cart_updated", "checkout_reached"),
                entities=entities or ((primary,) if primary else ()),
                quantity=qty,
                budget_inr=budget,
                prefer_best=prefer_best,
                prefer_cheapest=prefer_cheapest,
                requires_checkout=True,
                allows_add_to_cart=True,
                remaining_items=entities if len(entities) >= 2 else ((primary,) if primary else ()),
            )
        return _build_spec(
            raw=raw,
            intent="checkout",
            objective="Reach checkout with suitable items in cart.",
            goal_phases=("checkout_reached",),
            entities=entities or ((primary,) if primary else ()),
            quantity=max(quantity, len(entities) or 1),
            budget_inr=budget,
            prefer_best=prefer_best,
            prefer_cheapest=prefer_cheapest,
            requires_checkout=True,
        )

    if _ADD_TO_CART.search(raw) or (
        "add" in lowered and ("cart" in lowered or "bag" in lowered)
    ):
        qty = max(quantity, len(entities) or 1)
        entity_tuple = entities or ((primary,) if primary else ())
        goal_phases: tuple[GoalPhase, ...] = ("cart_updated",)
        target_phase: GoalPhase = "cart_updated"
        objective = "Add suitable product(s) to the cart."
        if _ON_THIS_PAGE.search(raw):
            objective = "Find the product on the current page and add it to the cart."
        if _COMPARE_ADD_BEST.search(raw) and "compare" in lowered:
            qty = 1
            goal_phases = ("search_results", "cart_updated")
            target_phase = "search_results"
            objective = (
                "Search and compare results, then add exactly one best match to the cart."
            )
        return _build_spec(
            raw=raw,
            intent="add_to_cart",
            objective=objective,
            target_phase=target_phase,
            goal_phases=goal_phases,
            entities=entity_tuple,
            quantity=qty,
            budget_inr=budget,
            prefer_best=prefer_best,
            prefer_cheapest=prefer_cheapest,
            allows_add_to_cart=True,
            remaining_items=entity_tuple,
        )

    if (
        re.search(r"\badd\b", raw, re.I)
        and not _VIEW_CART.search(raw)
        and not re.match(r"^\s*find\b", lowered)
        and not (_INSPECT_ONLY.search(raw) and not _ADD_TO_CART.search(raw))
    ):
        qty = max(quantity, len(entities) or 1)
        return _build_spec(
            raw=raw,
            intent="add_to_cart",
            objective="Add suitable product(s) to the cart.",
            entities=entities or ((primary,) if primary else ()),
            quantity=qty,
            budget_inr=budget,
            prefer_best=prefer_best,
            prefer_cheapest=prefer_cheapest,
            allows_add_to_cart=True,
            remaining_items=entities if len(entities) >= 2 else ((primary,) if primary else ()),
        )

    if _CLICK_UI.search(raw) and not _SEARCH.search(raw):
        return _build_spec(
            raw=raw,
            intent="search",
            objective="Click the requested UI control on the current page.",
            target_phase="search_results",
            entities=(),
            allows_add_to_cart=False,
        )

    buy_me = re.search(r"\bbuy\s+me\b", raw, re.I)
    autonomous_buy = buy_me and (prefer_best or prefer_cheapest)
    if _BUY.search(raw) and autonomous_buy and not _SUBMIT_ORDER.search(raw):
        entity_tuple = entities or ((primary,) if primary else ())
        phases: tuple[GoalPhase, ...]
        if prefer_best or prefer_cheapest:
            phases = ("search_results", "cart_updated", "checkout_reached")
            objective = (
                "Research visible options, compare price and quality, "
                "add the best match, then reach checkout."
            )
            target: GoalPhase = "search_results"
        else:
            phases = ("cart_updated", "checkout_reached")
            objective = "Add suitable product(s) to cart and reach checkout."
            target = "cart_updated"
        return _build_spec(
            raw=raw,
            intent="purchase",
            objective=objective,
            target_phase=target,
            goal_phases=phases,
            entities=entity_tuple,
            quantity=max(quantity, len(entity_tuple) or 1),
            budget_inr=budget,
            prefer_best=prefer_best,
            prefer_cheapest=prefer_cheapest,
            requires_checkout=True,
            allows_add_to_cart=True,
            remaining_items=entity_tuple,
        )

    if _BUY.search(raw) and not _SEARCH.search(raw) and not _SUBMIT_ORDER.search(raw):
        buy_intent: TaskIntent = (
            "add_to_cart" if re.search(r"\bbuy\s+me\b", raw, re.I) else "purchase"
        )
        return _build_spec(
            raw=raw,
            intent=buy_intent,
            objective=(
                "Add suitable product(s) to the cart."
                if buy_intent == "add_to_cart"
                else "Complete purchase flow per policy."
            ),
            target_phase="cart_updated" if buy_intent == "add_to_cart" else "purchase_reached",
            entities=entities or ((primary,) if primary else ()),
            quantity=max(quantity, len(entities) or 1),
            budget_inr=budget,
            prefer_best=prefer_best,
            prefer_cheapest=prefer_cheapest,
            remaining_items=entities if len(entities) >= 2 else ((primary,) if primary else ()),
        )

    if _SEARCH.search(raw) or _WANT_NEED.search(raw) or budget is not None:
        if _ON_THIS_PAGE.search(raw) and _ADD_TO_CART.search(raw):
            entity_tuple = entities or ((primary,) if primary else ())
            return _build_spec(
                raw=raw,
                intent="add_to_cart",
                objective="Find the product on the current page and add it to the cart.",
                target_phase="cart_updated",
                goal_phases=("cart_updated",),
                entities=entity_tuple,
                quantity=max(quantity, len(entity_tuple) or 1),
                budget_inr=budget,
                prefer_best=prefer_best,
                prefer_cheapest=prefer_cheapest,
                allows_add_to_cart=True,
                remaining_items=entity_tuple,
            )
        intent: TaskIntent = "compare" if "compare" in lowered else "search"
        phase = _resolve_search_phase(raw, lowered)
        if phase == "cart_updated":
            qty = max(quantity, len(entities) or 1)
            if _COMPARE_ADD_BEST.search(raw):
                qty = 1
            return _build_spec(
                raw=raw,
                intent="add_to_cart",
                objective="Find and add suitable product(s) to the cart.",
                target_phase="cart_updated",
                entities=entities or ((primary,) if primary else ()),
                quantity=qty,
                budget_inr=budget,
                prefer_best=prefer_best,
                prefer_cheapest=prefer_cheapest,
                allows_add_to_cart=True,
                remaining_items=entities if len(entities) >= 2 else ((primary,) if primary else ()),
            )
        allows_add = _task_allows_add(raw)
        inspect_objective = (
            "Inspect search results and identify the best match — do not add to cart."
            if _INSPECT_ONLY.search(raw) and not allows_add
            else (
                "Open the best matching product details."
                if phase == "product_details"
                else "Find and display relevant search results only."
            )
        )
        return _build_spec(
            raw=raw,
            intent=intent,
            objective=inspect_objective,
            target_phase=phase,
            entities=entities or ((primary,) if primary else ()),
            budget_inr=budget,
            prefer_best=prefer_best,
            prefer_cheapest=prefer_cheapest,
            allows_add_to_cart=allows_add,
        )

    return _build_spec(
        raw=raw,
        intent="search",
        objective="Find and display relevant search results only.",
        target_phase="search_results",
        entities=entities or ((primary,) if primary else ()),
        budget_inr=budget,
        prefer_best=prefer_best,
        prefer_cheapest=prefer_cheapest,
    )


def spec_to_parsed(spec: TaskSpec):
    from agent_runtime.task.parser import ParsedTask

    return ParsedTask(
        raw=spec.raw,
        goal=spec.goal,  # type: ignore[arg-type]
        actionable=spec.actionable,
        clarification_reason=spec.clarification_reason,
        item_count=spec.quantity,
        product_hints=spec.entities,
        remove_target=spec.metadata.get("remove_target"),
        budget_inr=spec.metadata.get("budget_inr"),
        prefer_best=bool(spec.metadata.get("prefer_best", False)),
        requires_checkout=bool(spec.metadata.get("requires_checkout", False)),
    )
