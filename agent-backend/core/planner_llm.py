"""LLM completion for the DOM agent planner (OpenRouter → Groq → Gemini fallback)."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from groq import Groq

from utils.config import (
    get_gemini_api_key,
    get_gemini_model,
    get_groq_api_key,
    get_groq_model,
    get_openrouter_api_keys,
    get_openrouter_model,
    get_planner_llm_fallback_chain,
    get_planner_llm_model,
    is_gemini_configured,
    is_groq_configured,
    is_openrouter_configured,
    is_planner_screenshot_enabled,
)

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_RETRYABLE_HTTP_CODES = {500, 502, 503, 504}
_KEY_SWITCH_HTTP_CODES = {401, 402, 403, 429}
_MAX_ATTEMPTS = 3


class PlannerConfigurationError(RuntimeError):
    """Raised when no planner LLM is configured."""


class PlannerLlmError(RuntimeError):
    """Raised when every planner LLM in the fallback chain fails."""


def _http_json_complete(
    *,
    url: str,
    body: dict,
    headers: dict[str, str],
    provider: str,
    extract_text: Callable[[dict], str],
    max_attempts: int = _MAX_ATTEMPTS,
) -> str:
    payload = json.dumps(body).encode()
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                parsed = json.loads(response.read())
            text = extract_text(parsed)
            if not text.strip():
                raise ValueError(f"{provider} returned empty planner output.")
            if attempt > 1:
                logger.info("%s planner succeeded on attempt %s", provider, attempt)
            return text
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:400]
            last_error = ValueError(f"{provider} HTTP {error.code}: {detail}")
            if error.code in _KEY_SWITCH_HTTP_CODES:
                raise last_error from error
            if error.code in _RETRYABLE_HTTP_CODES and attempt < max_attempts:
                delay = 0.8 * (2 ** (attempt - 1))
                logger.warning(
                    "%s planner HTTP %s attempt %s/%s — retry in %.1fs",
                    provider,
                    error.code,
                    attempt,
                    max_attempts,
                    delay,
                )
                time.sleep(delay)
                continue
            raise last_error from error
        except Exception as error:
            last_error = error
            if attempt < max_attempts:
                delay = 0.8 * (2 ** (attempt - 1))
                logger.warning(
                    "%s planner error attempt %s/%s — retry in %.1fs: %s",
                    provider,
                    attempt,
                    max_attempts,
                    delay,
                    error,
                )
                time.sleep(delay)
                continue
            raise

    raise PlannerLlmError(str(last_error or f"{provider} planner failed."))


def _parse_data_url(data_url: str) -> tuple[str, str]:
    match = re.match(r"data:([^;]+);base64,(.+)", data_url.strip(), re.I | re.S)
    if not match:
        raise ValueError("Invalid screenshot data URL.")
    return match.group(1), match.group(2)


def _vision_enabled(provider: str, screenshot_data_url: str | None) -> bool:
    return bool(
        screenshot_data_url
        and is_planner_screenshot_enabled()
        and provider in {"openrouter", "gemini"}
    )


def _gemini_complete(
    system_prompt: str,
    user_prompt: str,
    screenshot_data_url: str | None = None,
) -> str:
    api_key = get_gemini_api_key()
    if not api_key:
        raise PlannerConfigurationError(
            "GEMINI_API_KEY is not configured. Add it to .env and restart the backend.",
        )

    model = get_gemini_model()
    url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"

    user_parts: list[dict] = [{"text": user_prompt}]
    if screenshot_data_url and is_planner_screenshot_enabled():
        mime, payload = _parse_data_url(screenshot_data_url)
        user_parts.append({"inline_data": {"mime_type": mime, "data": payload}})

    def extract_text(payload: dict) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts") or []
        return "".join(part.get("text", "") for part in parts if isinstance(part, dict))

    return _http_json_complete(
        url=url,
        body={
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": user_parts}],
            "generationConfig": {
                "temperature": 0.05,
                "responseMimeType": "application/json",
            },
        },
        headers={"Content-Type": "application/json"},
        provider="Gemini",
        extract_text=extract_text,
    )


def _openrouter_extract_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("OpenRouter returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("OpenRouter returned empty planner output.")
    return content


def _openrouter_complete_with_key(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    screenshot_data_url: str | None = None,
) -> str:
    user_content: str | list[dict]
    if screenshot_data_url and is_planner_screenshot_enabled():
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": screenshot_data_url}},
        ]
    else:
        user_content = user_prompt

    return _http_json_complete(
        url=OPENROUTER_API_URL,
        body={
            "model": get_openrouter_model(),
            "temperature": 0.05,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        },
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://razorflow.local",
        },
        provider="OpenRouter",
        extract_text=_openrouter_extract_text,
        max_attempts=2,
    )


def _openrouter_complete(
    system_prompt: str,
    user_prompt: str,
    screenshot_data_url: str | None = None,
) -> str:
    keys = get_openrouter_api_keys()
    if not keys:
        raise PlannerConfigurationError(
            "OPENROUTER_API_KEY is not configured. Add it to .env and restart the backend.",
        )

    last_error: Exception | None = None
    for index, api_key in enumerate(keys):
        try:
            if index > 0:
                logger.info("OpenRouter planner trying backup key #%s", index + 1)
            return _openrouter_complete_with_key(
                api_key,
                system_prompt,
                user_prompt,
                screenshot_data_url,
            )
        except Exception as error:
            last_error = error
            if index + 1 < len(keys):
                logger.warning(
                    "OpenRouter key #%s failed (%s) — switching to next key",
                    index + 1,
                    error,
                )
            continue

    raise PlannerLlmError(
        str(last_error or "All OpenRouter API keys failed."),
    )


def _groq_complete(system_prompt: str, user_prompt: str) -> str:
    if not get_groq_api_key():
        raise PlannerConfigurationError(
            "GROQ_API_KEY is not configured. Add it to .env and restart the backend.",
        )

    client = Groq(api_key=get_groq_api_key())
    response = client.chat.completions.create(
        model=get_groq_model(),
        temperature=0.05,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw_content = response.choices[0].message.content
    if not raw_content:
        raise ValueError("Groq returned empty planner output.")
    return raw_content


def _complete_with_provider(
    provider: str,
    system_prompt: str,
    user_prompt: str,
    screenshot_data_url: str | None = None,
) -> str:
    if provider == "groq":
        if _vision_enabled(provider, screenshot_data_url):
            logger.info("Planner screenshot skipped for groq (text-only)")
        return _groq_complete(system_prompt, user_prompt)
    if provider == "openrouter":
        return _openrouter_complete(system_prompt, user_prompt, screenshot_data_url)
    if provider == "gemini":
        return _gemini_complete(system_prompt, user_prompt, screenshot_data_url)
    raise PlannerConfigurationError(f"Unknown planner provider: {provider}")


def _is_provider_configured(provider: str) -> bool:
    if provider == "groq":
        return is_groq_configured()
    if provider == "openrouter":
        return is_openrouter_configured()
    if provider == "gemini":
        return is_gemini_configured()
    return False


def complete_planner_json(
    system_prompt: str,
    user_prompt: str,
    screenshot_data_url: str | None = None,
) -> str:
    chain = get_planner_llm_fallback_chain()
    configured = [provider for provider in chain if _is_provider_configured(provider)]
    if not configured:
        raise PlannerConfigurationError(
            "No planner LLM configured. Set OPENROUTER_API_KEY, GROQ_API_KEY, or GEMINI_API_KEY in .env.",
        )

    last_error: Exception | None = None
    for index, provider in enumerate(configured):
        model = get_planner_llm_model(provider)
        try:
            if screenshot_data_url and _vision_enabled(provider, screenshot_data_url):
                logger.info("Planner LLM provider=%s model=%s vision=on", provider, model)
            else:
                logger.info("Planner LLM provider=%s model=%s", provider, model)
            return _complete_with_provider(
                provider,
                system_prompt,
                user_prompt,
                screenshot_data_url,
            )
        except PlannerConfigurationError:
            continue
        except Exception as error:
            last_error = error
            fallback = configured[index + 1] if index + 1 < len(configured) else None
            if fallback:
                logger.warning(
                    "Planner LLM %s failed (%s) — falling back to %s",
                    provider,
                    error,
                    fallback,
                )
            continue

    raise PlannerLlmError(
        str(last_error or "All planner LLM providers in the fallback chain failed."),
    )
