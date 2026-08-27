"""Tests for voice intent classification."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.bridge_server import app
from voice.intent_classifier import classify_intent_locally


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("continue", "resume"),
        ("Resume please", "resume"),
    ],
)
def test_local_classifier_waiting_state(text: str, expected: str) -> None:
    assert classify_intent_locally(text, "waiting_for_user") == expected


def test_local_classifier_ambiguous_returns_none() -> None:
    assert classify_intent_locally("find cheapest shampoo", "waiting_for_user") is None


def test_local_classifier_idle_defaults_to_new_task() -> None:
    assert classify_intent_locally("continue", "idle") == "new_task"


def test_classify_intent_endpoint_short_resume() -> None:
    client = TestClient(app)
    response = client.post(
        "/voice/classify-intent",
        json={"text": "done", "runStatus": "waiting_for_user"},
    )
    assert response.status_code == 200
    assert response.json()["intent"] == "resume"


def test_classify_intent_endpoint_long_task() -> None:
    client = TestClient(app)
    response = client.post(
        "/voice/classify-intent",
        json={
            "text": "search for the cheapest shampoo under 500 rupees",
            "runStatus": "waiting_for_user",
        },
    )
    assert response.status_code == 200
    assert response.json()["intent"] == "new_task"
