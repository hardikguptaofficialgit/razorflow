"""Viewport coordinate helpers for overlay sync with Browser Use."""

from __future__ import annotations

from browser_use.browser.views import BrowserStateSummary
from browser_use.dom.views import DOMInteractedElement, DOMRect, EnhancedDOMTreeNode


def viewport_rect_from_node(
    node: EnhancedDOMTreeNode,
    browser_state: BrowserStateSummary,
) -> DOMRect | None:
    """Return element bounds in viewport space for fixed-position overlay."""
    snapshot = node.snapshot_node
    if snapshot and snapshot.clientRects:
        return snapshot.clientRects

    if snapshot and snapshot.bounds:
        scroll_x = 0
        scroll_y = 0
        if browser_state.page_info is not None:
            scroll_x = browser_state.page_info.scroll_x
            scroll_y = browser_state.page_info.scroll_y
        return DOMRect(
            x=snapshot.bounds.x - scroll_x,
            y=snapshot.bounds.y - scroll_y,
            width=snapshot.bounds.width,
            height=snapshot.bounds.height,
        )

    if node.absolute_position and browser_state.page_info is not None:
        return DOMRect(
            x=node.absolute_position.x - browser_state.page_info.scroll_x,
            y=node.absolute_position.y - browser_state.page_info.scroll_y,
            width=node.absolute_position.width,
            height=node.absolute_position.height,
        )

    return None


def viewport_rect_from_interacted(
    element: DOMInteractedElement,
    browser_state: BrowserStateSummary,
    selector_map: dict[int, EnhancedDOMTreeNode],
) -> DOMRect | None:
    """Resolve overlay rect preferring live selector_map clientRects."""
    for node in selector_map.values():
        if node.backend_node_id == element.backend_node_id:
            rect = viewport_rect_from_node(node, browser_state)
            if rect is not None:
                return rect

    if element.bounds and browser_state.page_info is not None:
        return DOMRect(
            x=element.bounds.x - browser_state.page_info.scroll_x,
            y=element.bounds.y - browser_state.page_info.scroll_y,
            width=element.bounds.width,
            height=element.bounds.height,
        )

    return element.bounds
