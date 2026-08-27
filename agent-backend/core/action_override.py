"""Deterministic action overrides for Browser Use AgentOutput (index-based clicks)."""

from __future__ import annotations

import logging
from typing import Any

from browser_use.agent.views import AgentOutput

from core.product_compare import NormalizedProduct

logger = logging.getLogger(__name__)


def _action_names(agent_output: AgentOutput) -> list[str]:
    names: list[str] = []
    for action in agent_output.action or []:
        dumped = action.model_dump(exclude_unset=True)
        names.extend(str(key) for key in dumped.keys())
    return names


def _click_index(agent_output: AgentOutput) -> int | None:
    for action in agent_output.action or []:
        dumped = action.model_dump(exclude_unset=True)
        if "click" not in dumped:
            continue
        idx = action.get_index()
        if idx is not None:
            return idx
    return None


def should_skip_force(agent_output: AgentOutput) -> bool:
    """Do not override handoff / payment / completion / navigation actions."""
    names = {name.lower() for name in _action_names(agent_output)}
    blocked = {
        "request_user_handoff",
        "propose_checkout_payment",
        "mark_shopping_complete",
        "done",
        "navigate",
        "go_to_url",
        "search",
        "search_google",
        "input",
        "input_text",
        "send_keys",
        "wait",
    }
    return bool(names & blocked)


def force_click_add_to_cart(
    agent_output: AgentOutput,
    winner: NormalizedProduct,
) -> int | None:
    """
    Mutate agent_output.action in-place to click the winner's Add to cart index.

    Returns the forced index if mutated, else None.
    browser-use executes last_model_output after the step callback, so mutating
    here is how we inject deterministic index clicks without a second LLM call.
    """
    index = winner.add_to_cart_element_index
    if index is None or index < 1:
        return None
    if should_skip_force(agent_output):
        return None

    current = _click_index(agent_output)
    if current == index:
        return None

    if not agent_output.action:
        logger.warning("Cannot force click: empty action list")
        return None

    ActionCls = type(agent_output.action[0])
    try:
        forced = ActionCls.model_validate({"click": {"index": index}})
    except Exception as error:
        logger.warning("Failed to build forced click action index=%s: %s", index, error)
        return None

    previous = _action_names(agent_output)
    agent_output.action = [forced]
    logger.info(
        "Forced Add-to-cart click index=%s title=%r (replaced actions=%s)",
        index,
        winner.title[:48],
        previous,
    )
    return index


def summarize_actions(agent_output: AgentOutput) -> str:
    parts: list[str] = []
    for action in agent_output.action or []:
        dumped = action.model_dump(exclude_unset=True)
        for name, params in dumped.items():
            if isinstance(params, dict) and params:
                brief = ", ".join(f"{k}={v}" for k, v in list(params.items())[:3])
                parts.append(f"{name}({brief})" if brief else name)
            else:
                parts.append(str(name))
    return "; ".join(parts) if parts else "noop"
