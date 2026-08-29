"""Core agent configuration - controls optional domain-specific features."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class AgentConfig:
    """Configuration for the core browser agent."""

    # Enable/disable optional domain-specific features
    enable_shopping_guards: bool = field(
        default_factory=lambda: os.getenv("ENABLE_SHOPPING_GUARDS", "true").lower() == "true"
    )
    enable_store_fast_path: bool = field(
        default_factory=lambda: os.getenv("ENABLE_STORE_FAST_PATH", "true").lower() == "true"
    )
    enable_shopping_heuristics: bool = field(
        default_factory=lambda: os.getenv("ENABLE_SHOPING_HEURISTICS", "true").lower() == "true"
    )

    # Core agent behavior
    max_planning_retries: int = field(
        default_factory=lambda: int(os.getenv("MAX_PLANNING_RETRIES", "2"))
    )
    max_steps_per_chunk: int = field(
        default_factory=lambda: int(os.getenv("MAX_STEPS_PER_CHUNK", "2"))
    )

    # Recovery and safety
    enable_loop_detection: bool = True
    enable_auth_detection: bool = True
    enable_goal_verification: bool = True

    # Executor mode
    executor_mode: Literal["browser_use", "extension_dom"] = field(
        default_factory=lambda: os.getenv("EXECUTOR_MODE", "browser_use")
    )

    @classmethod
    def get(cls) -> "AgentConfig":
        """Get the singleton configuration instance."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    def is_generic_mode(self) -> bool:
        """Check if running in generic mode (no shopping-specific features)."""
        return not (
            self.enable_shopping_guards
            or self.enable_store_fast_path
            or self.enable_shopping_heuristics
        )


# Global configuration instance
config = AgentConfig.get()
