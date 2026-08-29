"""Bridge routing tests for Agent Runtime V2."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.bridge_server import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_start_run_routes_to_v2_runtime(client: TestClient) -> None:
    v2_start = AsyncMock()
    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=True):
        with patch("core.bridge_server.is_agent_runtime_v2_enabled", return_value=True):
            with patch("agent_runtime.bridge.adapter.handle_start_run", v2_start):
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json(
                        {
                            "type": "START_RUN",
                            "runId": "run-v2-1",
                            "task": "Find shampoo",
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

    v2_start.assert_awaited_once()
