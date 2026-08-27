"""Build the LLM for the open-source Browser Use executor.

Uses the OSS `browser_use` Agent + Tools stack with a BYO LLM:
gemini | openrouter | groq | llamacpp. Paid ChatBrowserUse / Browser-Use cloud
LLM is intentionally unsupported.
"""

from __future__ import annotations

import logging

from browser_use.llm.base import BaseChatModel
from browser_use.llm.google.chat import ChatGoogle
from browser_use.llm.groq.chat import ChatGroq
from browser_use.llm.openai.chat import ChatOpenAI
from browser_use.llm.openrouter.chat import ChatOpenRouter

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
)

logger = logging.getLogger(__name__)

_PAID_PROVIDER_MSG = (
    "LLM_PROVIDER=browser_use (ChatBrowserUse / Browser-Use cloud LLM) is disabled. "
    "RazorFlow uses open-source browser-use with a BYO model. "
    "Set LLM_PROVIDER=gemini|openrouter|groq|llamacpp."
)


def create_browser_use_llm() -> BaseChatModel:
    """Return the LLM used by the Browser Use executor (OSS BYO only)."""
    provider = get_llm_provider()

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
        return ChatGoogle(
            model=model,
            api_key=api_key,
            temperature=0.0,
            max_retries=3,
        )

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
            max_retries=2,
            timeout=180.0,
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
            timeout=90.0,
            max_retries=3,
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
    return ChatGroq(
        model=model,
        api_key=api_key,
        temperature=0.0,
    )


def require_browser_use_llm() -> BaseChatModel:
    """Same as create_browser_use_llm, with clearer errors for misconfig."""
    try:
        return create_browser_use_llm()
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
            raise RuntimeError(
                f"Failed to create OpenRouter LLM client. Details: {error}"
            ) from error
        if provider == "gemini":
            raise RuntimeError(
                f"Failed to create Gemini LLM client. Details: {error}"
            ) from error
        raise
