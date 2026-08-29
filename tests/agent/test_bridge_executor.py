"""Bridge server routing tests for Browser Use executor mode."""

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


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_reports_executor_mode(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "executorMode" in payload
    assert payload["executorMode"] in {"browser_use", "extension_dom"}


def test_start_run_routes_to_store_dom_planner(client: TestClient) -> None:
    dispatch_mock = AsyncMock()
    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=False):
        with patch("core.bridge_server.is_agent_runtime_v2_enabled", return_value=False):
            with patch("core.bridge_server._dispatch_next_chunk", dispatch_mock):
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json(
                        {
                            "type": "START_RUN",
                            "runId": "run-dom-1",
                            "task": "Find shampoo",
                            "url": "http://localhost:3000",
                            "pageContext": {
                                "title": "Home",
                                "url": "http://localhost:3000/",
                                "elements": [],
                                "products": [],
                            },
                        },
                    )
                    first = json.loads(websocket.receive_text())
                    assert first["type"] == "EXECUTOR_MODE"
                    assert first["mode"] == "extension_dom"

    dispatch_mock.assert_awaited_once()


def test_start_run_routes_to_browser_use_controller(client: TestClient) -> None:
    start_mock = AsyncMock()
    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=True):
        with patch("core.bridge_server.is_agent_runtime_v2_enabled", return_value=False):
            with patch("core.bridge_server.browser_use_controller.start_run", start_mock):
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json(
                        {
                            "type": "START_RUN",
                            "runId": "run-bridge-1",
                            "task": "Find shampoo",
                            "url": "http://localhost:3000",
                        },
                    )
                    first = json.loads(websocket.receive_text())
                    assert first["type"] == "EXECUTOR_MODE"
                    assert first["mode"] == "browser_use"

    start_mock.assert_awaited_once()
    args = start_mock.await_args
    assert args is not None
    session = args.args[1]
    assert session.run_id == "run-bridge-1"
    assert args.args[2] == "http://localhost:3000"


def test_action_result_ignored_in_executor_mode(client: TestClient) -> None:
    dispatch_mock = AsyncMock()
    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=True):
        with patch("core.bridge_server.is_agent_runtime_v2_enabled", return_value=False):
            with patch("core.bridge_server._dispatch_next_chunk", dispatch_mock):
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json(
                        {
                            "type": "ACTION_RESULT",
                            "runId": "run-bridge-2",
                            "step": {"action": "set_state", "state": "acting"},
                            "success": True,
                        },
                    )
                    websocket.send_json({"type": "PING_SHOULD_NOT_EXIST"})

    dispatch_mock.assert_not_awaited()


def test_cancel_run_calls_browser_use_cleanup(client: TestClient) -> None:
    cancel_mock = AsyncMock()
    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=True):
        with patch("core.bridge_server.is_agent_runtime_v2_enabled", return_value=False):
            with patch("core.bridge_server.browser_use_controller.cancel_run", cancel_mock):
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json(
                        {
                            "type": "CANCEL_RUN",
                            "runId": "run-bridge-3",
                        },
                    )

    cancel_mock.assert_awaited_once_with("run-bridge-3", cleanup=True)
