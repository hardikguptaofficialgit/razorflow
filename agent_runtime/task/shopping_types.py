"""Re-export shopping domain types for tests and tooling."""

from agent_runtime.domain.shopping.spec import (  # noqa: F401
    COMPLETION_BY_PHASE,
    FORBIDDEN_BY_INTENT,
    FORBIDDEN_BY_PHASE,
    GoalPhase,
    TaskIntent,
    forbidden_for_phase,
    phase_for_intent,
)
