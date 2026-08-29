"""Generic recovery system - domain-independent failure handling."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from core.protocol import PageContext, PlannerChunkOutput, ClickElementStep, ScrollPageStep, GoBackStep
from core.run_manager import RunSession
from core.generic_page_analyzer import get_generic_page_analyzer
from core.action_loop import action_signature

logger = logging.getLogger(__name__)


@dataclass
class RecoveryAction:
    """A recovery action to take when the agent gets stuck."""
    action_type: Literal["retry", "alternative", "scroll", "navigate_back", "handoff"]
    target_element_index: int | None = None
    target_text: str | None = None
    reason: str = ""
    confidence: float = 0.5


class GenericRecovery:
    """
    Generic recovery system that handles failures without domain assumptions.
    Works for any browser automation task, not just shopping.
    """

    def __init__(self):
        self.max_retries = 3
        self.max_alternatives = 5

    def analyze_failure(
        self,
        session: RunSession,
        last_error: str | None = None,
    ) -> RecoveryAction | None:
        """Analyze the current failure state and suggest recovery action."""
        if not session.history:
            return None

        last_entry = session.history[-1]
        last_step = last_entry.step
        last_success = last_entry.success

        page = session.latest_page_context

        # If last action succeeded but we're still stuck
        if last_success:
            return self._analyze_stuck_state(session, page)

        # If last action failed
        return self._analyze_failed_action(session, last_step, page, last_error)

    def _analyze_stuck_state(
        self,
        session: RunSession,
        page: PageContext | None,
    ) -> RecoveryAction | None:
        """Analyze when agent is stuck (page not changing, repeating actions)."""
        if session.stale_page_turns >= 2:
            # Page hasn't changed - try scrolling
            return RecoveryAction(
                action_type="scroll",
                reason="Page state unchanged - suggest scrolling",
                confidence=0.7,
            )

        # Check for repeated actions
        if len(session.history) >= 2:
            recent = session.history[-2:]
            if (recent[0].success and recent[1].success and
                action_signature(recent[0].step) == action_signature(recent[1].step)):
                # Repeating same action - try alternative
                return self._suggest_alternative_action(session, page)

        return None

    def _analyze_failed_action(
        self,
        session: RunSession,
        last_step,
        page: PageContext | None,
        last_error: str | None,
    ) -> RecoveryAction | None:
        """Analyze a failed action and suggest recovery."""
        action = getattr(last_step, "action", "")
        signature = action_signature(last_step)

        # Count how many times this signature has failed
        failure_count = 0
        for entry in reversed(session.history[-5:]):
            if not entry.success and action_signature(entry.step) == signature:
                failure_count += 1

        if failure_count >= self.max_retries:
            # Too many retries - try alternative or handoff
            alternative = self._suggest_alternative_action(session, page)
            if alternative:
                return alternative
            return RecoveryAction(
                action_type="handoff",
                reason=f"Action '{signature}' failed {failure_count} times - request handoff",
                confidence=0.8,
            )

        # If it's a click failure, try a different element
        if action == "click_element" and page:
            return self._suggest_alternative_click(session, last_step, page)

        # If it's a type failure, the element might not be suitable
        if action == "type_in_element":
            return RecoveryAction(
                action_type="retry",
                reason="Type action failed - might need different element or wait",
                confidence=0.5,
            )

        # Default: retry
        return RecoveryAction(
            action_type="retry",
            reason="Action failed - suggest retry",
            confidence=0.4,
        )

    def _suggest_alternative_action(
        self,
        session: RunSession,
        page: PageContext | None,
    ) -> RecoveryAction | None:
        """Suggest an alternative action based on page context."""
        if not page:
            return None

        analyzer = get_generic_page_analyzer()
        actionable_elements = analyzer.find_actionable_elements(page)

        # Filter out elements we've already tried
        tried_signatures = {
            action_signature(entry.step)
            for entry in session.history[-10:]
            if not entry.success
        }

        for index, role, text in actionable_elements:
            # Create a simple signature for this element
            element_sig = f"{role}:{text[:20]}"
            if element_sig not in tried_signatures:
                return RecoveryAction(
                    action_type="alternative",
                    target_element_index=index,
                    target_text=text,
                    reason=f"Try alternative element: {role} '{text[:30]}'",
                    confidence=0.6,
                )

        return None

    def _suggest_alternative_click(
        self,
        session: RunSession,
        last_step,
        page: PageContext,
    ) -> RecoveryAction | None:
        """Suggest an alternative element to click."""
        if not isinstance(last_step, ClickElementStep):
            return None

        analyzer = get_generic_page_analyzer()
        failed_text = (last_step.match_text or "").lower()

        # Find similar elements
        similar_elements = []
        for index, role, text in analyzer.find_actionable_elements(page):
            if role == last_step.role and text != failed_text:
                # Calculate similarity (simple heuristic)
                similarity = self._text_similarity(failed_text, text)
                if similarity > 0.3:
                    similar_elements.append((index, text, similarity))

        # Sort by similarity and suggest the best alternative
        if similar_elements:
            similar_elements.sort(key=lambda x: x[2], reverse=True)
            best_index, best_text, _ = similar_elements[0]
            return RecoveryAction(
                action_type="alternative",
                target_element_index=best_index,
                target_text=best_text,
                reason=f"Try similar element: '{best_text[:30]}'",
                confidence=0.7,
            )

        return None

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity (0-1)."""
        text1 = text1.lower()
        text2 = text2.lower()

        if text1 == text2:
            return 1.0

        # Simple overlap calculation
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union) if union else 0.0

    def should_handoff(
        self,
        session: RunSession,
        page: PageContext | None,
    ) -> tuple[bool, str]:
        """
        Determine if the agent should hand off to the user.
        Returns (should_handoff, reason).
        """
        # Too many consecutive failures
        if session.consecutive_failures >= 3:
            return True, f"Too many consecutive failures ({session.consecutive_failures})"

        # Page requires authentication
        if page:
            from core.generic_utils import detect_auth_page
            is_auth, reason = detect_auth_page(
                page.url or "",
                page.title or "",
                page.elements or [],
            )
            if is_auth:
                return True, f"Authentication required: {reason}"

        # Stale page for too long
        if session.stale_page_turns >= 4:
            return True, f"Page unchanged for {session.stale_page_turns} turns"

        # No actionable elements found
        if page and len(page.elements) == 0:
            return True, "No interactive elements found on page"

        return False, ""


def recovery_to_planner_chunk(
    recovery_action: RecoveryAction,
    session: RunSession,
) -> PlannerChunkOutput | None:
    """Convert a generic recovery suggestion into executable wire steps."""
    if recovery_action.action_type == "scroll":
        session.auto_recovery_count += 1
        return PlannerChunkOutput(
            steps=[ScrollPageStep(action="scroll_page", direction="down", amount_px=700)],
        )
    if recovery_action.action_type == "navigate_back":
        session.auto_recovery_count += 1
        return PlannerChunkOutput(steps=[GoBackStep(action="go_back")])
    if (
        recovery_action.action_type == "alternative"
        and recovery_action.target_element_index is not None
    ):
        session.auto_recovery_count += 1
        return PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role="button",
                    elementIndex=recovery_action.target_element_index,
                    matchText=recovery_action.target_text or "",
                )
            ],
        )
    return None


# Singleton instance
_generic_recovery = GenericRecovery()


def get_generic_recovery() -> GenericRecovery:
    """Get the generic recovery singleton."""
    return _generic_recovery
