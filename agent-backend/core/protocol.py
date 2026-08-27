"""Shared WebSocket bridge protocol between extension and agent-backend."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

AgentState = Literal[
    "idle",
    "listening",
    "thinking",
    "acting",
    "paused",
    "waiting_for_user",
]

TargetRole = Literal["search", "input", "button", "link"]

RunStatus = Literal["active", "waiting_for_user", "complete", "error", "cancelled"]


class PageElementSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    index: int = Field(default=0, ge=0)
    role: TargetRole
    tag: str
    text: str = ""
    placeholder: str = ""
    aria_label: str = Field(default="", alias="ariaLabel")
    href: str = ""
    value: str = ""
    enabled: bool = True
    bbox_x: int | None = Field(default=None, alias="bboxX")
    bbox_y: int | None = Field(default=None, alias="bboxY")
    bbox_width: int | None = Field(default=None, alias="bboxWidth")
    bbox_height: int | None = Field(default=None, alias="bboxHeight")

    @field_validator("href", "value", mode="before")
    @classmethod
    def _coerce_optional_str(cls, value: object) -> str:
        return "" if value is None else str(value)


class PageProductSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    price_text: str = Field(default="", alias="priceText")
    rating_text: str = Field(default="", alias="ratingText")
    review_count_text: str = Field(default="", alias="reviewCountText")
    availability_text: str = Field(default="", alias="availabilityText")
    element_index: int | None = Field(default=None, alias="elementIndex")
    add_to_cart_element_index: int | None = Field(
        default=None,
        alias="addToCartElementIndex",
    )


class PageCartLineSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    quantity: int = Field(default=1, ge=1)
    remove_element_index: int | None = Field(
        default=None,
        alias="removeElementIndex",
    )


class PageContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    url: str
    elements: list[PageElementSummary] = Field(default_factory=list, max_length=120)
    products: list[PageProductSummary] = Field(default_factory=list, max_length=16)
    cart_lines: list[PageCartLineSummary] = Field(
        default_factory=list,
        alias="cartLines",
        max_length=24,
    )
    screenshot_data_url: str | None = Field(
        default=None,
        alias="screenshotDataUrl",
        max_length=400_000,
    )


class SetStateStep(BaseModel):
    action: Literal["set_state"]
    state: AgentState


class TypeInElementStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: Literal["type_in_element"]
    role: TargetRole
    text: str = Field(min_length=1)
    element_index: int | None = Field(default=None, alias="elementIndex", ge=1)
    match_text: str | None = Field(default=None, alias="matchText", min_length=1)


class ClickElementStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: Literal["click_element"]
    role: TargetRole
    element_index: int | None = Field(default=None, alias="elementIndex", ge=1)
    match_text: str | None = Field(default=None, alias="matchText", min_length=1)


class HighlightElementStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: Literal["highlight_element"]
    role: TargetRole
    element_index: int | None = Field(default=None, alias="elementIndex", ge=1)
    match_text: str | None = Field(default=None, alias="matchText", min_length=1)


class NavigateUrlStep(BaseModel):
    action: Literal["navigate_url"]
    url: str = Field(min_length=1)


class WaitForUserStep(BaseModel):
    action: Literal["wait_for_user"]


class ReadyForPaymentLinkStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: Literal["ready_for_payment_link"]
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    amount_paise: int = Field(alias="amountPaise", gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)


ActionStep = Annotated[
    Union[
        SetStateStep,
        TypeInElementStep,
        ClickElementStep,
        HighlightElementStep,
        NavigateUrlStep,
        WaitForUserStep,
        ReadyForPaymentLinkStep,
    ],
    Field(discriminator="action"),
]


class PaymentLinkProposalPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    amount_paise: int = Field(alias="amountPaise", gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)


class StartRunMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["START_RUN"]
    task: str = Field(min_length=1)
    run_id: str = Field(alias="runId", min_length=1)
    url: str | None = None
    page_context: PageContext | None = Field(default=None, alias="pageContext")


class ActionResultMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["ACTION_RESULT"]
    run_id: str = Field(alias="runId", min_length=1)
    step: ActionStep
    success: bool
    error: str | None = None
    verified: bool | None = None
    page_context: PageContext | None = Field(default=None, alias="pageContext")


class ResumeRunMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["RESUME_RUN"]
    run_id: str = Field(alias="runId", min_length=1)
    page_context: PageContext | None = Field(default=None, alias="pageContext")


class CancelRunMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["CANCEL_RUN"]
    run_id: str = Field(alias="runId", min_length=1)


class ConfirmPaymentLinkMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["CONFIRM_PAYMENT_LINK"]
    run_id: str = Field(alias="runId", min_length=1)
    confirmed: bool = True


class DeclinePaymentLinkMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["DECLINE_PAYMENT_LINK"]
    run_id: str = Field(alias="runId", min_length=1)


ExtensionMessage = Annotated[
    Union[
        StartRunMessage,
        ActionResultMessage,
        ResumeRunMessage,
        CancelRunMessage,
        ConfirmPaymentLinkMessage,
        DeclinePaymentLinkMessage,
    ],
    Field(discriminator="type"),
]


class NextActionMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["NEXT_ACTION"]
    run_id: str = Field(alias="runId", min_length=1)
    steps: list[ActionStep] = Field(min_length=1, max_length=2)
    turn: int = Field(ge=1)
    action_summary: str | None = Field(default=None, alias="actionSummary")
    screenshot_data_url: str | None = Field(
        default=None,
        alias="screenshotDataUrl",
        max_length=400_000,
    )


class RunCompleteMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["RUN_COMPLETE"]
    run_id: str = Field(alias="runId", min_length=1)
    message: str = ""


class RunWaitingForUserMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["RUN_WAITING_FOR_USER"]
    run_id: str = Field(alias="runId", min_length=1)
    message: str = ""


class RunNeedsClarificationMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["RUN_NEEDS_CLARIFICATION"]
    run_id: str = Field(alias="runId", min_length=1)
    message: str


class RunErrorMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["RUN_ERROR"]
    run_id: str = Field(alias="runId", min_length=1)
    message: str


class PaymentLinkConfirmationMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["PAYMENT_LINK_CONFIRMATION_REQUIRED"]
    run_id: str = Field(alias="runId", min_length=1)
    proposal: PaymentLinkProposalPayload
    message: str = "Confirm payment link creation."


class PaymentLinkReadyMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["PAYMENT_LINK_READY"]
    run_id: str = Field(alias="runId", min_length=1)
    payment_link_url: str = Field(alias="paymentLinkUrl", min_length=1)
    amount_paise: int = Field(alias="amountPaise", gt=0)
    currency: str
    description: str
    reference_id: str = Field(alias="referenceId", min_length=1)
    message: str = "Payment link ready."


class PaymentLinkFailedMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["PAYMENT_LINK_FAILED"]
    run_id: str = Field(alias="runId", min_length=1)
    message: str
    recoverable: bool = True


class AgentSyncCursor(BaseModel):
    x: float
    y: float


class AgentSyncHighlight(BaseModel):
    x: float
    y: float
    width: float
    height: float


class AgentSyncMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["AGENT_SYNC"]
    run_id: str = Field(alias="runId", min_length=1)
    phase: Literal["thinking", "acting", "observing"]
    url: str = ""
    title: str = ""
    step: int = Field(default=0, ge=0)
    action_summary: str = Field(default="", alias="actionSummary")
    cursor: AgentSyncCursor | None = None
    highlight: AgentSyncHighlight | None = None


class ExecutorModeMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: Literal["EXECUTOR_MODE"]
    run_id: str = Field(alias="runId", min_length=1)
    mode: Literal["browser_use", "extension_dom"] = "browser_use"


BackendMessage = Annotated[
    Union[
        NextActionMessage,
        RunCompleteMessage,
        RunWaitingForUserMessage,
        RunNeedsClarificationMessage,
        RunErrorMessage,
        PaymentLinkConfirmationMessage,
        PaymentLinkReadyMessage,
        PaymentLinkFailedMessage,
        AgentSyncMessage,
        ExecutorModeMessage,
    ],
    Field(discriminator="type"),
]


class PlannerChunkOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    steps: list[ActionStep] = Field(default_factory=list, max_length=2)
    terminal: Literal[
        "continue",
        "complete",
        "system_complete",
        "wait_for_user",
        "ready_for_payment_link",
        "needs_clarification",
    ] = "continue"
    payment_proposal: PaymentLinkProposalPayload | None = Field(
        default=None,
        alias="paymentProposal",
    )


class ActionHistoryEntry(BaseModel):
    step: ActionStep
    success: bool
    error: str | None = None
    verified: bool | None = None
    page_fingerprint: str | None = None


class ObservedElement(BaseModel):
    index: int
    tag: str
    text: str = ""
    placeholder: str = ""
    aria_label: str = ""
    role_hint: str = ""


class BrowserObservation(BaseModel):
    source: Literal["browser-use"] = "browser-use"
    url: str = ""
    title: str = ""
    page_summary: str = ""
    interactive_elements: list[ObservedElement] = Field(default_factory=list, max_length=30)
    screenshot_available: bool = False
    vision_hook_note: str | None = None


PlanningSource = Literal["page_context_only", "page_context_and_browser_use"]
