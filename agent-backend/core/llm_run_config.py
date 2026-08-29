"""Per-connection BYOK agent configuration (demo store)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

PlannerProvider = Literal["openrouter", "groq", "gemini", "vercel_ai_gateway"]

SUPPORTED_PLANNER_PROVIDERS: tuple[str, ...] = (
    "openrouter",
    "groq",
    "gemini",
    "vercel_ai_gateway",
)

DEFAULT_MAX_AGENT_STEPS = 40
DEFAULT_TEMPERATURE = 0.05


@dataclass(frozen=True)
class LlmByokConfig:
    provider: PlannerProvider
    api_key: str
    model: str
    temperature: float = DEFAULT_TEMPERATURE


@dataclass(frozen=True)
class AgentConnectionConfig:
    """Runtime agent settings for a WebSocket connection."""

    use_byok: bool = False
    llm: LlmByokConfig | None = None
    max_agent_steps: int = DEFAULT_MAX_AGENT_STEPS
    shopping_skill_enabled: bool = True

    @property
    def uses_server_default_llm(self) -> bool:
        return not self.use_byok or self.llm is None


def redact_secrets(text: str, *secrets: str | None) -> str:
    """Remove API key material from user-facing error strings."""
    cleaned = text
    for secret in secrets:
        if not secret or len(secret) < 4:
            continue
        cleaned = cleaned.replace(secret, "[REDACTED]")
    return cleaned


def sanitize_provider_error(error: Exception, api_key: str | None = None) -> str:
    message = redact_secrets(str(error), api_key)
    if api_key and len(api_key) >= 8:
        tail = api_key[-4:]
        message = message.replace(tail, "[REDACTED]")
    return message[:400]


def agent_config_from_wire(payload: dict[str, Any]) -> AgentConnectionConfig:
    use_byok = bool(payload.get("useByok", False))
    shopping = bool(payload.get("shoppingSkillEnabled", True))
    max_steps = int(payload.get("maxAgentSteps") or DEFAULT_MAX_AGENT_STEPS)
    max_steps = max(5, min(max_steps, 200))

    llm: LlmByokConfig | None = None
    if use_byok:
        provider = str(payload.get("provider") or "openrouter").strip().lower()
        if provider not in SUPPORTED_PLANNER_PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")
        api_key = str(payload.get("apiKey") or "").strip()
        if not api_key:
            raise ValueError("API key is required when BYOK is enabled.")
        model = str(payload.get("model") or "").strip()
        if not model:
            raise ValueError("Model is required when BYOK is enabled.")
        temperature_raw = payload.get("temperature")
        temperature = (
            float(temperature_raw)
            if temperature_raw is not None
            else DEFAULT_TEMPERATURE
        )
        temperature = max(0.0, min(temperature, 1.5))
        llm = LlmByokConfig(
            provider=provider,  # type: ignore[arg-type]
            api_key=api_key,
            model=model,
            temperature=temperature,
        )

    return AgentConnectionConfig(
        use_byok=use_byok,
        llm=llm,
        max_agent_steps=max_steps,
        shopping_skill_enabled=shopping,
    )


def agent_config_status_payload(config: AgentConnectionConfig | None) -> dict[str, Any]:
    if config is None or config.uses_server_default_llm:
        return {
            "mode": "server_default",
            "useByok": False,
            "shoppingSkillEnabled": True,
            "maxAgentSteps": DEFAULT_MAX_AGENT_STEPS,
        }
    assert config.llm is not None
    return {
        "mode": "byok",
        "useByok": True,
        "provider": config.llm.provider,
        "model": config.llm.model,
        "temperature": config.llm.temperature,
        "shoppingSkillEnabled": config.shopping_skill_enabled,
        "maxAgentSteps": config.max_agent_steps,
    }
