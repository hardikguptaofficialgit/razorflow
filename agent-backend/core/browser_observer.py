"""Optional browser-use observation helper for planning (read-only, no execution)."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal
from urllib.parse import urlparse

from core.protocol import BrowserObservation, ObservedElement, PageContext
from utils.config import (
    BROWSER_USE_CDP_URL,
    BROWSER_USE_HEADLESS,
    BROWSER_USE_INCLUDE_SCREENSHOT,
    BROWSER_USE_MAX_ELEMENTS,
    BROWSER_USE_OBSERVER_TIMEOUT_SEC,
    is_browser_use_enabled,
)

logger = logging.getLogger(__name__)

PlanningSource = Literal["page_context_only", "page_context_and_browser_use"]

_run_sessions: dict[str, object] = {}


def _should_use_browser_observer(
    url: str,
    page_context: PageContext | None,
) -> bool:
    if not is_browser_use_enabled():
        return False

    if BROWSER_USE_CDP_URL:
        return True

    host = (urlparse(url).hostname or "").lower()
    # Extension pageContext on the user's live tab is always preferred — even on localhost.
    if page_context and len(page_context.elements) >= 2:
        logger.info(
            "Skipping browser-use for %s — extension pageContext has %d elements",
            host or url,
            len(page_context.elements),
        )
        return False

    if host in {"localhost", "127.0.0.1"}:
        return False

    return False


def _resolve_url(page_context: PageContext | None, fallback_url: str | None) -> str | None:
    if page_context and page_context.url.strip():
        return page_context.url.strip()
    if fallback_url and fallback_url.strip():
        return fallback_url.strip()
    return None


def _infer_role_hint(tag: str, attributes: dict[str, str], text: str) -> str:
    input_type = attributes.get("type", "").lower()
    role = attributes.get("role", "").lower()
    placeholder = attributes.get("placeholder", "").lower()
    aria_label = attributes.get("aria-label", "").lower()
    combined = f"{text} {placeholder} {aria_label}".lower()

    if tag == "a" and attributes.get("href"):
        return "link"
    if tag == "button" or role == "button" or input_type in {"button", "submit"}:
        return "button"
    if input_type == "search" or role == "searchbox" or "search" in combined:
        return "search"
    if tag in {"input", "textarea"}:
        return "input"
    return "input"


def _build_page_summary(state) -> str:
    parts = [f"Observed page '{state.title}' at {state.url}."]

    if state.page_info:
        parts.append(
            "Viewport "
            f"{state.page_info.viewport_width}x{state.page_info.viewport_height}, "
            f"scroll y={state.page_info.scroll_y}."
        )

    if state.pagination_buttons:
        parts.append(f"Pagination controls detected: {len(state.pagination_buttons)}.")

    if state.browser_errors:
        parts.append(f"Browser warnings: {len(state.browser_errors)}.")

    return " ".join(parts)


def _extract_observation_from_state(state) -> BrowserObservation:
    elements: list[ObservedElement] = []

    for index, element in list(state.dom_state.selector_map.items())[:BROWSER_USE_MAX_ELEMENTS]:
        attributes = {str(key): str(value) for key, value in element.attributes.items()}
        text = element.get_all_children_text(max_depth=2)[:80]

        elements.append(
            ObservedElement(
                index=index,
                tag=element.tag_name.lower(),
                text=text,
                placeholder=attributes.get("placeholder", "")[:80],
                aria_label=attributes.get("aria-label", "")[:80],
                role_hint=_infer_role_hint(element.tag_name.lower(), attributes, text),
            ),
        )

    screenshot_available = bool(state.screenshot)
    vision_hook_note = None
    if screenshot_available:
        vision_hook_note = (
            "Screenshot captured by browser-use observer for future vision pipeline; "
            "not attached to text planner in this session."
        )

    return BrowserObservation(
        source="browser-use",
        url=state.url,
        title=state.title,
        page_summary=_build_page_summary(state),
        interactive_elements=elements,
        screenshot_available=screenshot_available,
        vision_hook_note=vision_hook_note,
    )


async def _get_or_create_session(run_id: str):
    from browser_use.browser.session import BrowserSession

    existing = _run_sessions.get(run_id)
    if existing is not None:
        return existing

    if BROWSER_USE_CDP_URL:
        session = BrowserSession(cdp_url=BROWSER_USE_CDP_URL, headless=False)
    else:
        session = BrowserSession(
            headless=BROWSER_USE_HEADLESS,
            highlight_elements=False,
            dom_highlight_elements=False,
        )

    await session.start()
    _run_sessions[run_id] = session
    return session


async def _observe_with_browser_use(
    run_id: str,
    url: str,
) -> BrowserObservation:
    session = await _get_or_create_session(run_id)
    await session.navigate_to(url)
    state = await session.get_browser_state_summary(
        include_screenshot=BROWSER_USE_INCLUDE_SCREENSHOT,
    )
    return _extract_observation_from_state(state)


async def observe_page_for_planning(
    run_id: str,
    page_context: PageContext | None,
    fallback_url: str | None = None,
) -> tuple[BrowserObservation | None, PlanningSource]:
    if not is_browser_use_enabled():
        return None, "page_context_only"

    url = _resolve_url(page_context, fallback_url)
    if not url:
        logger.info(
            "Planning runId=%s source=page_context_only (no URL for browser-use)",
            run_id,
        )
        return None, "page_context_only"

    if not _should_use_browser_observer(url, page_context):
        return None, "page_context_only"

    try:
        observation = await asyncio.wait_for(
            _observe_with_browser_use(run_id, url),
            timeout=BROWSER_USE_OBSERVER_TIMEOUT_SEC,
        )
        logger.info(
            "Planning runId=%s source=page_context_and_browser_use elements=%d screenshot=%s",
            run_id,
            len(observation.interactive_elements),
            observation.screenshot_available,
        )
        return observation, "page_context_and_browser_use"
    except ImportError:
        logger.warning(
            "browser-use not installed; planning with pageContext only (runId=%s)",
            run_id,
        )
        return None, "page_context_only"
    except Exception as error:
        logger.warning(
            "browser-use observation unavailable for runId=%s: %s",
            run_id,
            error,
        )
        return None, "page_context_only"


async def cleanup_observer_session(run_id: str) -> None:
    session = _run_sessions.pop(run_id, None)
    if session is None:
        return

    try:
        await session.kill()
    except Exception as error:
        logger.warning("Failed to cleanup browser-use session runId=%s: %s", run_id, error)
