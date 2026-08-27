"""Optional live E2E smoke test for Browser Use executor (requires configured BYO LLM)."""

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


pytestmark = pytest.mark.skipif(not RUN_E2E, reason="Set RUN_E2E=1 to run live Browser Use E2E")


def _require_browser_use_e2e() -> None:
    from utils.config import is_browser_llm_ready, is_browser_use_executor_enabled

    if not is_browser_use_executor_enabled():
        pytest.skip("BROWSER_USE_EXECUTOR_ENABLED is false")
    if not is_browser_llm_ready():
        pytest.skip("Browser Use LLM not configured (set GEMINI_API_KEY / OPENROUTER / GROQ)")


@pytest.mark.asyncio
async def test_browser_use_search_smoke() -> None:
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
                    "task": "Search for shampoo and open the cheapest product with good ratings.",
                    "url": FAKE_STORE_URL,
                },
            ),
        )

        deadline = asyncio.get_event_loop().time() + 180
        terminal_types = {
            "RUN_COMPLETE",
            "RUN_ERROR",
            "RUN_WAITING_FOR_USER",
            "PAYMENT_LINK_CONFIRMATION_REQUIRED",
        }

        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=45)
            except TimeoutError:
                break

            payload = json.loads(raw)
            messages.append(payload)
            if payload.get("type") in terminal_types and payload.get("runId") == run_id:
                break

    types = [item.get("type") for item in messages]
    assert "EXECUTOR_MODE" in types
    assert any(item.get("type") == "AGENT_SYNC" for item in messages if item.get("runId") == run_id)

    terminal = next(
        (item for item in reversed(messages) if item.get("type") in terminal_types),
        None,
    )
    assert terminal is not None, f"No terminal message. Got: {types}"
    assert terminal["type"] != "RUN_ERROR", terminal.get("message", "")
