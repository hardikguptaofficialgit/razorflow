"""Single entry point for Razorpay MCP payment-link creation."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from utils.config import (
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_MCP_ENDPOINT,
)

logger = logging.getLogger(__name__)


class RazorpayMcpError(Exception):
    """Raised when Razorpay MCP communication fails."""


@dataclass(frozen=True)
class PaymentLinkMcpResult:
    payment_link_url: str
    amount_paise: int
    currency: str
    description: str
    reference_id: str
    raw: dict[str, Any]


class RazorpayMcpClient:
    """Minimal MCP streamable-HTTP client for Razorpay payment-link tools."""

    def __init__(self) -> None:
        self._session_id: str | None = None
        self._request_id = 0

    def _auth_header(self) -> str:
        if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            raise RazorpayMcpError(
                "Razorpay test-mode credentials are not configured.",
            )

        token = base64.b64encode(
            f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}".encode(),
        ).decode()
        return f"Basic {token}"

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                RAZORPAY_MCP_ENDPOINT,
                headers=headers,
                json=payload,
            )

        if response.headers.get("mcp-session-id"):
            self._session_id = response.headers["mcp-session-id"]

        body = self._parse_response_body(response)
        if "error" in body:
            raise RazorpayMcpError(str(body["error"]))

        return body.get("result")

    def _parse_response_body(self, response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        text = response.text.strip()

        if response.status_code >= 400:
            raise RazorpayMcpError(
                f"MCP HTTP {response.status_code}: {text[:240]}",
            )

        if "text/event-stream" in content_type:
            return self._parse_sse_json(text)

        if not text:
            return {}

        parsed = json.loads(text)
        if isinstance(parsed, list):
            for item in reversed(parsed):
                if isinstance(item, dict) and "result" in item:
                    return item
                if isinstance(item, dict) and "error" in item:
                    return item
            return parsed[-1] if parsed else {}

        return parsed if isinstance(parsed, dict) else {"result": parsed}

    def _parse_sse_json(self, text: str) -> dict[str, Any]:
        for line in reversed(text.splitlines()):
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if not data or data == "[DONE]":
                continue
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                return parsed
        raise RazorpayMcpError("MCP SSE response did not contain JSON data.")

    async def initialize(self) -> None:
        await self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "razorflow-agent", "version": "0.1.0"},
            },
        )

    async def create_payment_link(
        self,
        *,
        amount_paise: int,
        currency: str,
        description: str,
        reference_id: str,
    ) -> PaymentLinkMcpResult:
        await self.initialize()

        result = await self._rpc(
            "tools/call",
            {
                "name": "create_payment_link",
                "arguments": {
                    "amount": amount_paise,
                    "currency": currency,
                    "description": description,
                    "reference_id": reference_id,
                },
            },
        )

        payload = self._extract_tool_payload(result)
        payment_url = self._extract_payment_url(payload)
        if not payment_url:
            raise RazorpayMcpError("MCP response did not include a payment link URL.")

        return PaymentLinkMcpResult(
            payment_link_url=payment_url,
            amount_paise=amount_paise,
            currency=currency,
            description=description,
            reference_id=reference_id,
            raw=payload,
        )

    def _extract_tool_payload(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise RazorpayMcpError("Unexpected MCP tool result shape.")

        payloads: list[dict[str, Any]] = []
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    try:
                        parsed = json.loads(text)
                        if isinstance(parsed, dict):
                            payloads.append(parsed)
                    except json.JSONDecodeError:
                        if "http" in text:
                            payloads.append({"short_url": text.strip()})
        if "structuredContent" in result and isinstance(
            result["structuredContent"],
            dict,
        ):
            payloads.append(result["structuredContent"])

        if payloads:
            merged: dict[str, Any] = {}
            for payload in payloads:
                merged.update(payload)
            return merged

        return result

    def _extract_payment_url(self, payload: dict[str, Any]) -> str | None:
        preferred_keys = {"short_url", "payment_link_url", "url", "shortUrl"}

        def walk(value: Any, key: str = "") -> str | None:
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    if child_key in preferred_keys and isinstance(child_value, str):
                        if child_value.startswith(("http://", "https://")):
                            return child_value
                    found = walk(child_value, child_key)
                    if found:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = walk(child)
                    if found:
                        return found
            elif isinstance(value, str) and key in preferred_keys:
                match = re.search(r"https?://[^\s\"']+", value)
                if match:
                    return match.group(0)
            return None

        found = walk(payload)
        if found:
            return found

        text_blob = json.dumps(payload)
        match = re.search(r"https?://[^\s\"']+", text_blob)
        return match.group(0).rstrip(".,)") if match else None


razorpay_mcp_client = RazorpayMcpClient()
