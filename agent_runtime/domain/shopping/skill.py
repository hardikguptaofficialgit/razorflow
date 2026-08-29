"""Shopping domain skill — e-commerce phases, guards, and verification."""

from __future__ import annotations

import re

from agent_runtime.domain.protocol import DomainSkill
from agent_runtime.domain.shopping import (
    action_gate,
    action_result,
    checkout_controls,
    goal,
    goal_guard,
    memory_sync,
    parse,
    phase_progression,
    search_state,
    signals,
)
from agent_runtime.domain.shopping.checkout_flow import (
    checkout_requires_handoff,
    is_checkout_flow_page,
)
from agent_runtime.domain.shopping.helpers import shopping_intent
from agent_runtime.domain.shopping.spec import COMPLETION_BY_PHASE, forbidden_for_phase
from agent_runtime.domain.shopping.action_gate import (
    _is_checkout_action,
    handoff_allowed as shopping_handoff_allowed,
)
from agent_runtime.executor.actions import AgentAction
from agent_runtime.observation.browser_state import BrowserPage
from agent_runtime.observation.signals import infer_generic_page_signals
from agent_runtime.domain.shopping.target_resolve import refresh_action_target
from agent_runtime.task.parsed import ParsedTask
from agent_runtime.task.spec import TaskSpec
from core.protocol import PageContext

_SHOPPING_HINT = re.compile(
    r"\b(?:cart|checkout|add\s+to\s+cart|buy|purchase|snacks|earbuds|product)\b",
    re.I,
)


class ShoppingDomainSkill(DomainSkill):
    skill_id = "shopping"

    @staticmethod
    def is_shopping_task(task: str) -> bool:
        return bool(_SHOPPING_HINT.search(task))

    def parse_task_with_spec(self, task: str) -> tuple[ParsedTask, TaskSpec]:
        spec = parse.parse_task_spec(task)
        return parse.spec_to_parsed(spec), spec

    def infer_page_signals(self, page: PageContext) -> list[str]:
        combined = infer_generic_page_signals(page)
        for signal in signals.infer_shopping_page_signals(page):
            if signal not in combined:
                combined.append(signal)
        return combined

    def forbidden_for_phase(self, phase: str, spec: TaskSpec) -> frozenset[str]:
        return forbidden_for_phase(phase)  # type: ignore[arg-type]

    def phase_completion_text(self, phase: str, spec: TaskSpec) -> str:
        return COMPLETION_BY_PHASE.get(phase, spec.target_state)  # type: ignore[arg-type]

    def phase_satisfied(self, phase: str, state: RunState, page: BrowserPage) -> bool:
        return goal.phase_satisfied(phase, state, page)  # type: ignore[arg-type]

    def milestones_met(self, phase: str, state: RunState) -> bool:
        return goal.milestones_met(state)

    def is_goal_satisfied(self, state: RunState, page: BrowserPage | None) -> bool:
        return goal.is_goal_satisfied(state, page)

    def approve_completion(
        self, state: RunState, page: BrowserPage | None, *, source: str
    ) -> bool:
        return goal.approve_completion(state, page, source=source)

    def update_milestones(self, state: RunState, page: BrowserPage | None) -> None:
        goal.update_milestones(state, page)

    def sync_memory(self, state: RunState, page: BrowserPage | None) -> None:
        memory_sync.sync_memory_from_observation(state, page)

    def try_advance_phase(self, state: RunState, page: BrowserPage | None) -> bool:
        return phase_progression.try_advance_phase(state, page)

    def filter_forbidden_actions(
        self,
        spec: TaskSpec,
        actions: list[AgentAction],
        *,
        current_phase: str,
        state: RunState,
    ) -> tuple[list[AgentAction], list[str]]:
        return action_gate.filter_forbidden_actions(
            spec, actions, current_phase=current_phase, state=state  # type: ignore[arg-type]
        )

    def filter_non_advancing_actions(
        self, state: RunState, actions: list[AgentAction]
    ) -> tuple[list[AgentAction], list[str]]:
        return goal_guard.filter_non_advancing_actions(state, actions)

    def classify_action(self, action: AgentAction) -> set[str]:
        return action_gate.classify_action(action)

    def action_advances_goal(
        self, state: RunState, action: AgentAction
    ) -> tuple[bool, str]:
        return goal_guard.action_advances_goal(state, action)

    def goal_quota_met(self, state: RunState) -> bool:
        return goal_guard.goal_quota_met(state)

    def find_goal_ready(self, state: RunState, page: BrowserPage | None) -> bool:
        return search_state.find_goal_ready(state, page)

    def needs_search(self, state: RunState, page: BrowserPage | None) -> bool:
        return search_state.needs_search(state, page)

    def planner_nudges(self, state: RunState, page: BrowserPage | None) -> list[str]:
        nudges: list[str] = []
        spec = state.task_spec
        if (
            spec
            and shopping_intent(spec) == "add_to_cart"
            and page
            and not search_state.on_search_page(page)
            and search_state.search_entity(state)
            and not search_state.entity_visible_on_page(page, search_state.search_entity(state))
        ):
            entity = search_state.search_entity(state)
            nudges.append(
                f"Search for '{entity}' using the search bar before adding to cart."
            )
        if self.needs_search(state, page):
            query = search_state.search_entity(state) or "the requested product"
            nudges.append(
                f"Not on search results yet — use search/type for '{query}' in the search bar. "
                "Do NOT scroll the homepage product grid."
            )
        return nudges

    def planner_context_extra(self, state: RunState, page: BrowserPage | None) -> str:
        if not page:
            return ""
        section = checkout_controls.format_checkout_controls_section(page)
        if section:
            return section
        if state.current_phase in {"checkout", "checkout_reached"}:
            return (
                "Checkout phase: use visible Proceed to checkout / Checkout controls from observation."
            )
        return ""

    def verify_action_result(
        self,
        state: RunState,
        action: AgentAction,
        *,
        success: bool,
        verified: bool | None,
        before: BrowserPage | None,
        after: BrowserPage | None,
    ) -> bool:
        return action_result.verify_action_result(
            state, action, success=success, verified=verified, before=before, after=after
        )

    def apply_verified_progress(
        self,
        state: RunState,
        action: AgentAction,
        page: BrowserPage | None,
        *,
        ok: bool,
        before: BrowserPage | None = None,
    ) -> None:
        action_result.apply_verified_progress(
            state, action, page, ok=ok, before=before
        )

    def refresh_action_target(
        self, action: AgentAction, page: BrowserPage | None
    ) -> AgentAction:
        return refresh_action_target(action, page)

    def post_action_handoff(
        self,
        state: RunState,
        page: BrowserPage | None,
        action: AgentAction,
        *,
        ok: bool,
    ) -> "DispatchResult | None":
        from agent_runtime.runtime import DispatchResult
        from agent_runtime.state.phase import RuntimePhase

        if not ok or not _is_checkout_action(action):
            return None
        if state.current_phase not in {"checkout", "checkout_reached"}:
            return None
        state.milestones.add("reached_checkout")
        if page and checkout_requires_handoff(page):
            state.phase = RuntimePhase.HANDOFF
            state.waiting_for_user = True
            state.metrics["completion_source"] = "checkout_action_handoff"
            msg = (
                "Sign in to complete checkout. Your cart is saved — "
                "finish signing in, then tap Resume."
            )
            return DispatchResult(
                kind="handoff",
                steps=[],
                message=msg,
                chat_message=msg,
                runtime_phase="handoff",
            )
        if page and is_checkout_flow_page(page):
            from agent_runtime.chat.messages import completion_message

            state.phase = RuntimePhase.GOAL_REACHED
            state.metrics["completion_source"] = "checkout_action"
            msg = completion_message(state, page)
            return DispatchResult(
                kind="complete",
                steps=[],
                message=msg,
                chat_message=msg,
            )
        state.planner_nudge = (
            "Checkout control click did not reach checkout or a login gate. "
            "Re-observe checkout-capable controls on the cart or current page."
        )
        return DispatchResult(kind="continue", steps=[], runtime_phase="observing")

    def completion_handoff(
        self, state: RunState, page: BrowserPage | None, *, source: str
    ) -> "DispatchResult | None":
        from agent_runtime.runtime import DispatchResult
        from agent_runtime.state.phase import RuntimePhase

        if page and checkout_requires_handoff(page):
            state.phase = RuntimePhase.HANDOFF
            state.waiting_for_user = True
            state.metrics["completion_source"] = f"{source}_handoff"
            msg = (
                "Sign in to complete checkout. Your cart is saved — "
                "finish signing in, then tap Resume."
            )
            return DispatchResult(
                kind="handoff",
                steps=[],
                message=msg,
                chat_message=msg,
                runtime_phase="handoff",
            )
        return None

    def initial_remaining_work(self, parsed: ParsedTask) -> list[str]:
        if parsed.goal == "search":
            return ["find matching results"]
        if parsed.goal == "add_to_cart":
            if parsed.product_hints:
                return [f"add {hint}" for hint in parsed.product_hints]
            return [f"add {parsed.item_count} item(s) to cart"]
        if parsed.goal == "view_cart":
            return ["open cart page"]
        if parsed.goal in {"checkout", "purchase"}:
            return ["reach checkout"]
        if parsed.goal == "remove":
            return [f"remove {parsed.remove_target or 'item'} from cart"]
        return ["complete user request"]

    def handoff_allowed(self, page: BrowserPage | None, reason: str) -> bool:
        return shopping_handoff_allowed(page, reason)


_shopping_skill = ShoppingDomainSkill()


def get_shopping_skill() -> ShoppingDomainSkill:
    return _shopping_skill
