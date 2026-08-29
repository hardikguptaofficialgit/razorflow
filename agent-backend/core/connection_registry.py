"""In-memory per-connection agent configuration (demo BYOK)."""

from __future__ import annotations

from core.llm_run_config import AgentConnectionConfig

_configs: dict[str, AgentConnectionConfig] = {}


def set_agent_config(connection_id: str, config: AgentConnectionConfig) -> None:
    _configs[connection_id] = config


def get_agent_config(connection_id: str) -> AgentConnectionConfig | None:
    return _configs.get(connection_id)


def clear_agent_config(connection_id: str) -> None:
    _configs.pop(connection_id, None)
