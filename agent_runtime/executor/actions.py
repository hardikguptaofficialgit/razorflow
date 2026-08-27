"""Strict V2 action schema."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ActionType = Literal[
    "navigate",
    "click",
    "type",
    "select",
    "scroll",
    "wait",
    "search",
    "extract",
    "go_back",
    "open_tab",
    "close_tab",
    "finish",
    "handoff",
]

TargetRole = Literal["search", "input", "button", "link"]


class ElementTarget(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    element_id: str | None = Field(default=None, alias="elementId")
    role: TargetRole | None = None
    description: str = ""
    match_text: str | None = Field(default=None, alias="matchText")


class VerificationCondition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url_changed: bool | None = Field(default=None, alias="urlChanged")
    url_contains: str | None = Field(default=None, alias="urlContains")
    url_matches: str | None = Field(default=None, alias="urlMatches")
    results_visible: bool | None = Field(default=None, alias="resultsVisible")
    cart_count_increased: bool | None = Field(default=None, alias="cartCountIncreased")
    value_equals: str | None = Field(default=None, alias="valueEquals")
    element_visible: str | None = Field(default=None, alias="elementVisible")


class AgentAction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: ActionType
    target: ElementTarget | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)
    expected_outcome: str = Field(min_length=1, alias="expectedOutcome")
    verification: VerificationCondition | None = None


class PlannerOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reasoning: str = ""
    user_message: str = Field(default="", alias="userMessage")
    actions: list[AgentAction] = Field(default_factory=list, max_length=3)
    propose_finish: bool = Field(default=False, alias="proposeFinish")
    propose_handoff: bool = Field(default=False, alias="proposeHandoff")
    handoff_reason: str | None = Field(default=None, alias="handoffReason")
