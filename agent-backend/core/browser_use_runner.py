"""Browser Use execution layer — real browser control for RazorFlow runs."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from urllib.parse import quote, urlparse

from browser_use import Agent
from browser_use.agent.views import AgentOutput
from browser_use.browser.session import BrowserSession
from browser_use.browser.views import BrowserStateSummary

from core.action_override import force_click_add_to_cart, summarize_actions
from core.agent_decision_log import log_agent_decision
from core.browser_use_prompt import RAZORFLOW_EXTEND_SYSTEM_MESSAGE
from core.browser_use_tools import bind_tools_for_run, clear_tool_state, get_tool_state
from core.cart_verify import read_cart_count
from core.llm_factory import require_browser_use_llm
from core.overlay_coords import viewport_rect_from_interacted
from core.page_context_from_browser import page_context_from_browser_state
from core.product_compare import select_best_product
from core.protocol import (
    AgentSyncMessage,
    PaymentLinkConfirmationMessage,
    RunCompleteMessage,
    RunErrorMessage,
    RunWaitingForUserMessage,
)
from core.run_manager import RunManager, RunSession, page_fingerprint
from core.shopping_intent import ShoppingIntent, parse_shopping_intent
from core.step_metrics import StepMetrics, timed_section
from utils.config import (
    BROWSER_USE_HEADLESS,
    get_browser_use_cdp_url,
    get_llm_provider,
    MAX_BROWSER_USE_STEPS,
)

logger = logging.getLogger(__name__)

SendJson = Callable[[Any], Awaitable[None]]

# Stock browser-use Agent defaults (see site-packages/browser_use/agent/service.py).
_STOCK_MAX_CLICKABLE_ELEMENTS_LENGTH = 40_000
_MAX_CLICKABLE_ELEMENTS_HEAVY = 5_500
_MAX_CLICKABLE_ELEMENTS_LOCAL = 18_000
_MAX_HISTORY_ITEMS_LOCAL = 8
_MAX_ACTIONS_PER_STEP_LOCAL = 4
_FIRST_STEP_TIMEOUT_SEC = 50.0
_FIRST_STEP_TIMEOUT_CLOUD_SEC = 180.0
_FIRST_STEP_TIMEOUT_LOCAL_SEC = 180.0
_HEAVY_SITE_MARKERS = (
    "amazon.",
    "flipkart.",
    "walmart.",
    "ebay.",
    "myntra.",
    "ajio.",
)


@dataclass
class BrowserUseRunHandle:
    run_id: str
    task: asyncio.Task | None = None
    agent: Agent | None = None
    browser_session: BrowserSession | None = None
    cancelled: bool = False
    intent: ShoppingIntent | None = None
    last_fingerprint: str | None = None
    last_action_key: str | None = None
    repeated_action_count: int = 0


class BrowserUseRunController:
    """Runs Browser Use agents and streams sync events to the Chrome extension overlay."""

    def __init__(self, run_manager: RunManager) -> None:
        self._run_manager = run_manager
        self._handles: dict[str, BrowserUseRunHandle] = {}

    async def start_run(
        self,
        send_json: SendJson,
        session: RunSession,
        start_url: str | None,
    ) -> None:
        await self.cancel_run(session.run_id, cleanup=False)

        intent = parse_shopping_intent(session.task)
        handle = BrowserUseRunHandle(run_id=session.run_id, intent=intent)
        self._handles[session.run_id] = handle
        clear_tool_state(session.run_id)
        get_tool_state(session.run_id)

        log_agent_decision(
            run_id=session.run_id,
            step=0,
            phase="intent_parsed",
            extracted=intent.to_dict(),
            reasoning="Parsed structured shopping constraints from user task",
            action="parse_shopping_intent",
        )

        handle.task = asyncio.create_task(
            self._run_agent_loop(send_json, session, start_url, handle, resume=False),
        )

    async def resume_run(
        self,
        send_json: SendJson,
        session: RunSession,
        start_url: str | None,
    ) -> None:
        handle = self._handles.get(session.run_id)
        if handle is None or handle.browser_session is None:
            await self.start_run(send_json, session, start_url)
            return

        tool_state = get_tool_state(session.run_id)
        tool_state.pause_requested = False
        tool_state.handoff_message = None
        tool_state.payment_proposal = None
        tool_state.completion_summary = None
        handle.cancelled = False
        if handle.intent is None:
            handle.intent = parse_shopping_intent(session.task)

        if handle.task and not handle.task.done():
            handle.task.cancel()
            try:
                await handle.task
            except asyncio.CancelledError:
                pass

        handle.task = asyncio.create_task(
            self._run_agent_loop(send_json, session, start_url, handle, resume=True),
        )

    async def cancel_run(self, run_id: str, *, cleanup: bool = True) -> None:
        handle = self._handles.get(run_id)
        if handle is None:
            return

        handle.cancelled = True
        get_tool_state(run_id).pause_requested = True

        if handle.task and not handle.task.done():
            handle.task.cancel()
            try:
                await handle.task
            except asyncio.CancelledError:
                pass

        if cleanup and handle.browser_session is not None:
            try:
                await handle.browser_session.kill()
            except Exception as error:
                logger.warning("Browser Use cleanup failed runId=%s: %s", run_id, error)

        if cleanup:
            self._handles.pop(run_id, None)
            clear_tool_state(run_id)

    async def cancel_all_runs(self, *, cleanup: bool = True) -> None:
        for run_id in list(self._handles.keys()):
            await self.cancel_run(run_id, cleanup=cleanup)

    async def _run_agent_loop(
        self,
        send_json: SendJson,
        session: RunSession,
        start_url: str | None,
        handle: BrowserUseRunHandle,
        *,
        resume: bool,
    ) -> None:
        run_id = session.run_id
        tool_state = get_tool_state(run_id)
        intent = handle.intent or parse_shopping_intent(session.task)
        handle.intent = intent

        try:
            if handle.browser_session is None:
                handle.browser_session = self._create_browser_session()

            cdp_url = get_browser_use_cdp_url()
            if self._is_heavy_commerce_url(start_url) and not cdp_url:
                message = (
                    "This large storefront (e.g. Amazon) can't be driven reliably without "
                    "attaching your Chrome tab via CDP — and the page DOM is usually too large. "
                    "Open http://127.0.0.1:3000 (fake-store) for the demo, or start Chrome with "
                    "--remote-debugging-port=9222 and set BROWSER_USE_CDP_URL=http://127.0.0.1:9222."
                )
                logger.warning(
                    "Refusing heavy site without CDP runId=%s url=%s",
                    run_id,
                    start_url,
                )
                self._run_manager.wait_for_user(session)
                await send_json(
                    RunWaitingForUserMessage(
                        type="RUN_WAITING_FOR_USER",
                        runId=run_id,
                        message=message,
                    ).model_dump(by_alias=True, exclude_none=True),
                )
                return

            llm = require_browser_use_llm()
            tools = bind_tools_for_run(run_id)

            task_text = self._build_task(session.task, intent=intent, resume=resume)
            initial_actions = None
            if start_url and not resume:
                initial_actions = [
                    {"navigate": {"url": self._resolve_start_navigation(start_url, intent)}},
                ]

            first_step = asyncio.Event()

            async def on_step(
                browser_state: BrowserStateSummary,
                agent_output: AgentOutput,
                step_number: int,
            ) -> None:
                """
                browser-use calls this AFTER the LLM and BEFORE actions execute.
                Keep it light: observe → optional force index click → overlay sync.
                Cart verification runs here for the PREVIOUS step's click (already executed).
                """
                import time

                first_step.set()
                metrics = StepMetrics(run_id=run_id, step=step_number)
                callback_started = time.perf_counter()

                # --- Verify previous Add-to-cart (post-execution) ---
                with timed_section(metrics, "verify_ms"):
                    if tool_state.pending_cart_verify:
                        after = await read_cart_count(handle.browser_session)
                        before = tool_state.cart_count_before_click
                        tool_state.pending_cart_verify = False
                        increased = (
                            after is not None
                            and before is not None
                            and after > before
                        ) or (after is not None and after >= 1 and before == 0)
                        log_agent_decision(
                            run_id=run_id,
                            step=step_number,
                            phase="click_verify",
                            reasoning=f"cart before={before} after={after}",
                            action="post_click_verify",
                            verification={
                                "cart_before": before,
                                "cart_after": after,
                                "increased": increased,
                                "product": tool_state.pending_product_title,
                            },
                        )
                        if increased:
                            title = tool_state.pending_product_title or "product"
                            tool_state.selected_product_title = title
                            tool_state.cart_verified_count = after
                            tool_state.pending_product_title = None
                            verify_msg = (
                                f"Verified '{title}' in cart (count={after}). "
                                "Continue to cart and checkout."
                            )
                            tool_state.last_reasoning = verify_msg
                            log_agent_decision(
                                run_id=run_id,
                                step=step_number,
                                phase="cart_verified",
                                reasoning=verify_msg,
                                action="continue_after_add_to_cart",
                                verification={
                                    "cart_before": before,
                                    "cart_after": after,
                                    "product": title,
                                },
                            )
                            await send_json(
                                AgentSyncMessage(
                                    type="AGENT_SYNC",
                                    runId=run_id,
                                    phase="acting",
                                    url=browser_state.url or "",
                                    title=browser_state.title or "",
                                    step=step_number,
                                    actionSummary=verify_msg,
                                ).model_dump(by_alias=True, exclude_none=True),
                            )
                            metrics.callback_total_ms = (
                                time.perf_counter() - callback_started
                            ) * 1000.0
                            metrics.log()
                            # Do not pause or complete — agent should proceed to checkout.

                # --- Observe (compact page extract + deterministic compare) ---
                with timed_section(metrics, "observe_ms"):
                    page = page_context_from_browser_state(browser_state)
                    session.latest_page_context = page
                    fingerprint = page_fingerprint(page)
                    changed = fingerprint != handle.last_fingerprint
                    handle.last_fingerprint = fingerprint
                    tool_state.last_page_fingerprint = fingerprint
                    winner, candidates, compare_reason = select_best_product(page, intent)
                    metrics.page_changed = changed
                    metrics.product_count = len(page.products)

                # --- Action selection: force click for BYO LLMs when catalog winner is clear ---
                with timed_section(metrics, "action_select_ms"):
                    forced_index = None
                    if (
                        winner is not None
                        and winner.add_to_cart_element_index is not None
                        and not tool_state.completion_summary
                    ):
                        forced_index = force_click_add_to_cart(agent_output, winner)
                        metrics.forced_click_index = forced_index
                        if forced_index is not None:
                            before = await read_cart_count(handle.browser_session)
                            tool_state.pending_cart_verify = True
                            tool_state.cart_count_before_click = before
                            tool_state.pending_product_title = winner.title
                            tool_state.selected_product_title = winner.title
                            tool_state.last_reasoning = compare_reason

                    action_summary = summarize_actions(agent_output)
                    action_key = action_summary.lower().strip()
                    if action_key and action_key == handle.last_action_key:
                        handle.repeated_action_count += 1
                    else:
                        handle.last_action_key = action_key
                        handle.repeated_action_count = 1

                    # Schedule verify when LLM itself chose a click (no force).
                    if (
                        forced_index is None
                        and "click" in action_key
                        and winner is not None
                        and not tool_state.pending_cart_verify
                    ):
                        before = await read_cart_count(handle.browser_session)
                        tool_state.pending_cart_verify = True
                        tool_state.cart_count_before_click = before
                        tool_state.pending_product_title = winner.title

                    if handle.repeated_action_count >= 3 and forced_index is None:
                        tool_state.pause_requested = True
                        tool_state.handoff_message = (
                            f"Agent stuck repeating '{action_summary}'. "
                            "Please click Add to cart for the chosen product, then resume."
                        )

                log_agent_decision(
                    run_id=run_id,
                    step=step_number,
                    phase="observe_act",
                    observation={
                        "url": browser_state.url,
                        "title": browser_state.title,
                        "page_changed": changed,
                        "elements": len(page.elements),
                    },
                    extracted={
                        "product_count": len(page.products),
                        "recommended": (
                            {
                                "title": winner.title,
                                "price": winner.price,
                                "add_to_cart_index": winner.add_to_cart_element_index,
                            }
                            if winner
                            else None
                        ),
                        "candidates": [
                            {"title": c.title, "price": c.price} for c in candidates[:4]
                        ],
                    },
                    reasoning=compare_reason if winner else str(
                        getattr(agent_output, "memory", None) or ""
                    )[:400],
                    action=action_summary,
                    verification={
                        "forced_click_index": forced_index,
                        "page_fingerprint_changed": changed,
                    },
                )

                # --- Overlay sync (UI only; must not gate the click) ---
                with timed_section(metrics, "sync_ms"):
                    if winner and winner.add_to_cart_element_index is not None:
                        action_override = (
                            f"CLICK Add to cart [{winner.add_to_cart_element_index}] "
                            f"→ {winner.title[:36]}"
                        )
                    else:
                        action_override = action_summary
                    await self._emit_agent_sync(
                        send_json,
                        run_id,
                        browser_state,
                        agent_output,
                        step_number,
                        action_override=action_override,
                    )

                metrics.callback_total_ms = (
                    time.perf_counter() - callback_started
                ) * 1000.0
                metrics.log()

            async def should_stop() -> bool:
                return handle.cancelled or tool_state.pause_requested

            # Fresh agent state on resume — reinjecting history often stalls on huge DOMs.
            injected_state = None

            await send_json(
                AgentSyncMessage(
                    type="AGENT_SYNC",
                    runId=run_id,
                    phase="thinking",
                    url=start_url or "",
                    title="",
                    step=0,
                    actionSummary=(
                        f"Intent: search “{intent.search_query}”"
                        if not resume
                        else "Re-observing page after handoff…"
                    ),
                ).model_dump(by_alias=True, exclude_none=True),
            )

            # OSS browser-use Agent + BYO LLM (openrouter/groq/llamacpp).
            if self._is_heavy_commerce_url(start_url):
                dom_budget = _MAX_CLICKABLE_ELEMENTS_HEAVY
            else:
                dom_budget = _MAX_CLICKABLE_ELEMENTS_LOCAL

            agent_kwargs: dict[str, Any] = {
                "task": task_text,
                "llm": llm,
                "browser_session": handle.browser_session,
                "tools": tools,
                "register_new_step_callback": on_step,
                "register_should_stop_callback": should_stop,
                "extend_system_message": RAZORFLOW_EXTEND_SYSTEM_MESSAGE,
                "use_vision": False,
                "directly_open_url": bool(start_url) and not resume,
                "initial_actions": initial_actions,
                "enable_signal_handler": False,
                "max_failures": 3,
                "max_actions_per_step": _MAX_ACTIONS_PER_STEP_LOCAL,
                "max_history_items": _MAX_HISTORY_ITEMS_LOCAL,
                "max_clickable_elements_length": dom_budget,
                "flash_mode": True,
                "use_judge": False,
                "include_tool_call_examples": False,
                "enable_planning": False,
                "loop_detection_enabled": True,
                "loop_detection_window": 8,
                "injected_agent_state": injected_state,
                "use_thinking": False,
            }

            handle.agent = Agent(**agent_kwargs)

            logger.info(
                "Browser Use agent starting runId=%s resume=%s url=%s query=%s provider=%s vision=%s dom_budget=%s",
                run_id,
                resume,
                start_url,
                intent.search_query,
                get_llm_provider(),
                False,
                dom_budget,
            )

            async def thinking_heartbeat() -> None:
                ticks = 0
                while not handle.cancelled and not first_step.is_set():
                    await asyncio.sleep(12)
                    if first_step.is_set() or handle.cancelled:
                        return
                    ticks += 1
                    await send_json(
                        AgentSyncMessage(
                            type="AGENT_SYNC",
                            runId=run_id,
                            phase="thinking",
                            url=start_url or "",
                            title="",
                            step=0,
                    actionSummary=(
                        "Still observing page (waiting on local LLM)…"
                        if get_llm_provider() == "llamacpp" and ticks < 4
                        else (
                            "Still observing page (waiting on LLM)…"
                            if ticks < 3
                            else "Still waiting on LLM — first step can take a while on local models…"
                        )
                    ),
                        ).model_dump(by_alias=True, exclude_none=True),
                    )

            heartbeat_task = asyncio.create_task(thinking_heartbeat())
            run_task = asyncio.create_task(handle.agent.run(max_steps=MAX_BROWSER_USE_STEPS))
            first_step_timeout = (
                _FIRST_STEP_TIMEOUT_LOCAL_SEC
                if get_llm_provider() == "llamacpp"
                else _FIRST_STEP_TIMEOUT_SEC
            )
            try:
                try:
                    await asyncio.wait_for(first_step.wait(), timeout=first_step_timeout)
                except asyncio.TimeoutError:
                    logger.error(
                        "Browser Use stalled before first step runId=%s resume=%s provider=%s",
                        run_id,
                        resume,
                        get_llm_provider(),
                    )
                    handle.cancelled = True
                    tool_state.pause_requested = True
                    run_task.cancel()
                    try:
                        await run_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    provider = get_llm_provider()
                    if provider == "llamacpp":
                        stall_message = (
                            "Local llama.cpp model took too long on the first step "
                            f"(>{int(first_step_timeout)}s). Keep http://127.0.0.1:3000 open, "
                            "Cancel, then start a new run — or set LLM_PROVIDER=openrouter for a faster cloud model."
                        )
                    elif provider == "openrouter":
                        stall_message = (
                            "OpenRouter agent stalled before the first step. "
                            "Cancel and retry, or check OPENROUTER_API_KEY / model."
                        )
                    else:
                        stall_message = (
                            "Agent stalled while observing the page (often rate limit "
                            "or page too large). Cancel, open http://127.0.0.1:3000, and start "
                            "a new run — or wait for quota reset."
                        )
                    self._run_manager.wait_for_user(session)
                    await send_json(
                        RunWaitingForUserMessage(
                            type="RUN_WAITING_FOR_USER",
                            runId=run_id,
                            message=stall_message,
                        ).model_dump(by_alias=True, exclude_none=True),
                    )
                    return

                await run_task
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            if handle.cancelled:
                return

            await self._finish_run(send_json, session, tool_state)

        except InterruptedError:
            if handle.cancelled:
                return
            await self._finish_run(send_json, session, tool_state)

        except asyncio.CancelledError:
            logger.info("Browser Use run cancelled runId=%s", run_id)
            raise

        except Exception as error:
            logger.exception("Browser Use run failed runId=%s", run_id)
            message = str(error)
            lowered = message.lower()
            if "rate_limit" in lowered or "tokens per day" in lowered or "tpd" in lowered:
                message = (
                    "Browser agent hit Groq rate limits (daily/minute token cap). "
                    "Wait for the quota reset, switch LLM_PROVIDER=llamacpp, or upgrade Groq. "
                    f"Details: {error}"
                )
            elif "connection" in lowered or "connect" in lowered or "refused" in lowered:
                if get_llm_provider() == "llamacpp":
                    message = (
                        "llama.cpp server is not reachable. Start llama-server "
                        "(see scripts/start-llamacpp.ps1), then retry. "
                        f"Details: {error}"
                    )
                elif get_llm_provider() == "openrouter":
                    message = (
                        "OpenRouter connection failed. Check OPENROUTER_API_KEY / network. "
                        f"Details: {error}"
                    )
                else:
                    message = f"Browser agent LLM connection failed: {error}"
            elif "request too large" in lowered or "413" in message:
                message = (
                    "Browser agent failed: page context too large for the LLM. "
                    "Prefer fake-store (http://127.0.0.1:3000) or a smaller page."
                )
            self._run_manager.fail_run(session, message)
            await send_json(
                RunErrorMessage(
                    type="RUN_ERROR",
                    runId=run_id,
                    message=message,
                ).model_dump(by_alias=True, exclude_none=True),
            )
            await self.cancel_run(run_id, cleanup=True)

    async def _finish_run(self, send_json: SendJson, session: RunSession, tool_state) -> None:
        run_id = session.run_id

        if tool_state.payment_proposal is not None:
            self._run_manager.request_payment_confirmation(
                session,
                tool_state.payment_proposal,
            )
            await send_json(
                PaymentLinkConfirmationMessage(
                    type="PAYMENT_LINK_CONFIRMATION_REQUIRED",
                    runId=run_id,
                    proposal=tool_state.payment_proposal,
                    message="Review and confirm payment link creation.",
                ).model_dump(by_alias=True, exclude_none=True),
            )
            return

        if tool_state.completion_summary:
            self._run_manager.complete_run(session)
            await send_json(
                RunCompleteMessage(
                    type="RUN_COMPLETE",
                    runId=run_id,
                    message=tool_state.completion_summary,
                ).model_dump(by_alias=True, exclude_none=True),
            )
            await self.cancel_run(run_id, cleanup=True)
            return

        if tool_state.pause_requested:
            message = tool_state.handoff_message or "Please complete the required step, then resume."
            self._run_manager.wait_for_user(session)
            await send_json(
                RunWaitingForUserMessage(
                    type="RUN_WAITING_FOR_USER",
                    runId=run_id,
                    message=message,
                ).model_dump(by_alias=True, exclude_none=True),
            )
            return

        # Agent stopped without explicit completion — hand off instead of
        # treating a product selection alone as success.
        if tool_state.selected_product_title:
            message = (
                tool_state.last_reasoning
                or (
                    f"Selected '{tool_state.selected_product_title}' but checkout "
                    "was not finished. Open /cart → /checkout or resume."
                )
            )
            self._run_manager.wait_for_user(session)
            await send_json(
                RunWaitingForUserMessage(
                    type="RUN_WAITING_FOR_USER",
                    runId=run_id,
                    message=message,
                ).model_dump(by_alias=True, exclude_none=True),
            )
            return

        self._run_manager.wait_for_user(session)
        await send_json(
            RunWaitingForUserMessage(
                type="RUN_WAITING_FOR_USER",
                runId=run_id,
                message=(
                    "Agent stopped before verifying cart/checkout. "
                    "Please continue manually or resume after adjusting the page."
                ),
            ).model_dump(by_alias=True, exclude_none=True),
        )

    @staticmethod
    def _is_heavy_commerce_url(url: str | None) -> bool:
        if not url:
            return False
        host = (urlparse(url).hostname or "").lower()
        return any(marker in host for marker in _HEAVY_SITE_MARKERS)

    def _create_browser_session(self) -> BrowserSession:
        cdp_url = get_browser_use_cdp_url()
        # Without CDP the agent launches a separate browser — not the user's extension tab.
        # Prefer a visible window for demos when headless would hide that mismatch.
        headless = BROWSER_USE_HEADLESS if not cdp_url else None
        if not cdp_url:
            logger.warning(
                "BROWSER_USE_CDP_URL is not set — Browser Use will launch its OWN browser "
                "(not your Chrome tab / overlay). For stock-like accuracy + overlay sync: "
                "chrome.exe --remote-debugging-port=9222 then "
                "BROWSER_USE_CDP_URL=http://127.0.0.1:9222"
            )
            if headless:
                logger.warning(
                    "BROWSER_USE_HEADLESS=true with no CDP — agent runs invisibly in a "
                    "separate browser. Set BROWSER_USE_HEADLESS=false or attach CDP."
                )
        logger.info(
            "Browser Use session cdp=%s headless=%s",
            cdp_url or "local-launch",
            headless if headless is not None else "n/a",
        )
        return BrowserSession(
            cdp_url=cdp_url,
            headless=headless,
            keep_alive=True,
            highlight_elements=False,
            dom_highlight_elements=False,
        )

    @staticmethod
    async def _read_cart_count(browser_session: BrowserSession | None) -> int | None:
        return await read_cart_count(browser_session)

    @staticmethod
    def _resolve_start_navigation(start_url: str, intent: ShoppingIntent) -> str:
        """Prefer a direct search URL on known demo storefronts."""
        parsed = urlparse(start_url)
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1"} and intent.search_query:
            return f"{parsed.scheme}://{parsed.netloc}/search?q={quote(intent.search_query)}"
        return start_url

    @staticmethod
    def _build_task(task: str, *, intent: ShoppingIntent, resume: bool) -> str:
        """Build a concise shopping task for the OSS browser-use Agent."""
        intent_block = intent.prompt_block()

        if resume:
            return (
                f"RESUME after user handoff. Task: {task.strip()}\n"
                f"{intent_block}\n"
                f"Re-observe. If wrong page, search exactly: {intent.search_query}\n"
                "Low confidence → request_user_handoff."
            )

        return (
            f"Task: {task.strip()}\n"
            f"{intent_block}\n"
            f"1) Open/search EXACTLY: {intent.search_query}\n"
            "2) Pick the best matching in-stock product (price + rating).\n"
            "3) Click Add to cart, then mark_shopping_complete once cart has it.\n"
            "4) request_user_handoff for login/OTP/CAPTCHA."
        )

    async def _emit_agent_sync(
        self,
        send_json: SendJson,
        run_id: str,
        browser_state: BrowserStateSummary,
        agent_output: AgentOutput,
        step_number: int,
        *,
        action_override: str | None = None,
    ) -> None:
        cursor = None
        highlight = None

        try:
            elements = AgentOutput.get_interacted_element(
                agent_output,
                browser_state.dom_state.selector_map,
            )
            if elements:
                element = next((item for item in elements if item is not None), None)
                if element:
                    rect = viewport_rect_from_interacted(
                        element,
                        browser_state,
                        browser_state.dom_state.selector_map,
                    )
                    if rect and rect.width > 0 and rect.height > 0:
                        highlight = {
                            "x": rect.x,
                            "y": rect.y,
                            "width": rect.width,
                            "height": rect.height,
                        }
                        cursor = {
                            "x": rect.x + rect.width / 2,
                            "y": rect.y + rect.height / 2,
                        }
        except Exception:
            logger.debug("Overlay bounds unavailable runId=%s", run_id)

        await send_json(
            AgentSyncMessage(
                type="AGENT_SYNC",
                runId=run_id,
                phase="acting",
                url=browser_state.url,
                title=browser_state.title,
                step=step_number,
                actionSummary=action_override or self._summarize_output(agent_output),
                cursor=cursor,
                highlight=highlight,
            ).model_dump(by_alias=True, exclude_none=True),
        )

    @staticmethod
    def _summarize_output(agent_output: AgentOutput) -> str:
        if not agent_output.action:
            return "Observing page"
        labels: list[str] = []
        for action in agent_output.action[:3]:
            if action is None:
                continue
            dumped = action.model_dump(exclude_none=True)
            if not dumped:
                continue
            name = next(iter(dumped.keys()))
            labels.append(name.replace("_", " "))
        return ", ".join(labels) if labels else "Acting"
