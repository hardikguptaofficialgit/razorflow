"""Parse natural-language tasks into explicit TaskSpec + legacy ParsedTask."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from agent_runtime.task.spec import (
    COMPLETION_BY_INTENT,
    FORBIDDEN_BY_INTENT,
    TaskIntent,
    TaskSpec,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.search_query import extract_product_queries, extract_search_query  # noqa: E402


_CHECKOUT = re.compile(r"\b(?:proceed\s+to\s+)?checkout\b|\bcheck\s*out\b", re.I)
_VIEW_CART = re.compile(
    r"\b(?:view|open|see|go\s+to|show(?:\s+me)?)\s+(?:my\s+)?(?:cart|bag|basket)\b",
    re.I,
)
_ADD_CART = re.compile(
    r"\b(?:add|put|place)\b[^.]{0,80}\b(?:cart|bag|basket)\b|"
    r"\badd\s+(?:me\s+)?(?:some|a|an|the|\d+)?\b",
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


def _primary_entity(task: str) -> str:
    queries = extract_product_queries(task)
    if queries and queries[0]:
        return queries[0]
    return extract_search_query(task)


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


def _build_spec(
    *,
    raw: str,
    intent: TaskIntent,
    objective: str,
    entities: tuple[str, ...] = (),
    quantity: int = 1,
    budget_inr: float | None = None,
    prefer_best: bool = False,
    remove_target: str | None = None,
    requires_checkout: bool = False,
    actionable: bool = True,
    clarification_reason: str = "",
    remaining_items: tuple[str, ...] = (),
) -> TaskSpec:
    forbidden = FORBIDDEN_BY_INTENT.get(intent, frozenset())
    target = COMPLETION_BY_INTENT.get(intent, "")
    completion = (target,) if target else ()
    return TaskSpec(
        raw=raw,
        intent=intent,
        objective=objective,
        entities=entities,
        quantity=quantity,
        budget_inr=budget_inr,
        prefer_best=prefer_best,
        remove_target=remove_target,
        requires_checkout=requires_checkout,
        actionable=actionable,
        clarification_reason=clarification_reason,
        remaining_items=remaining_items or entities,
        forbidden_actions=forbidden,
        target_state=target,
        completion_conditions=completion,
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
    prefer_best = "best" in lowered or "cheapest" in lowered
    requires_checkout = bool(_CHECKOUT.search(raw))
    entities = _usable_entities(tuple(extract_product_queries(raw)))
    primary = entities[0] if entities else _primary_entity(raw)
    if not _entity_usable(primary):
        primary = ""

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

    remove_match = _REMOVE.search(raw)
    if remove_match:
        target = (remove_match.group(1) or "").strip() or None
        return _build_spec(
            raw=raw,
            intent="remove",
            objective=f"Remove {target or 'item'} from cart.",
            entities=entities,
            remove_target=target,
        )

    if _VIEW_CART.search(raw) and not _ADD_CART.search(raw):
        return _build_spec(
            raw=raw,
            intent="view_cart",
            objective="Open and show the shopping cart.",
            entities=(),
        )

    if requires_checkout:
        return _build_spec(
            raw=raw,
            intent="checkout",
            objective="Reach checkout with suitable items in cart.",
            entities=entities or (primary,) if primary else (),
            quantity=max(quantity, len(entities) or 1),
            budget_inr=budget,
            prefer_best=prefer_best,
            requires_checkout=True,
        )

    if _ADD_CART.search(raw) or (
        "add" in lowered and ("cart" in lowered or "bag" in lowered)
    ):
        qty = max(quantity, len(entities) or 1)
        return _build_spec(
            raw=raw,
            intent="add_to_cart",
            objective="Add suitable product(s) to the cart.",
            entities=entities or (primary,) if primary else (),
            quantity=qty,
            budget_inr=budget,
            prefer_best=prefer_best,
            remaining_items=entities if len(entities) >= 2 else (primary,) if primary else (),
        )

    if _BUY.search(raw):
        return _build_spec(
            raw=raw,
            intent="add_to_cart",
            objective="Find and add suitable product(s) to the cart (do not checkout).",
            entities=entities or (primary,) if primary else (),
            quantity=max(quantity, len(entities) or 1),
            budget_inr=budget,
            prefer_best=prefer_best,
            remaining_items=entities if len(entities) >= 2 else (primary,) if primary else (),
        )

    if _SEARCH.search(raw) or _WANT_NEED.search(raw) or budget is not None:
        intent: TaskIntent = "compare" if "compare" in lowered else "search"
        return _build_spec(
            raw=raw,
            intent=intent,
            objective="Find and display relevant products.",
            entities=entities or (primary,) if primary else (),
            budget_inr=budget,
            prefer_best=prefer_best,
        )

    return _build_spec(
        raw=raw,
        intent="search",
        objective="Find and display relevant products.",
        entities=entities or (primary,) if primary else (),
        budget_inr=budget,
        prefer_best=prefer_best,
    )


def spec_to_parsed(spec: TaskSpec):
    from agent_runtime.task.parser import ParsedTask

    return ParsedTask(
        raw=spec.raw,
        goal=spec.intent,  # type: ignore[arg-type]
        actionable=spec.actionable,
        clarification_reason=spec.clarification_reason,
        item_count=spec.quantity,
        product_hints=spec.entities,
        remove_target=spec.remove_target,
        budget_inr=spec.budget_inr,
        prefer_best=spec.prefer_best,
        requires_checkout=spec.requires_checkout,
    )
