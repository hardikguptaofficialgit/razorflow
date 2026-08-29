"""Tests for Razorpay MCP response normalization."""

from __future__ import annotations

import json

from policy.razorpay_mcp_client import RazorpayMcpClient


def test_structured_content_url_is_not_hidden_by_text_payload() -> None:
    client = RazorpayMcpClient()
    result = {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"id": "plink_test", "status": "created"}),
            },
        ],
        "structuredContent": {
            "short_url": "https://rzp.io/rzp/test-link",
        },
    }

    payload = client._extract_tool_payload(result)

    assert client._extract_payment_url(payload) == "https://rzp.io/rzp/test-link"
