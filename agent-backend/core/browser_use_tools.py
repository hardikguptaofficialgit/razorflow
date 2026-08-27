"""Custom Browser Use tools for RazorFlow handoffs and protected checkout."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from browser_use.agent.views import ActionResult
from browser_use.tools.service import Tools

from core.agent_decision_log import log_agent_decision
from core.protocol import PaymentLinkProposalPayload


@dataclass
class BrowserUseToolState:
    run_id: str
    pause_requested: bool = False
    handoff_message: str | None = None
    payment_proposal: PaymentLinkProposalPayload | None = None
    last_reasoning: str | None = None
    last_candidates: list[dict] = field(default_factory=list)
    selected_product_title: str | None = None
    cart_verified_count: int | None = None
    last_page_fingerprint: str | None = None
    completion_summary: str | None = None
    # Cart verify runs on the NEXT step callback (after click executed).
    pending_cart_verify: bool = False
    cart_count_before_click: int | None = None
    pending_product_title: str | None = None


_run_tool_state: dict[str, BrowserUseToolState] = {}


def get_tool_state(run_id: str) -> BrowserUseToolState:
    state = _run_tool_state.get(run_id)
    if state is None:
        state = BrowserUseToolState(run_id=run_id)
        _run_tool_state[run_id] = state
    return state


def clear_tool_state(run_id: str) -> None:
    _run_tool_state.pop(run_id, None)


class RequestUserHandoffParams(BaseModel):
    reason: str = Field(
        description=(
            "Why the user must take over (login, OTP, CAPTCHA, address, missing "
            "price/rating, low confidence, etc.)"
        ),
        min_length=3,
    )


class ProposeCheckoutPaymentParams(BaseModel):
    title: str = Field(description="Short product or order title", min_length=1)
    description: str = Field(description="Checkout summary for the user", min_length=1)
    amount_paise: int = Field(description="Total amount in paise (INR)", gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)


class RecordProductDecisionParams(BaseModel):
    reasoning: str = Field(
        description="Why this product was chosen vs alternatives using visible facts only",
        min_length=3,
    )
    selected_title: str = Field(description="Exact visible product title selected", min_length=1)
    selected_price: str = Field(
        default="",
        description="Exact visible price text, or empty if not visible",
    )
    selected_rating: str = Field(
        default="",
        description="Exact visible rating text, or empty if not visible",
    )
    candidates_summary: str = Field(
        default="",
        description="Short list of other visible candidates considered (title+price+rating)",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence that selection matches user constraints (0-1)",
    )


# record_product_decision kept for optional explicit logging but not required in the prompt.


class MarkShoppingCompleteParams(BaseModel):
    summary: str = Field(
        description="What was accomplished (must mention product added / checkout ready)",
        min_length=3,
    )
    product_in_cart: str = Field(
        description="Exact product title confirmed in cart, or empty if only checkout-ready",
        default="",
    )
    cart_count: int = Field(
        default=0,
        ge=0,
        description="Visible cart item count after add-to-cart (must be >= 1 unless checkout-ready)",
    )
    checkout_ready: bool = Field(
        default=False,
        description="True only if checkout page/total is visible and verified",
    )


def bind_tools_for_run(run_id: str) -> Tools:
    state = get_tool_state(run_id)
    # Keep native `done` (stock Agent forces it at max_steps / failures).
    # Prefer mark_shopping_complete after verified cart; both may complete a run.
    tools = Tools()

    @tools.action(
        description=(
            "Pause automation and ask the user to complete a manual step such as login, "
            "OTP, CAPTCHA, address confirmation, missing catalog matches, or missing product data."
        ),
        param_model=RequestUserHandoffParams,
    )
    async def request_user_handoff(params: RequestUserHandoffParams) -> ActionResult:
        state.pause_requested = True
        state.handoff_message = params.reason.strip()
        log_agent_decision(
            run_id=run_id,
            step=-1,
            phase="handoff",
            reasoning=state.handoff_message,
            action="request_user_handoff",
        )
        return ActionResult(
            extracted_content=f"Waiting for user: {state.handoff_message}",
            long_term_memory=state.handoff_message,
            include_in_memory=True,
        )

    @tools.action(
        description=(
            "Mark the shopping goal complete ONLY after Add to Cart succeeded "
            "(verified cart count) or checkout is ready. Do not call after search alone."
        ),
        param_model=MarkShoppingCompleteParams,
    )
    async def mark_shopping_complete(
        params: MarkShoppingCompleteParams,
        browser_session=None,
    ) -> ActionResult:
        from core.cart_verify import read_cart_count

        cart_count = params.cart_count
        live = await read_cart_count(browser_session)
        if live is not None:
            cart_count = live

        verified = params.checkout_ready or cart_count >= 1
        if not verified:
            log_agent_decision(
                run_id=run_id,
                step=-1,
                phase="completion_rejected",
                reasoning=params.summary,
                action="mark_shopping_complete",
                verification={
                    "accepted": False,
                    "cart_count": cart_count,
                    "checkout_ready": params.checkout_ready,
                },
            )
            return ActionResult(
                extracted_content=(
                    "Completion rejected: cart still empty. "
                    "Click Add to cart, verify cart_count>=1, then retry."
                ),
                include_in_memory=True,
                error="Cannot complete without cart or checkout verification",
            )

        state.selected_product_title = params.product_in_cart.strip() or state.selected_product_title
        state.last_reasoning = params.summary.strip()
        state.completion_summary = params.summary.strip()
        state.pause_requested = True
        log_agent_decision(
            run_id=run_id,
            step=-1,
            phase="complete",
            reasoning=params.summary.strip(),
            action="mark_shopping_complete",
            extracted={
                "product_in_cart": params.product_in_cart,
                "cart_count": cart_count,
                "checkout_ready": params.checkout_ready,
            },
            verification={"accepted": True, "cart_count_live": cart_count},
        )
        return ActionResult(
            extracted_content=f"Shopping complete: {params.summary}",
            long_term_memory=params.summary,
            include_in_memory=True,
            is_done=True,
            success=True,
        )

    @tools.action(
        description=(
            "Optional: log a product choice. Prefer clicking Add to cart immediately instead. "
            "If already recorded, this returns an error telling you to click Add to cart."
        ),
        param_model=RecordProductDecisionParams,
    )
    async def record_product_decision(params: RecordProductDecisionParams) -> ActionResult:
        selected = params.selected_title.strip()
        if (
            state.selected_product_title
            and state.selected_product_title.lower() == selected.lower()
        ):
            return ActionResult(
                extracted_content=(
                    f"Selection already recorded: '{state.selected_product_title}'. "
                    "Do NOT call record_product_decision again. "
                    "NEXT ACTION: click the Add to cart button for this product, "
                    "then verify cart_count increased."
                ),
                long_term_memory=(
                    f"Already chose {state.selected_product_title}. Must click Add to cart now."
                ),
                include_in_memory=True,
                error="Duplicate product decision — click Add to cart now",
            )

        if params.confidence < 0.5:
            state.pause_requested = True
            state.handoff_message = (
                f"Low confidence ({params.confidence:.2f}) selecting '{params.selected_title}'. "
                "Please choose the product manually, then resume."
            )
            log_agent_decision(
                run_id=run_id,
                step=-1,
                phase="low_confidence_handoff",
                reasoning=params.reasoning,
                action="request_user_handoff",
                extracted={
                    "selected_title": params.selected_title,
                    "confidence": params.confidence,
                },
            )
            return ActionResult(
                extracted_content=state.handoff_message,
                long_term_memory=state.handoff_message,
                include_in_memory=True,
                error="Low confidence — handoff required",
            )

        state.last_reasoning = params.reasoning.strip()
        state.selected_product_title = params.selected_title.strip()
        state.last_candidates = [
            {
                "title": params.selected_title.strip(),
                "price": params.selected_price.strip(),
                "rating": params.selected_rating.strip(),
                "candidates": params.candidates_summary.strip(),
                "confidence": params.confidence,
            }
        ]
        log_agent_decision(
            run_id=run_id,
            step=-1,
            phase="product_decision",
            reasoning=params.reasoning.strip(),
            action="record_product_decision",
            extracted={
                "selected_title": params.selected_title.strip(),
                "selected_price": params.selected_price.strip(),
                "selected_rating": params.selected_rating.strip(),
                "candidates_summary": params.candidates_summary.strip(),
                "confidence": params.confidence,
            },
        )
        return ActionResult(
            extracted_content=(
                f"Recorded selection '{params.selected_title}' "
                f"(price={params.selected_price or 'n/a'}, "
                f"rating={params.selected_rating or 'n/a'}, "
                f"confidence={params.confidence:.2f}). "
                "NEXT REQUIRED ACTION: click Add to cart for this product now. "
                "Do not record again."
            ),
            long_term_memory=(
                f"Selected product: {params.selected_title}. Next: Add to cart."
            ),
            include_in_memory=True,
        )

    @tools.action(
        description=(
            "Propose checkout payment for user confirmation in RazorFlow. "
            "Does NOT charge the user — opens protected payment confirmation."
        ),
        param_model=ProposeCheckoutPaymentParams,
    )
    async def propose_checkout_payment(params: ProposeCheckoutPaymentParams) -> ActionResult:
        state.payment_proposal = PaymentLinkProposalPayload(
            title=params.title.strip(),
            description=params.description.strip(),
            amount_paise=params.amount_paise,
            currency=params.currency.strip().upper(),
        )
        state.pause_requested = True
        state.handoff_message = "Confirm payment to continue."
        log_agent_decision(
            run_id=run_id,
            step=-1,
            phase="payment_proposal",
            action="propose_checkout_payment",
            extracted={
                "title": params.title.strip(),
                "amount_paise": params.amount_paise,
                "currency": params.currency.strip().upper(),
            },
        )
        return ActionResult(
            extracted_content=(
                f"Payment confirmation requested: {params.currency} "
                f"{params.amount_paise / 100:.2f} — {params.title}"
            ),
            long_term_memory="Payment confirmation requested — waiting for user.",
            include_in_memory=True,
        )

    return tools
