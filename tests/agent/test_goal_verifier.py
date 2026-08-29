"""Tests for nonsense task handling and verified completion."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.bridge_server import app  # noqa: E402
from core.goal_verifier import approve_completion  # noqa: E402
from core.protocol import (  # noqa: E402
    ActionHistoryEntry,
    ClickElementStep,
    NavigateUrlStep,
    PageContext,
    PageProductSummary,
    PlannerChunkOutput,
)
from core.run_manager import RunManager, RunSession  # noqa: E402
from core.task_interpretation import interpret_task  # noqa: E402


@pytest.mark.legacy
def test_wdwd_needs_clarification() -> None:
    interpretation = interpret_task("wdwd")
    assert interpretation.status == "needs_clarification"
    assert interpretation.actionable is False


def test_search_on_homepage_does_not_auto_complete() -> None:
    manager = RunManager()
    session = manager.start_run(
        "run-search",
        "search for wireless earbuds",
        PageContext(
            title="Home",
            url="http://localhost:3001/",
            elements=[],
            products=[],
        ),
    )
    interpretation = interpret_task(session.task)
    assert not approve_completion(session, interpretation.intent, source="test")


def test_search_completes_after_verified_navigation() -> None:
    session = RunSession(
        run_id="run-nav",
        task="search for wireless earbuds",
        latest_page_context=PageContext(
            title="Search",
            url="http://localhost:3001/search?q=earbuds",
            elements=[],
            products=[PageProductSummary(title="Buds", price_text="₹999")],
        ),
    )
    session.history.append(
        ActionHistoryEntry(
            step=NavigateUrlStep(
                action="navigate_url",
                url="http://localhost:3001/search?q=earbuds",
            ),
            success=True,
            verified=True,
        ),
    )
    session.verified_progress_count = 1
    session.milestones.add("verified_search")
    interpretation = interpret_task(session.task)
    assert approve_completion(session, interpretation.intent, source="test")


@pytest.mark.asyncio
async def test_wdwd_websocket_needs_clarification_not_complete() -> None:
    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=False):
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {
                    "type": "START_RUN",
                    "runId": "wdwd-run",
                    "task": "wdwd",
                    "pageContext": {
                        "title": "Home",
                        "url": "http://localhost:3001/",
                        "elements": [],
                        "products": [],
                    },
                },
            )
            msgs = [json.loads(ws.receive_text()) for _ in range(2)]
            types = [msg["type"] for msg in msgs]
            assert "EXECUTOR_MODE" in types
            assert "RUN_NEEDS_CLARIFICATION" in types
            assert "RUN_COMPLETE" not in types


def test_llm_complete_does_not_finish_without_verified_progress() -> None:
    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=False):
        with patch(
            "core.agent_loop.plan_with_llm",
            new_callable=AsyncMock,
            return_value=PlannerChunkOutput(steps=[], terminal="complete"),
        ):
            client = TestClient(app)
            with client.websocket_connect("/ws") as ws:
                ws.send_json(
                    {
                        "type": "START_RUN",
                        "runId": "no-fake-done",
                        "task": "search for wireless earbuds",
                        "pageContext": {
                            "title": "Home",
                            "url": "http://localhost:3001/",
                            "elements": [],
                            "products": [],
                        },
                    },
                )
                msgs: list[dict] = []
                for _ in range(6):
                    raw = ws.receive_text()
                    if raw is None:
                        break
                    item = json.loads(raw)
                    msgs.append(item)
                    if item.get("type") in {
                        "RUN_COMPLETE",
                        "RUN_WAITING_FOR_USER",
                        "RUN_NEEDS_CLARIFICATION",
                        "RUN_ERROR",
                        "NEXT_ACTION",
                    }:
                        break
                assert not any(msg.get("type") == "RUN_COMPLETE" for msg in msgs)
