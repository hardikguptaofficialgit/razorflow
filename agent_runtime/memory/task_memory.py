"""Structured task memory for planner context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_runtime.observation.browser_state import BrowserPage


@dataclass
class TaskMemory:
    goal: str = ""
    constraints: list[str] = field(default_factory=list)
    completed_steps: list[str] = field(default_factory=list)
    verified_facts: list[str] = field(default_factory=list)
    failed_actions: list[str] = field(default_factory=list)
    verified_items: list[str] = field(default_factory=list)
    current_target: str = ""
    remaining_work: list[str] = field(default_factory=list)
    remaining_items: list[str] = field(default_factory=list)
    items_added: int = 0
    items_target: int = 1
    current_page: BrowserPage | None = None
    current_url: str = ""

    def to_prompt_block(self) -> str:
        lines = ["TASK MEMORY:"]
        if self.goal:
            lines.append(f"- goal: {self.goal}")
        if self.constraints:
            lines.append(f"- constraints: {'; '.join(self.constraints)}")
        if self.verified_facts:
            lines.append("- verified_facts:")
            lines.extend(f"  • {fact}" for fact in self.verified_facts[-12:])
        if self.failed_actions:
            lines.append("- failed_actions (do NOT repeat):")
            lines.extend(f"  • {item}" for item in self.failed_actions[-8:])
        if self.verified_items:
            lines.append("- verified_items:")
            lines.extend(f"  • {item}" for item in self.verified_items[-8:])
        if self.completed_steps:
            lines.append("- completed_steps:")
            lines.extend(f"  • {step}" for step in self.completed_steps[-8:])
        if self.remaining_work:
            lines.append("- remaining_work:")
            lines.extend(f"  • {item}" for item in self.remaining_work)
        if self.remaining_items:
            lines.append("- remaining_items:")
            lines.extend(f"  • {item}" for item in self.remaining_items)
        if self.current_url:
            lines.append(f"- current_url: {self.current_url}")
        lines.append(f"- items_added: {self.items_added}/{self.items_target}")
        if self.current_target:
            lines.append(f"- current_target: {self.current_target}")
        return "\n".join(lines)

    def note_fact(self, fact: str) -> None:
        if fact and fact not in self.verified_facts:
            self.verified_facts.append(fact)

    def note_failure(self, description: str) -> None:
        if description and description not in self.failed_actions:
            self.failed_actions.append(description)

    def note_completed(self, step: str) -> None:
        if step:
            self.completed_steps.append(step)
