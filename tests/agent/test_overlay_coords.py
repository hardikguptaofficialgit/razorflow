"""Tests for viewport coordinate conversion used by overlay sync."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-backend"))

from browser_use.browser.views import BrowserStateSummary, PageInfo  # noqa: E402
from browser_use.dom.views import (  # noqa: E402
    DOMInteractedElement,
    DOMRect,
    EnhancedAXNode,
    EnhancedDOMTreeNode,
    EnhancedSnapshotNode,
    NodeType,
    SerializedDOMState,
)
from core.overlay_coords import viewport_rect_from_interacted, viewport_rect_from_node  # noqa: E402


def _node(
    *,
    backend_id: int = 1,
    client: DOMRect | None = None,
    bounds: DOMRect | None = None,
) -> EnhancedDOMTreeNode:
    return EnhancedDOMTreeNode(
        node_id=backend_id,
        backend_node_id=backend_id,
        node_type=NodeType.ELEMENT_NODE,
        node_name="BUTTON",
        node_value="",
        attributes={"type": "button"},
        is_scrollable=False,
        is_visible=True,
        absolute_position=bounds,
        target_id="target-1",
        frame_id=None,
        session_id=None,
        content_document=None,
        shadow_root_type=None,
        shadow_roots=None,
        parent_node=None,
        children_nodes=None,
        ax_node=EnhancedAXNode(
            ax_node_id="ax-1",
            ignored=False,
            role="button",
            name="Add to cart",
            description=None,
            properties=None,
            child_ids=None,
        ),
        snapshot_node=EnhancedSnapshotNode(
            is_clickable=True,
            cursor_style="pointer",
            bounds=bounds,
            clientRects=client,
            scrollRects=None,
            computed_styles=None,
            paint_order=None,
            stacking_contexts=None,
        ),
    )


def _state(scroll_y: int = 400) -> BrowserStateSummary:
    return BrowserStateSummary(
        dom_state=SerializedDOMState(_root=None, selector_map={}),
        url="http://localhost:3000/search",
        title="Search",
        tabs=[],
        page_info=PageInfo(
            viewport_width=1280,
            viewport_height=800,
            page_width=1280,
            page_height=2400,
            scroll_x=0,
            scroll_y=scroll_y,
            pixels_above=scroll_y,
            pixels_below=2400 - scroll_y - 800,
            pixels_left=0,
            pixels_right=0,
        ),
    )


def test_prefers_client_rects_for_viewport_overlay() -> None:
    node = _node(
        bounds=DOMRect(x=100, y=500, width=80, height=32),
        client=DOMRect(x=100, y=100, width=80, height=32),
    )
    rect = viewport_rect_from_node(node, _state(scroll_y=400))
    assert rect is not None
    assert rect.x == 100
    assert rect.y == 100


def test_converts_document_bounds_using_scroll() -> None:
    node = _node(bounds=DOMRect(x=50, y=450, width=120, height=40), client=None)
    rect = viewport_rect_from_node(node, _state(scroll_y=400))
    assert rect is not None
    assert rect.x == 50
    assert rect.y == 50


def test_interacted_element_uses_selector_map_client_rects() -> None:
    node = _node(
        backend_id=42,
        bounds=DOMRect(x=10, y=910, width=60, height=24),
        client=DOMRect(x=10, y=110, width=60, height=24),
    )
    state = _state(scroll_y=800)
    state.dom_state.selector_map[3] = node
    interacted = DOMInteractedElement.load_from_enhanced_dom_tree(node)
    rect = viewport_rect_from_interacted(
        interacted,
        state,
        state.dom_state.selector_map,
    )
    assert rect is not None
    assert rect.y == 110
