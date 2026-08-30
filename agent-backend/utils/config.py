"""Environment configuration for agent-backend."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent


def load_environment() -> None:
    """Load repo-root .env first, then .env.test overrides, then agent-backend/.env."""
    repo_env = _REPO_ROOT / ".env"
    repo_env_test = _REPO_ROOT / ".env.test"
    local_env = _BACKEND_ROOT / ".env"

    if repo_env.is_file():
        load_dotenv(repo_env)
        logger.info("Loaded environment from %s", repo_env)
    if repo_env_test.is_file():
        load_dotenv(repo_env_test, override=True)
        logger.info("Applied test overrides from %s", repo_env_test)
    elif not repo_env.is_file():
        logger.warning("No .env found at %s", repo_env)

    if local_env.is_file():
        load_dotenv(local_env, override=True)
        logger.info("Applied overrides from %s", local_env)


load_environment()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_groq_api_keys() -> tuple[str, ...]:
    """All Groq keys in priority order, removing duplicates."""
    return _get_api_keys("GROQ")


def _get_api_keys(prefix: str) -> tuple[str, ...]:
    """Read API_KEY, API_KEY_2..API_KEY_N, and API_KEYS without a fixed limit."""
    keys: list[str] = []
    base_name = f"{prefix}_API_KEY"
    names = [base_name]
    names.extend(sorted(
        (name for name in os.environ if re.fullmatch(rf"{re.escape(base_name)}_\d+", name)),
        key=lambda name: int(name.rsplit("_", 1)[1]),
    ))
    for name in names:
        value = os.getenv(name, "").strip()
        if value and value not in keys:
            keys.append(value)

    bulk = os.getenv(f"{prefix}_API_KEYS", "").strip()
    if bulk:
        for part in bulk.split(","):
            part = part.strip()
            if part and part not in keys:
                keys.append(part)
    return tuple(keys)


def get_groq_api_key() -> str:
    keys = get_groq_api_keys()
    return keys[0] if keys else ""


DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


def get_groq_model() -> str:
    return os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL


def is_groq_configured() -> bool:
    return bool(get_groq_api_key())


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


# Three providers at 15s each stay inside the browser-use 50s first-step watchdog, while a
# typical per-minute Retry-After still fits in one bounded wait before failing over.
DEFAULT_LLM_RETRY_MAX_ATTEMPTS = 3
DEFAULT_LLM_RETRY_BASE_DELAY_SEC = 1.0
DEFAULT_LLM_RETRY_MAX_DELAY_SEC = 10.0
DEFAULT_LLM_RETRY_BUDGET_SEC = 15.0


def get_llm_retry_max_attempts() -> int:
    return _env_int("LLM_RETRY_MAX_ATTEMPTS", DEFAULT_LLM_RETRY_MAX_ATTEMPTS)


def get_llm_retry_base_delay() -> float:
    return _env_float("LLM_RETRY_BASE_DELAY_SEC", DEFAULT_LLM_RETRY_BASE_DELAY_SEC)


def get_llm_retry_max_delay() -> float:
    return _env_float("LLM_RETRY_MAX_DELAY_SEC", DEFAULT_LLM_RETRY_MAX_DELAY_SEC)


def get_llm_retry_budget() -> float:
    """Wall-clock ceiling for same-provider retries before falling over to the next provider."""
    return _env_float("LLM_RETRY_BUDGET_SEC", DEFAULT_LLM_RETRY_BUDGET_SEC)


def get_planner_strategy() -> str:
    """llm = Groq-first for in-app DOM agent; hybrid = heuristics before Groq."""
    raw = (os.getenv("PLANNER_STRATEGY", "llm").strip() or "llm").lower()
    return raw if raw in {"llm", "hybrid"} else "llm"


def get_llm_provider() -> str:
    """gemini | openrouter | groq | llamacpp — BYO LLM for OSS browser-use executor.

    Paid ChatBrowserUse / Browser-Use cloud LLM is not supported.
    """
    raw = (os.getenv("LLM_PROVIDER", "openrouter").strip() or "openrouter").lower()
    if raw in {"browser_use", "chatbrowseruse", "bu"}:
        logger.warning(
            "LLM_PROVIDER=%s is the paid Browser-Use cloud LLM — forcing gemini",
            raw,
        )
        return "gemini"
    if raw == "google":
        return "gemini"
    return raw


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

PLANNER_LLM_CHAIN = ("openrouter", "vercel_ai_gateway", "groq", "gemini")


def get_planner_llm_provider() -> str:
    """Primary planner LLM (defaults to openrouter)."""
    raw = (os.getenv("PLANNER_LLM_PROVIDER", "").strip() or "openrouter").lower()
    if raw in PLANNER_LLM_CHAIN:
        return raw
    return "openrouter"


def get_planner_llm_fallback_chain() -> tuple[str, ...]:
    """Ordered planner providers, defaulting to OpenRouter then Gateway."""
    configured = os.getenv("PLANNER_LLM_PROVIDERS", "").strip()
    if configured:
        chain = tuple(
            item
            for item in (part.strip().lower() for part in configured.split(","))
            if item in PLANNER_LLM_CHAIN
        )
        if chain:
            return tuple(dict.fromkeys(chain))
    primary = get_planner_llm_provider()
    start = PLANNER_LLM_CHAIN.index(primary)
    return PLANNER_LLM_CHAIN[start:]


def get_planner_llm_model(provider: str) -> str:
    if provider == "groq":
        return get_groq_model()
    if provider == "openrouter":
        return get_openrouter_model()
    return get_gemini_model()


def get_planner_max_tokens() -> int:
    """Cap planner completions — avoids OpenRouter 402 when credits are low."""
    raw = os.getenv("PLANNER_MAX_TOKENS", "2048").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 2048
    return max(256, min(value, 8192))


def get_vercel_ai_gateway_api_key() -> str:
    """AI Gateway API key or Vercel OIDC token (see vercel env pull)."""
    return (
        os.getenv("AI_GATEWAY_API_KEY", "").strip()
        or os.getenv("VERCEL_OIDC_TOKEN", "").strip()
    )


def get_vercel_ai_gateway_model() -> str:
    return (
        os.getenv("VERCEL_AI_GATEWAY_MODEL", "").strip()
        or os.getenv("AI_GATEWAY_MODEL", "").strip()
        or "alibaba/qwen3.7-flash"
    )


def is_vercel_ai_gateway_configured() -> bool:
    return bool(get_vercel_ai_gateway_api_key())


def is_planner_llm_ready() -> bool:
    return (
        is_openrouter_configured()
        or is_groq_configured()
        or is_vercel_ai_gateway_configured()
        or is_gemini_configured()
    )


def get_gemini_api_key() -> str:
    return (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
    )


def get_gemini_model() -> str:
    return (
        os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
        or DEFAULT_GEMINI_MODEL
    )


def is_gemini_configured() -> bool:
    return bool(get_gemini_api_key())


def get_browser_use_api_key() -> str:
    """Deprecated: paid Browser-Use cloud LLM key is unused."""
    return ""


def get_browser_use_model() -> str:
    """Deprecated: paid Browser-Use cloud model aliases are unused."""
    return ""


def is_browser_use_cloud_configured() -> bool:
    """Always false — RazorFlow does not use paid ChatBrowserUse."""
    return False


def get_openrouter_api_keys() -> tuple[str, ...]:
    """All OpenRouter keys in priority order (primary → backups)."""
    keys = list(_get_api_keys("OPENROUTER"))

    if not keys:
        fallback = os.getenv("LLM_API_KEY", "").strip()
        if fallback:
            keys.append(fallback)
    return tuple(keys)


def get_openrouter_api_key() -> str:
    keys = get_openrouter_api_keys()
    return keys[0] if keys else ""


def get_openrouter_model() -> str:
    # Fast Flash-Lite + :nitro = highest-throughput OpenRouter routing.
    return (
        os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite:nitro").strip()
        or "google/gemini-2.5-flash-lite:nitro"
    )


def is_openrouter_configured() -> bool:
    return bool(get_openrouter_api_keys())


def get_llamacpp_base_url() -> str:
    return (
        os.getenv("LLAMACPP_BASE_URL", "http://127.0.0.1:8080/v1").strip()
        or "http://127.0.0.1:8080/v1"
    )


def get_llamacpp_model() -> str:
    # llama-server ignores the name for single-model loads; keep a stable id for logs.
    return (
        os.getenv("LLAMACPP_MODEL", "qwen2.5-7b-instruct").strip()
        or "qwen2.5-7b-instruct"
    )


def get_llamacpp_api_key() -> str:
    # OpenAI client requires a non-empty key; llama-server does not validate it.
    return os.getenv("LLAMACPP_API_KEY", "llamacpp").strip() or "llamacpp"


def is_llamacpp_configured() -> bool:
    return get_llm_provider() == "llamacpp"


def is_browser_llm_ready() -> bool:
    provider = get_llm_provider()
    if provider == "llamacpp":
        return True
    if provider == "gemini":
        return is_gemini_configured()
    if provider == "openrouter":
        return is_openrouter_configured()
    return is_groq_configured()


def is_browser_use_enabled() -> bool:
    return _env_bool("BROWSER_USE_OBSERVER_ENABLED", False)


def is_browser_use_executor_enabled() -> bool:
    """When true, legacy browser-use library drives actions. Default is store DOM executor."""
    return _env_bool("BROWSER_USE_EXECUTOR_ENABLED", False)


def is_agent_runtime_v2_enabled() -> bool:
    """When true, use Agent Runtime V2 (clean LLM loop). Default on."""
    return _env_bool("AGENT_RUNTIME_V2", True)


def get_browser_use_cdp_url() -> str | None:
    url = os.getenv("BROWSER_USE_CDP_URL", "").strip()
    return url or None


def is_razorpay_configured() -> bool:
    return bool(
        os.getenv("RAZORPAY_KEY_ID", "").strip()
        and os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    )


def log_config_status() -> None:
    provider = get_llm_provider()
    if provider == "gemini":
        llm_status = (
            f"gemini:{get_gemini_model()}"
            if is_gemini_configured()
            else "missing GEMINI_API_KEY"
        )
    elif provider == "llamacpp":
        llm_status = f"llamacpp:{get_llamacpp_model()}@{get_llamacpp_base_url()}"
    elif provider == "openrouter":
        llm_status = (
            f"openrouter:{get_openrouter_model()}"
            if is_openrouter_configured()
            else "missing OPENROUTER_API_KEY"
        )
    else:
        llm_status = "ready" if is_groq_configured() else "missing GROQ_API_KEY"

    logger.info(
        "Config: llm=%s planner=%s+%s browser_use_observer=%s browser_use_executor=%s razorpay=%s env_file=%s",
        llm_status,
        get_planner_llm_provider(),
        "->".join(get_planner_llm_fallback_chain()[1:]) or "none",
        "on" if is_browser_use_enabled() else "off",
        "on" if is_browser_use_executor_enabled() else "off",
        "ready" if is_razorpay_configured() else "missing keys",
        _REPO_ROOT / ".env",
    )


# Back-compat module constants (read fresh at import after load_environment)
GROQ_API_KEY = get_groq_api_key()
GROQ_MODEL = get_groq_model()

MAX_STEPS_PER_CHUNK = 1
MAX_PLANNING_TURNS = int(os.getenv("MAX_PLANNING_TURNS", "16"))
MAX_CONSECUTIVE_FAILURES = int(os.getenv("MAX_CONSECUTIVE_FAILURES", "3"))
MAX_STALE_PAGE_TURNS = int(os.getenv("MAX_STALE_PAGE_TURNS", "4"))
MAX_BROWSER_USE_STEPS = int(os.getenv("MAX_BROWSER_USE_STEPS", "40"))

BROWSER_USE_OBSERVER_ENABLED = is_browser_use_enabled()
BROWSER_USE_EXECUTOR_ENABLED = is_browser_use_executor_enabled()
BROWSER_USE_HEADLESS = _env_bool("BROWSER_USE_HEADLESS", False)
BROWSER_USE_INCLUDE_SCREENSHOT = _env_bool("BROWSER_USE_INCLUDE_SCREENSHOT", True)


def is_planner_screenshot_enabled() -> bool:
    return _env_bool("PLANNER_INCLUDE_SCREENSHOT", True)
BROWSER_USE_CDP_URL = get_browser_use_cdp_url()
BROWSER_USE_OBSERVER_TIMEOUT_SEC = int(
    os.getenv("BROWSER_USE_OBSERVER_TIMEOUT_SEC", "8"),
)
BROWSER_USE_MAX_ELEMENTS = int(os.getenv("BROWSER_USE_MAX_ELEMENTS", "30"))

VOICE_INTENT_GROQ_ENABLED = _env_bool("VOICE_INTENT_GROQ_ENABLED", True)

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_MCP_ENDPOINT = os.getenv(
    "RAZORPAY_MCP_ENDPOINT",
    "https://mcp.razorpay.com/mcp",
).strip()

DEFAULT_PAYMENT_CURRENCY = os.getenv("DEFAULT_PAYMENT_CURRENCY", "INR").strip().upper()
MAX_SPEND_PAISE = int(os.getenv("MAX_SPEND_PAISE", "500000"))
