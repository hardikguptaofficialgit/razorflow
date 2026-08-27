"""WebSocket integration tests for store DOM executor (LLM mocked)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.bridge_server import app  # noqa: E402
from core.protocol import (  # noqa: E402
    ClickElementStep,
    NavigateUrlStep,
    PlannerChunkOutput,
)

HOME_CONTEXT = {
    "title": "Razorflow Market",
    "url": "http://localhost:3000/",
    "elements": [],
    "products": [],
}

SEARCH_CONTEXT = {
    "title": "Search",
    "url": "http://localhost:3000/search?q=shampoo",
    "elements": [
        {
            "index": 1,
            "role": "button",
            "tag": "button",
            "text": "Add to cart",
            "placeholder": "",
            "ariaLabel": "",
        },
        {
            "index": 2,
            "role": "link",
            "tag": "a",
            "text": "Cart",
            "placeholder": "",
            "ariaLabel": "Cart, 0 items",
        },
    ],
    "products": [
        {
            "title": "Head & Shoulders Anti-Dandruff Shampoo 340ml",
            "priceText": "₹349",
            "addToCartElementIndex": 1,
            "elementIndex": 1,
        },
    ],
}

SEARCH_CONTEXT_AFTER_ADD = {
    **SEARCH_CONTEXT,
    "elements": [
        SEARCH_CONTEXT["elements"][0],
        {
            **SEARCH_CONTEXT["elements"][1],
            "ariaLabel": "Cart, 1 items",
        },
    ],
}

CHECKOUT_CONTEXT = {
    "title": "Checkout",
    "url": "http://localhost:3000/checkout",
    "elements": [],
    "products": [],
}

CART_CONTEXT = {
    "title": "Cart",
    "url": "http://localhost:3000/cart",
    "elements": [
        {
            "index": 1,
            "role": "link",
            "tag": "a",
            "text": "Proceed to checkout",
            "placeholder": "",
            "ariaLabel": "Proceed to checkout",
        },
    ],
    "products": [],
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _recv(websocket) -> dict:
    return json.loads(websocket.receive_text())


def test_store_dom_run_search_add_cart_flow(client: TestClient) -> None:
    """Home → search → add to cart → open cart (mocked LLM planner)."""
    llm_responses = [
        PlannerChunkOutput(
            steps=[
                NavigateUrlStep(
                    action="navigate_url",
                    url="http://localhost:3000/search?q=shampoo",
                ),
            ],
            terminal="continue",
        ),
        PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role="button",
                    element_index=1,
                    match_text="Add to cart",
                ),
            ],
            terminal="continue",
        ),
        PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role="link",
                    element_index=2,
                    match_text="Cart",
                ),
            ],
            terminal="continue",
        ),
        PlannerChunkOutput(
            steps=[
                ClickElementStep(
                    action="click_element",
                    role="link",
                    element_index=1,
                    match_text="Proceed to checkout",
                ),
            ],
            terminal="continue",
        ),
    ]

    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=False):
        with patch("core.bridge_server.is_agent_runtime_v2_enabled", return_value=False):
            with patch(
                "core.agent_loop.plan_with_llm",
                side_effect=llm_responses,
            ):
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json(
                        {
                            "type": "START_RUN",
                            "runId": "run-int-1",
                            "task": "Buy the cheapest shampoo under 500",
                            "url": "http://localhost:3000/",
                            "pageContext": HOME_CONTEXT,
                        },
                    )

                    mode = _recv(websocket)
                    assert mode["type"] == "EXECUTOR_MODE"
                    assert mode["mode"] == "extension_dom"

                    step1 = _recv(websocket)
                    assert step1["type"] == "NEXT_ACTION"
                    assert step1["steps"][0]["action"] == "navigate_url"

                    websocket.send_json(
                        {
                            "type": "ACTION_RESULT",
                            "runId": "run-int-1",
                            "step": step1["steps"][0],
                            "success": True,
                            "verified": True,
                            "pageContext": SEARCH_CONTEXT,
                        },
                    )

                    step2 = _recv(websocket)
                    assert step2["type"] == "NEXT_ACTION"
                    assert step2["steps"][0]["action"] == "click_element"

                    websocket.send_json(
                        {
                            "type": "ACTION_RESULT",
                            "runId": "run-int-1",
                            "step": step2["steps"][0],
                            "success": True,
                            "verified": True,
                            "pageContext": SEARCH_CONTEXT_AFTER_ADD,
                        },
                    )

                    step3 = _recv(websocket)
                    assert step3["type"] == "NEXT_ACTION"
                    assert step3["steps"][0]["action"] == "navigate_url"
                    assert "checkout" in step3["steps"][0]["url"].lower()

                    websocket.send_json(
                        {
                            "type": "ACTION_RESULT",
                            "runId": "run-int-1",
                            "step": step3["steps"][0],
                            "success": True,
                            "verified": True,
                            "pageContext": CHECKOUT_CONTEXT,
                        },
                    )

                    done = _recv(websocket)
                    assert done["type"] == "RUN_COMPLETE"


def test_start_run_accepts_homepage_sized_page_context(client: TestClient) -> None:
    elements = [
        {
            "index": index,
            "role": "button",
            "tag": "button",
            "text": f"Add to cart {index}",
            "placeholder": "",
            "ariaLabel": "",
        }
        for index in range(1, 57)
    ]
    products = [
        {
            "title": f"Product {index}",
            "priceText": f"₹{index * 10}",
            "addToCartElementIndex": index,
            "elementIndex": index,
        }
        for index in range(1, 13)
    ]

    navigate = PlannerChunkOutput(
        steps=[
            NavigateUrlStep(
                action="navigate_url",
                url="http://localhost:3000/search?q=shampoo",
            ),
        ],
        terminal="continue",
    )

    with patch("core.bridge_server.is_browser_use_executor_enabled", return_value=False):
        with patch("core.bridge_server.is_agent_runtime_v2_enabled", return_value=False):
            with patch("core.agent_loop.plan_with_llm", return_value=navigate):
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json(
                        {
                            "type": "START_RUN",
                            "runId": "run-large-context",
                            "task": "Buy the cheapest shampoo under 500",
                            "url": "http://localhost:3000/",
                            "pageContext": {
                                "title": "Razorflow Market",
                                "url": "http://localhost:3000/",
                                "elements": elements,
                                "products": products,
                            },
                        },
                    )

                    mode = _recv(websocket)
                    assert mode["type"] == "EXECUTOR_MODE"
                    next_action = _recv(websocket)
                    assert next_action["type"] == "NEXT_ACTION"
                    assert next_action["steps"][0]["action"] == "navigate_url"
