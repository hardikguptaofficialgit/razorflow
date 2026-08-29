"""BYOK configuration tests."""

from __future__ import annotations

from core.llm_run_config import (
    agent_config_from_wire,
    agent_config_status_payload,
    redact_secrets,
    sanitize_provider_error,
)


def test_redact_secrets_removes_api_key() -> None:
    secret = "sk-test-secret-key-12345"
    message = f"Auth failed for bearer {secret}"
    cleaned = redact_secrets(message, secret)
    assert secret not in cleaned
    assert "[REDACTED]" in cleaned


def test_agent_config_from_wire_server_default() -> None:
    config = agent_config_from_wire(
        {
            "useByok": False,
            "maxAgentSteps": 25,
            "shoppingSkillEnabled": False,
        }
    )
    assert config.uses_server_default_llm
    assert config.max_agent_steps == 25
    assert config.shopping_skill_enabled is False


def test_agent_config_from_wire_requires_key_when_byok() -> None:
    try:
        agent_config_from_wire(
            {
                "useByok": True,
                "provider": "openrouter",
                "model": "openai/gpt-4o-mini",
            }
        )
    except ValueError as error:
        assert "API key" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_status_payload_never_includes_api_key() -> None:
    config = agent_config_from_wire(
        {
            "useByok": True,
            "provider": "groq",
            "apiKey": "gsk_super_secret_value",
            "model": "openai/gpt-oss-120b",
            "temperature": 0.1,
            "maxAgentSteps": 30,
            "shoppingSkillEnabled": True,
        }
    )
    payload = agent_config_status_payload(config)
    assert "gsk_super_secret_value" not in str(payload)
    assert payload["mode"] == "byok"
    assert payload["provider"] == "groq"


def test_sanitize_provider_error() -> None:
    secret = "gsk_super_secret_value"
    message = sanitize_provider_error(RuntimeError(f"401 invalid key {secret}"), secret)
    assert secret not in message
