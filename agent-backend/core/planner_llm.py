"""LLM completion for the DOM agent planner (OpenRouter → Groq → Vercel AI Gateway → Gemini)."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from groq import Groq

from utils.config import (
    get_gemini_api_key,
    get_gemini_model,
    get_groq_api_key,
    get_groq_api_keys,
    get_groq_model,
    get_llm_retry_budget,
    get_openrouter_api_keys,
    get_openrouter_model,
    get_planner_llm_fallback_chain,
    get_planner_llm_model,
    get_planner_max_tokens,
    get_vercel_ai_gateway_api_key,
    get_vercel_ai_gateway_model,
    is_gemini_configured,
    is_groq_configured,
    is_openrouter_configured,
    is_planner_screenshot_enabled,
    is_vercel_ai_gateway_configured,
)
from utils.llm_resilience import (
    AUTH,
    BILLING,
    RATE_LIMIT,
    SERVER,
    TRANSPORT,
    call_with_resilience,
    classify_error,
    compute_delay,
)

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
VERCEL_AI_GATEWAY_API_URL = "https://ai-gateway.vercel.sh/v1/chat/completions"
# Credential/credit problems: rotate to the next API key immediately — waiting cannot help.
_KEY_SWITCH_HTTP_CODES = {401, 402, 403}
_MAX_ATTEMPTS = 3
_HTTP_TIMEOUT_SEC = 60
_KEY_COOLDOWNS: dict[tuple[str, str], float] = {}
_KEY_STATE_LOCK = threading.Lock()


class PlannerConfigurationError(RuntimeError):
    """Raised when no planner LLM is configured."""


class PlannerLlmError(RuntimeError):
    """Raised when every planner LLM in the fallback chain fails."""


def _key_label(index: int) -> str:
    """A safe key identifier for logs; API key material must never be logged."""
    return f"key #{index + 1}"


def _failure_cooldown(error: Exception) -> tuple[float, str]:
    """Return a conservative cooldown for failures that should trigger rotation."""
    kind = classify_error(error).kind
    if kind == RATE_LIMIT:
        return 300.0, "rate_or_quota_limit"
    if kind in (AUTH, BILLING):
        return 900.0, f"{kind}_failure"
    if kind in (TRANSPORT, SERVER):
        return 30.0, "temporary_provider_failure"
    return 60.0, "provider_failure"


def _available_keys(provider: str, keys: tuple[str, ...]) -> list[tuple[int, str]]:
    now = time.monotonic()
    with _KEY_STATE_LOCK:
        available = [
            (index, key)
            for index, key in enumerate(keys)
            if _KEY_COOLDOWNS.get((provider, key), 0.0) <= now
        ]
    return available


def _cool_down_key(provider: str, index: int, key: str, error: Exception) -> None:
    duration, reason = _failure_cooldown(error)
    with _KEY_STATE_LOCK:
        _KEY_COOLDOWNS[(provider, key)] = time.monotonic() + duration
    logger.warning(
        "%s planner %s failed (%s); cooling down for %.0fs",
        provider,
        _key_label(index),
        reason,
        duration,
    )


def _http_json_complete(
    *,
    url: str,
    body: dict,
    headers: dict[str, str],
    provider: str,
    extract_text: Callable[[dict], str],
    max_attempts: int = _MAX_ATTEMPTS,
    model: str = "",
) -> str:
    payload = json.dumps(body).encode()
    last_error: Exception | None = None
    started = time.perf_counter()
    retries = 0
    attempts = 0
    backoff_s = 0.0
    budget = get_llm_retry_budget()

    def finalize(ok: bool, detail: str | None = None) -> None:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "LLM_CALL provider=%s model=%s ok=%s attempts=%s retries=%s latency_ms=%.0f "
            "backoff_ms=%.0f providers_tried=%s error=%s",
            provider,
            model or "?",
            ok,
            attempts,
            retries,
            elapsed_ms,
            backoff_s * 1000.0,
            provider,
            (detail or "-")[:200],
        )

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        request = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SEC) as response:
                parsed = json.loads(response.read())
            text = extract_text(parsed)
            if not text.strip():
                raise ValueError(f"{provider} returned empty planner output.")
            if attempt > 1:
                logger.info("%s planner succeeded on attempt %s", provider, attempt)
            finalize(True)
            return text
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:400]
            last_error = ValueError(f"{provider} HTTP {error.code}: {detail}")
            info = classify_error(error, provider=provider, model=model)
            wait = (
                compute_delay(
                    attempt,
                    info,
                    base_delay=0.8,
                    max_delay=12.0,
                    elapsed=time.perf_counter() - started,
                    budget=budget,
                )
                if info.retryable
                else None
            )
            if error.code in _KEY_SWITCH_HTTP_CODES or wait is None:
                finalize(False, str(last_error))
                raise last_error from error
            retries += 1
            backoff_s += wait
            logger.warning(
                "%s planner %s attempt %s/%s — backing off %.1fs",
                provider,
                info.describe(),
                attempt,
                max_attempts,
                wait,
            )
            time.sleep(wait)
            continue
        except Exception as error:
            last_error = error
            info = classify_error(error, provider=provider, model=model)
            # A completion we could not parse is a provider hiccup, not a client mistake.
            wait = (
                compute_delay(
                    attempt,
                    info,
                    base_delay=0.8,
                    max_delay=12.0,
                    elapsed=time.perf_counter() - started,
                    budget=budget,
                )
                if info.retryable or isinstance(error, ValueError)
                else None
            )
            if wait is None or attempt >= max_attempts:
                finalize(False, str(error))
                raise
            retries += 1
            backoff_s += wait
            logger.warning(
                "%s planner error attempt %s/%s — retry in %.1fs: %s",
                provider,
                attempt,
                max_attempts,
                wait,
                error,
            )
            time.sleep(wait)
            continue

    finalize(False, str(last_error))
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
        and provider in {"openrouter", "vercel_ai_gateway", "gemini"}
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
        model=model,
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
    *,
    model: str | None = None,
    temperature: float = 0.05,
) -> str:
    resolved_model = model or get_openrouter_model()
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
            "model": resolved_model,
            "temperature": temperature,
            "max_tokens": get_planner_max_tokens(),
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
        model=resolved_model,
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

    available = _available_keys("OpenRouter", keys)
    if not available:
        raise PlannerLlmError("All OpenRouter API keys are cooling down.")

    last_error: Exception | None = None
    deadline = time.monotonic() + get_llm_retry_budget()
    for attempt, (index, api_key) in enumerate(available):
        if attempt and time.monotonic() >= deadline:
            logger.warning("Planner retry budget exhausted — failing over to the next provider")
            break
        try:
            if attempt > 0:
                logger.info("OpenRouter planner switching to %s", _key_label(index))
            return _openrouter_complete_with_key(
                api_key,
                system_prompt,
                user_prompt,
                screenshot_data_url,
            )
        except Exception as error:
            last_error = error
            _cool_down_key("OpenRouter", index, api_key, error)
            if attempt + 1 < len(available):
                logger.warning(
                    "OpenRouter key #%s failed (%s) — switching to next key",
                    index + 1,
                    error,
                )
            continue

    raise PlannerLlmError(
        str(last_error or "All OpenRouter API keys failed."),
    )


def _vercel_ai_gateway_complete(
    system_prompt: str,
    user_prompt: str,
    screenshot_data_url: str | None = None,
) -> str:
    api_key = get_vercel_ai_gateway_api_key()
    if not api_key:
        raise PlannerConfigurationError(
            "Vercel AI Gateway is not configured. Set AI_GATEWAY_API_KEY or run vercel env pull.",
        )

    user_content: str | list[dict]
    if screenshot_data_url and is_planner_screenshot_enabled():
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": screenshot_data_url}},
        ]
    else:
        user_content = user_prompt

    return _http_json_complete(
        url=VERCEL_AI_GATEWAY_API_URL,
        body={
            "model": get_vercel_ai_gateway_model(),
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
        },
        provider="VercelAIGateway",
        extract_text=_openrouter_extract_text,
        model=get_vercel_ai_gateway_model(),
        max_attempts=2,
    )


def _groq_complete_with_key(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.05,
) -> str:
    resolved_model = model or get_groq_model()

    def request() -> str:
        client = Groq(api_key=api_key, timeout=_HTTP_TIMEOUT_SEC, max_retries=0)
        response = client.chat.completions.create(
            model=resolved_model,
            temperature=temperature,
            max_tokens=get_planner_max_tokens(),
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

    return call_with_resilience(request, provider="Groq", model=resolved_model)[0]


def _groq_complete(system_prompt: str, user_prompt: str) -> str:
    keys = get_groq_api_keys()
    if not keys:
        raise PlannerConfigurationError(
            "GROQ_API_KEY is not configured. Add it to .env and restart the backend.",
        )

    available = _available_keys("Groq", keys)
    if not available:
        raise PlannerLlmError("All Groq API keys are cooling down.")

    last_error: Exception | None = None
    deadline = time.monotonic() + get_llm_retry_budget()
    for attempt, (index, api_key) in enumerate(available):
        if attempt and time.monotonic() >= deadline:
            logger.warning("Planner retry budget exhausted — failing over to the next provider")
            break
        try:
            if attempt > 0:
                logger.info("Groq planner switching to %s", _key_label(index))
            return _groq_complete_with_key(api_key, system_prompt, user_prompt)
        except Exception as error:
            last_error = error
            _cool_down_key("Groq", index, api_key, error)
            if attempt + 1 < len(available):
                logger.warning(
                    "Groq key #%s failed (%s) — switching to next key",
                    index + 1,
                    error,
                )
    raise PlannerLlmError(str(last_error or "All Groq API keys failed."))


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
    if provider == "vercel_ai_gateway":
        return _vercel_ai_gateway_complete(system_prompt, user_prompt, screenshot_data_url)
    if provider == "gemini":
        return _gemini_complete(system_prompt, user_prompt, screenshot_data_url)
    raise PlannerConfigurationError(f"Unknown planner provider: {provider}")


def _is_provider_configured(provider: str) -> bool:
    if provider == "groq":
        return is_groq_configured()
    if provider == "openrouter":
        return is_openrouter_configured()
    if provider == "vercel_ai_gateway":
        return is_vercel_ai_gateway_configured()
    if provider == "gemini":
        return is_gemini_configured()
    return False


def complete_planner_json(
    system_prompt: str,
    user_prompt: str,
    screenshot_data_url: str | None = None,
    *,
    run_config: "LlmByokConfig | None" = None,
) -> str:
    if run_config is not None:
        logger.info(
            "Planner LLM BYOK provider=%s model=%s",
            run_config.provider,
            run_config.model,
        )
        return complete_planner_json_byok(
            run_config,
            system_prompt,
            user_prompt,
            screenshot_data_url=screenshot_data_url,
        )

    chain = get_planner_llm_fallback_chain()
    configured = [provider for provider in chain if _is_provider_configured(provider)]
    if not configured:
        raise PlannerConfigurationError(
            "No planner LLM configured. Set OPENROUTER_API_KEY, GROQ_API_KEY, "
            "AI_GATEWAY_API_KEY, or GEMINI_API_KEY.",
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


def _gemini_complete_with_key(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.05,
    screenshot_data_url: str | None = None,
) -> str:
    resolved_model = model or get_gemini_model()
    url = f"{GEMINI_API_BASE}/{resolved_model}:generateContent?key={api_key}"

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
                "temperature": temperature,
                "maxOutputTokens": get_planner_max_tokens(),
                "responseMimeType": "application/json",
            },
        },
        headers={"Content-Type": "application/json"},
        provider="Gemini",
        extract_text=extract_text,
        model=resolved_model,
        max_attempts=2,
    )


def _vercel_gateway_complete_with_key(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    screenshot_data_url: str | None = None,
    *,
    model: str | None = None,
    temperature: float = 0.05,
) -> str:
    resolved_model = model or get_vercel_ai_gateway_model()
    user_content: str | list[dict]
    if screenshot_data_url and is_planner_screenshot_enabled():
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": screenshot_data_url}},
        ]
    else:
        user_content = user_prompt

    return _http_json_complete(
        url=VERCEL_AI_GATEWAY_API_URL,
        body={
            "model": resolved_model,
            "temperature": temperature,
            "max_tokens": get_planner_max_tokens(),
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        },
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        provider="VercelAIGateway",
        extract_text=_openrouter_extract_text,
        model=resolved_model,
        max_attempts=2,
    )


def complete_planner_json_byok(
    config: "LlmByokConfig",
    system_prompt: str,
    user_prompt: str,
    *,
    screenshot_data_url: str | None = None,
) -> str:
    from core.llm_run_config import LlmByokConfig

    if config.provider == "groq":
        if screenshot_data_url:
            logger.info("Planner BYOK screenshot skipped for groq (text-only)")
        return _groq_complete_with_key(
            config.api_key,
            system_prompt,
            user_prompt,
            model=config.model,
            temperature=config.temperature,
        )
    if config.provider == "openrouter":
        return _openrouter_complete_with_key(
            config.api_key,
            system_prompt,
            user_prompt,
            screenshot_data_url,
            model=config.model,
            temperature=config.temperature,
        )
    if config.provider == "vercel_ai_gateway":
        return _vercel_gateway_complete_with_key(
            config.api_key,
            system_prompt,
            user_prompt,
            screenshot_data_url,
            model=config.model,
            temperature=config.temperature,
        )
    if config.provider == "gemini":
        return _gemini_complete_with_key(
            config.api_key,
            system_prompt,
            user_prompt,
            model=config.model,
            temperature=config.temperature,
            screenshot_data_url=screenshot_data_url,
        )
    raise PlannerConfigurationError(f"Unknown BYOK provider: {config.provider}")


def test_planner_connection(
    *,
    provider: str,
    api_key: str,
    model: str,
    temperature: float = 0.05,
) -> dict[str, object]:
    """Validate a BYOK credential with a minimal completion request."""
    from core.llm_run_config import LlmByokConfig, sanitize_provider_error

    config = LlmByokConfig(
        provider=provider,  # type: ignore[arg-type]
        api_key=api_key,
        model=model,
        temperature=temperature,
    )
    try:
        complete_planner_json_byok(
            config,
            "You are a connection test assistant.",
            'Reply with JSON only: {"ok": true}',
        )
        return {"ok": True, "provider": provider, "model": model}
    except Exception as error:
        return {
            "ok": False,
            "error": sanitize_provider_error(error, api_key),
        }
