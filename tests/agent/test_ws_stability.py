"""Prove WebSocket stays alive during long LLM planning (event loop not blocked)."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

WS_URL = "ws://127.0.0.1:8765/ws"
HARNESS = (ROOT / "tests" / "agent" / "general_web_harness.js").read_text(encoding="utf-8")
EXTRACT = f"() => {{ {HARNESS} return extractPageContext(); }}"


@pytest.mark.asyncio
async def test_websocket_survives_long_start_run() -> None:
    import websockets
    from playwright.async_api import async_playwright

    run_id = f"ws-stability-{uuid.uuid4().hex[:8]}"
    pings_received = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        fixture = ROOT / "tests" / "agent" / "fixtures" / "target_resolution_page.html"
        await page.goto(fixture.as_uri(), wait_until="domcontentloaded")
        ctx = await page.evaluate(EXTRACT)

        async with websockets.connect(
            WS_URL,
            open_timeout=30,
            ping_interval=10,
            ping_timeout=120,
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "START_RUN",
                        "runId": run_id,
                        "task": "add Galaxy Buds FE to my cart",
                        "pageContext": ctx,
                    }
                )
            )

            got_next = False
            deadline = asyncio.get_event_loop().time() + 120
            while asyncio.get_event_loop().time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                except TimeoutError:
                    pings_received += 1
                    continue
                msg = json.loads(raw)
                if msg.get("type") == "NEXT_ACTION":
                    got_next = True
                    break
                if msg.get("type") in {"RUN_ERROR", "RUN_COMPLETE"}:
                    break

            assert got_next, f"No NEXT_ACTION within deadline (ping waits={pings_received})"
        await browser.close()
