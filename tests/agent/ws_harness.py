"""Shared WebSocket + Playwright harness for agent E2E tests."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
HARNESS = (ROOT / "tests" / "agent" / "general_web_harness.js").read_text(encoding="utf-8")
WS_URL = "ws://127.0.0.1:8765/ws"
WS_CONNECT_KWARGS = {
    "open_timeout": 30,
    "ping_interval": 30,
    "ping_timeout": 300,
    "close_timeout": 30,
}
EXTRACT_JS = f"() => {{ {HARNESS} return extractPageContext(); }}"
EXECUTE_JS = f"async (step) => {{ {HARNESS} return await executeStep(step); }}"


@dataclass
class WsRunResult:
    run_id: str
    terminal: str = ""
    message: str = ""
    steps: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)
    action_results: list[dict[str, Any]] = field(default_factory=list)
    ws_alive: bool = True


async def run_ws_task(
    page: Any,
    task: str,
    *,
    max_steps: int = 24,
    step_timeout_s: int = 180,
    before_execute: Callable[[dict[str, Any], int], Any] | None = None,
    after_execute: Callable[[dict[str, Any], dict[str, Any], int], Any] | None = None,
) -> WsRunResult:
    import websockets

    run_id = f"ws-{uuid.uuid4().hex[:8]}"
    result = WsRunResult(run_id=run_id)
    terminal_types = {
        "RUN_COMPLETE",
        "RUN_ERROR",
        "RUN_WAITING_FOR_USER",
        "RUN_NEEDS_CLARIFICATION",
    }

    async def _evaluate(js: str, arg: Any = None) -> Any:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                if arg is None:
                    return await page.evaluate(js)
                return await page.evaluate(js, arg)
            except Exception as exc:
                last_exc = exc
                if "Execution context was destroyed" not in str(exc) or attempt >= 2:
                    raise
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=8000)
                except Exception:
                    pass
                await page.wait_for_timeout(400)
        if last_exc:
            raise last_exc
        return None

    async with websockets.connect(WS_URL, **WS_CONNECT_KWARGS) as ws:
        page_context = await _evaluate(EXTRACT_JS)
        await ws.send(
            json.dumps(
                {
                    "type": "START_RUN",
                    "runId": run_id,
                    "task": task,
                    "pageContext": page_context,
                }
            )
        )

        deadline = asyncio.get_event_loop().time() + step_timeout_s * max_steps
        while asyncio.get_event_loop().time() < deadline and result.steps < max_steps:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=step_timeout_s)
            except TimeoutError:
                result.terminal = "RECV_TIMEOUT"
                result.message = "WebSocket recv timeout"
                break

            msg = json.loads(raw)
            result.messages.append(msg)
            mtype = msg.get("type", "")

            if mtype == "NEXT_ACTION" and msg.get("runId") == run_id:
                result.steps += 1
                steps = msg.get("steps") or []
                for step in steps:
                    if before_execute:
                        await before_execute(step, result.steps)
                    exec_result = await _evaluate(EXECUTE_JS, step)
                    if after_execute:
                        await after_execute(step, exec_result, result.steps)
                    result.action_results.append(
                        {"step": step, "result": exec_result, "turn": result.steps}
                    )
                    await page.wait_for_timeout(200)
                    page_context = await _evaluate(EXTRACT_JS)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "ACTION_RESULT",
                                "runId": run_id,
                                "step": step,
                                "success": bool(exec_result.get("success")),
                                "verified": exec_result.get("verified"),
                                "error": exec_result.get("error"),
                                "pageContext": page_context,
                            }
                        )
                    )
                continue

            if mtype in terminal_types and msg.get("runId") == run_id:
                result.terminal = mtype
                result.message = msg.get("message") or ""
                break

        try:
            await ws.send(json.dumps({"type": "CANCEL_RUN", "runId": run_id}))
        except Exception:
            result.ws_alive = False

    return result
