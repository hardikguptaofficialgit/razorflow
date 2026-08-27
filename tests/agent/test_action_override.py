"""Tests for deterministic Browser Use action overrides."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from core.action_override import (  # noqa: E402
    force_click_add_to_cart,
    should_skip_force,
    summarize_actions,
)
from core.product_compare import NormalizedProduct  # noqa: E402
from core.protocol import PageProductSummary  # noqa: E402


class _FakeAction:
    def __init__(self, data: dict):
        self._data = data

    def model_dump(self, exclude_unset: bool = True) -> dict:
        return dict(self._data)

    def get_index(self) -> int | None:
        click = self._data.get("click") or {}
        return click.get("index")

    @classmethod
    def model_validate(cls, data: dict) -> "_FakeAction":
        return cls(data)


def _winner(index: int = 42) -> NormalizedProduct:
    raw = PageProductSummary(
        title="Sunsilk Shampoo",
        price_text="289",
        rating_text="",
        availability_text="In stock",
        element_index=index,
        add_to_cart_element_index=index,
    )
    return NormalizedProduct(
        title="Sunsilk Shampoo",
        price=289.0,
        rating=None,
        available=True,
        element_index=index,
        add_to_cart_element_index=index,
        raw=raw,
    )


def test_force_click_replaces_scroll_action() -> None:
    output = SimpleNamespace(action=[_FakeAction({"scroll": {"down": True}})])
    forced = force_click_add_to_cart(output, _winner(17))  # type: ignore[arg-type]
    assert forced == 17
    assert output.action[0].model_dump() == {"click": {"index": 17}}


def test_force_click_skips_handoff() -> None:
    output = SimpleNamespace(
        action=[_FakeAction({"request_user_handoff": {"reason": "login"}})],
    )
    assert should_skip_force(output) is True  # type: ignore[arg-type]
    assert force_click_add_to_cart(output, _winner()) is None  # type: ignore[arg-type]


def test_force_click_skips_navigate() -> None:
    output = SimpleNamespace(
        action=[_FakeAction({"navigate": {"url": "http://127.0.0.1:3000"}})],
    )
    assert should_skip_force(output) is True  # type: ignore[arg-type]
    assert force_click_add_to_cart(output, _winner()) is None  # type: ignore[arg-type]


def test_summarize_actions() -> None:
    output = SimpleNamespace(
        action=[_FakeAction({"click": {"index": 3}})],
    )
    assert "click" in summarize_actions(output)  # type: ignore[arg-type]
