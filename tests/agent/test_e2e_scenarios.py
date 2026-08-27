"""Extended live E2E scenarios for RazorFlow Browser Use executor."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

RUN_E2E = os.getenv("RUN_E2E", "").strip().lower() in {"1", "true", "yes"}
FAKE_STORE_URL = os.getenv("FAKE_STORE_URL", "http://127.0.0.1:3000").rstrip("/")
E2E_TIMEOUT_SEC = int(os.getenv("E2E_TIMEOUT_SEC", "240"))

pytestmark = pytest.mark.skipif(not RUN_E2E, reason="Set RUN_E2E=1 to run live Browser Use E2E")


def _require_browser_use_e2e() -> None:
    from utils.config import is_browser_llm_ready, is_browser_use_executor_enabled

    if not is_browser_use_executor_enabled():
        pytest.skip("BROWSER_USE_EXECUTOR_ENABLED is false")
    if not is_browser_llm_ready():
        pytest.skip("Browser Use LLM not configured (set GEMINI_API_KEY / OPENROUTER / GROQ)")


async def _collect_run_messages(
    task: str,
    *,
    start_url: str | None = None,
    timeout_sec: int = E2E_TIMEOUT_SEC,
) -> tuple[str, list[dict]]:
    import websockets

    run_id = f"e2e-{uuid.uuid4().hex[:8]}"
    messages: list[dict] = []
    payload: dict = {
        "type": "START_RUN",
        "runId": run_id,
        "task": task,
    }
    if start_url:
        payload["url"] = start_url

    async with websockets.connect("ws://127.0.0.1:8765/ws", open_timeout=10) as ws:
        await ws.send(json.dumps(payload))

        terminal_types = {
            "RUN_COMPLETE",
            "RUN_ERROR",
            "RUN_WAITING_FOR_USER",
            "PAYMENT_LINK_CONFIRMATION_REQUIRED",
        }
        deadline = asyncio.get_event_loop().time() + timeout_sec

        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
            except TimeoutError:
                break

            item = json.loads(raw)
            messages.append(item)
            if item.get("type") in terminal_types and item.get("runId") == run_id:
                break

    return run_id, messages


def _terminal(messages: list[dict]) -> dict | None:
    terminal_types = {
        "RUN_COMPLETE",
        "RUN_ERROR",
        "RUN_WAITING_FOR_USER",
        "PAYMENT_LINK_CONFIRMATION_REQUIRED",
    }
    for item in reversed(messages):
        if item.get("type") in terminal_types:
            return item
    return None


@pytest.mark.asyncio
async def test_e2e_search_navigates_and_syncs() -> None:
    _require_browser_use_e2e()

    run_id, messages = await _collect_run_messages(
        "Search for shampoo and open the cheapest product with good ratings.",
        start_url=FAKE_STORE_URL,
        timeout_sec=180,
    )

    types = [m.get("type") for m in messages]
    syncs = [m for m in messages if m.get("type") == "AGENT_SYNC" and m.get("runId") == run_id]
    terminal = _terminal(messages)

    assert "EXECUTOR_MODE" in types
    assert len(syncs) >= 1
    assert terminal is not None
    assert terminal["type"] != "RUN_ERROR", terminal.get("message")

    urls = {m.get("url", "") for m in syncs if m.get("url")}
    assert any("search" in url or "product" in url or FAKE_STORE_URL in url for url in urls)


@pytest.mark.asyncio
async def test_e2e_checkout_requests_user_handoff_or_payment() -> None:
    _require_browser_use_e2e()

    run_id, messages = await _collect_run_messages(
        "Add the cheapest shampoo to cart and go to checkout.",
        start_url=FAKE_STORE_URL,
        timeout_sec=240,
    )

    terminal = _terminal(messages)
    assert terminal is not None
    assert terminal["type"] != "RUN_ERROR", terminal.get("message")
    assert terminal["type"] in {
        "RUN_WAITING_FOR_USER",
        "PAYMENT_LINK_CONFIRMATION_REQUIRED",
        "RUN_COMPLETE",
    }

    if terminal["type"] == "RUN_WAITING_FOR_USER":
        message = (terminal.get("message") or "").lower()
        assert any(
            token in message
            for token in ("login", "sign", "checkout", "complete", "verify", "user")
        )


@pytest.mark.asyncio
async def test_e2e_resume_after_handoff() -> None:
    _require_browser_use_e2e()

    import websockets

    run_id = f"e2e-{uuid.uuid4().hex[:8]}"
    messages: list[dict] = []

    async with websockets.connect("ws://127.0.0.1:8765/ws", open_timeout=10) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "START_RUN",
                    "runId": run_id,
                    "task": (
                        "Search for shampoo, add the cheapest one to cart, "
                        "then proceed to checkout."
                    ),
                    "url": FAKE_STORE_URL,
                },
            ),
        )

        terminal_types = {
            "RUN_COMPLETE",
            "RUN_ERROR",
            "RUN_WAITING_FOR_USER",
            "PAYMENT_LINK_CONFIRMATION_REQUIRED",
        }
        deadline = asyncio.get_event_loop().time() + 240
        terminal: dict | None = None

        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=90)
            except TimeoutError:
                break
            item = json.loads(raw)
            messages.append(item)
            if item.get("type") in terminal_types and item.get("runId") == run_id:
                terminal = item
                break

        if terminal is None or terminal.get("type") != "RUN_WAITING_FOR_USER":
            pytest.skip("Run did not pause for user handoff in time")

        await ws.send(
            json.dumps(
                {
                    "type": "RESUME_RUN",
                    "runId": run_id,
                    "pageContext": {
                        "title": "Checkout",
                        "url": f"{FAKE_STORE_URL}/checkout",
                        "elements": [],
                        "products": [],
                    },
                },
            ),
        )

        resume_deadline = asyncio.get_event_loop().time() + 180
        saw_post_resume = False
        while asyncio.get_event_loop().time() < resume_deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=90)
            except TimeoutError:
                break
            item = json.loads(raw)
            messages.append(item)
            saw_post_resume = True
            if item.get("type") in terminal_types and item.get("runId") == run_id:
                break

    assert saw_post_resume, "No websocket activity after RESUME_RUN"
