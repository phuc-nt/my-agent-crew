"""The `Settings` fields that come from the environment alone, kept as one place so a
key saved from the web lands in the same fields a restart would fill. Never from
`config.yaml`: that file is a whitelist of non-secret keys."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from my_agent_crew.config import Settings


def secrets_from(env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "openrouter_api_key": env.get("OPENROUTER_API_KEY") or None,
        "brave_api_key": env.get("BRAVE_API_KEY") or None,
        "tavily_api_key": env.get("TAVILY_API_KEY") or None,
        "firecrawl_base_url": str(env.get("FIRECRAWL_BASE_URL") or "").rstrip("/"),
        "firecrawl_api_key": env.get("FIRECRAWL_API_KEY") or None,
    }


def with_secrets(settings: Settings, env: Mapping[str, str]) -> Settings:
    return replace(settings, **secrets_from(env))
