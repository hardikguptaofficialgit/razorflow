"""Build the LLM for the open-source Browser Use executor.

Uses the OSS `browser_use` Agent + Tools stack with a BYO LLM:
gemini | openrouter | vercel_ai_gateway | groq | llamacpp. Paid ChatBrowserUse / Browser-Use cloud
LLM is intentionally unsupported.

Retry ownership lives in exactly one place: `utils.llm_resilience`. Client-level retry
loops are switched off (`max_retries=0`) so a provider's Retry-After cannot be slept out
ten times invisibly inside a single agent step; the resilience layer applies one bounded
budget per provider and then fails over to the next configured provider.
"""

from __future__ import annotations

import logging

from browser_use.llm.base import BaseChatModel
from browser_use.llm.google.chat import ChatGoogle
from browser_use.llm.groq.chat import ChatGroq
from browser_use.llm.openai.chat import ChatOpenAI
from browser_use.llm.openrouter.chat import ChatOpenRouter

from core.llm_failover import FailoverChatModel, ProviderSlot
from utils.config import (
    get_gemini_api_key,
    get_gemini_model,
    get_groq_api_key,
    get_groq_model,
    get_llm_provider,
    get_llamacpp_api_key,
    get_llamacpp_base_url,
    get_llamacpp_model,
    get_openrouter_api_key,
    get_openrouter_model,
    is_gemini_configured,
    is_groq_configured,
    is_openrouter_configured,
    get_vercel_ai_gateway_api_key,
    get_vercel_ai_gateway_model,
    is_vercel_ai_gateway_configured,
)
from utils.llm_resilience import ProviderNotConfiguredError

logger = logging.getLogger(__name__)

_PAID_PROVIDER_MSG = (
    "LLM_PROVIDER=browser_use (ChatBrowserUse / Browser-Use cloud LLM) is disabled. "
    "RazorFlow uses open-source browser-use with a BYO model. "
    "Set LLM_PROVIDER=gemini|openrouter|vercel_ai_gateway|groq|llamacpp."
)

# One HTTP attempt must finish inside this before the resilience layer retries or fails over.
_REQUEST_TIMEOUT_SEC = 60.0
# Failover candidate order after the configured primary.
_FAILOVER_PREFERENCE = ("openrouter", "vercel_ai_gateway", "gemini", "groq")


def _client_kwargs() -> dict[str, float | int]:
    return {"timeout": _REQUEST_TIMEOUT_SEC, "max_retries": 0}


# google-genai's HttpOptions.timeout is milliseconds, unlike the OpenAI-shaped clients.
_GEMINI_CLIENT_KWARGS: dict[str, float | int | dict[str, int]] = {
    "max_retries": 0,
    "http_options": {"timeout": int(_REQUEST_TIMEOUT_SEC * 1000)},
}


def _build_provider_llm(provider: str) -> BaseChatModel:
    """Construct one provider's chat model, raising if that provider is unusable."""
    if provider in {"browser_use", "chatbrowseruse", "bu"}:
        raise RuntimeError(_PAID_PROVIDER_MSG)

    if provider == "gemini":
        api_key = get_gemini_api_key()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Add it to .env or switch LLM_PROVIDER."
            )
        model = get_gemini_model()
        logger.info("Using Gemini LLM model=%s", model)
        return ChatGoogle(model=model, api_key=api_key, temperature=0.0, **_GEMINI_CLIENT_KWARGS)

    if provider == "llamacpp":
        base_url = get_llamacpp_base_url()
        model = get_llamacpp_model()
        logger.info("Using llama.cpp LLM model=%s base_url=%s", model, base_url)
        return ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=get_llamacpp_api_key(),
            temperature=0.0,
            frequency_penalty=0.0,
            timeout=_REQUEST_TIMEOUT_SEC,
            max_retries=0,
            add_schema_to_system_prompt=True,
            dont_force_structured_output=True,
            remove_min_items_from_schema=True,
            remove_defaults_from_schema=True,
            max_completion_tokens=1024,
        )

    if provider == "openrouter":
        api_key = get_openrouter_api_key()
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not configured. Add it to .env or switch LLM_PROVIDER."
            )
        model = get_openrouter_model()
        logger.info("Using OpenRouter LLM model=%s", model)
        return ChatOpenRouter(
            model=model,
            api_key=api_key,
            temperature=0.0,
            http_referer="https://razorflow.local",
            **_client_kwargs(),
        )

    if provider == "vercel_ai_gateway":
        api_key = get_vercel_ai_gateway_api_key()
        if not api_key:
            raise RuntimeError(
                "AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN is not configured. "
                "Add one to .env or switch LLM_PROVIDER."
            )
        model = get_vercel_ai_gateway_model()
        logger.info("Using Vercel AI Gateway LLM model=%s", model)
        return ChatOpenAI(
            model=model,
            base_url="https://ai-gateway.vercel.sh/v1",
            api_key=api_key,
            temperature=0.0,
            frequency_penalty=0.0,
            add_schema_to_system_prompt=True,
            dont_force_structured_output=True,
            remove_min_items_from_schema=True,
            remove_defaults_from_schema=True,
            **_client_kwargs(),
        )

    if provider != "groq":
        logger.warning("Unknown LLM_PROVIDER=%s — falling back to groq", provider)

    api_key = get_groq_api_key()
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not configured. Set LLM_PROVIDER=gemini|openrouter|llamacpp|groq "
            "and the matching API key / local llama-server."
        )

    model = get_groq_model()
    logger.info("Using Groq LLM model=%s", model)
    return ChatGroq(model=model, api_key=api_key, temperature=0.0, **_client_kwargs())


def create_browser_use_llm() -> BaseChatModel:
    """Return the LLM used by the Browser Use executor (OSS BYO only)."""
    return _build_provider_llm(get_llm_provider())


def _is_fallback_available(provider: str) -> bool:
    if provider == "openrouter":
        return is_openrouter_configured()
    if provider == "vercel_ai_gateway":
        return is_vercel_ai_gateway_configured()
    if provider == "gemini":
        return is_gemini_configured()
    if provider == "groq":
        return is_groq_configured()
    return False


def create_browser_use_llm_slots() -> list[ProviderSlot]:
    """Ordered providers for one run: configured primary first, then failover candidates."""
    primary = get_llm_provider()
    ordered = [primary, *[item for item in _FAILOVER_PREFERENCE if item != primary]]

    slots: list[ProviderSlot] = []
    for index, provider in enumerate(ordered):
        if index > 0 and not _is_fallback_available(provider):
            continue
        try:
            model = _build_provider_llm(provider)
        except Exception as error:
            if index == 0:
                raise
            logger.warning("Skipping LLM failover candidate %s: %s", provider, error)
            continue
        slots.append(ProviderSlot(provider=provider, model=str(getattr(model, "model", provider)), llm=model))

    if not slots:
        raise ProviderNotConfiguredError(
            "No usable LLM provider. Set OPENROUTER_API_KEY, AI_GATEWAY_API_KEY, "
            "GROQ_API_KEY or GEMINI_API_KEY, or start llama-server."
        )
    return slots


def require_browser_use_llm() -> BaseChatModel:
    """Executor LLM with bounded rate-limit backoff and provider failover."""
    try:
        slots = create_browser_use_llm_slots()
    except RuntimeError:
        raise
    except Exception as error:
        provider = get_llm_provider()
        if provider == "llamacpp":
            raise RuntimeError(
                "Failed to create llama.cpp LLM client. Start llama-server "
                f"({get_llamacpp_base_url()}) with model {get_llamacpp_model()!r}. "
                f"Details: {error}"
            ) from error
        if provider == "openrouter":
            raise RuntimeError(f"Failed to create OpenRouter LLM client. Details: {error}") from error
        if provider == "gemini":
            raise RuntimeError(f"Failed to create Gemini LLM client. Details: {error}") from error
        raise

    logger.info("Browser Use LLM chain: %s", " -> ".join(slot.describe() for slot in slots))
    return FailoverChatModel(slots)  # type: ignore[return-value]
