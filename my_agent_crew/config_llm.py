"""How the crew spends on models beyond which routes a turn takes: how long the Claude API
keeps the shared part of a prompt cached, and which routes write the short side texts
(a conversation's title, its summary) instead of the agent's own model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from my_agent_crew.config_parse import Route, as_bool, parse_routes

# The Claude API's two cache lifetimes. The tools and the system prompt rarely change, and a
# person answers minutes apart: an hour keeps them warm across that gap for twice the write.
CACHE_TTLS = ("5m", "1h")


@dataclass(frozen=True)
class LlmSettings:
    anthropic_cache_ttl: str = "5m"
    # Routes for the side texts, best first; empty writes them with the agent's own routes.
    side_routes: tuple[Route, ...] = ()


def llm_settings(env: Mapping[str, str], file_values: Mapping[str, object]) -> LlmSettings:
    ttl = str(
        env.get("MY_AGENT_ANTHROPIC_CACHE_TTL") or file_values.get("anthropic_cache_ttl") or "5m"
    ).strip()
    if ttl not in CACHE_TTLS:
        raise ValueError(f"anthropic_cache_ttl must be {' or '.join(CACHE_TTLS)}, got {ttl!r}")
    side = env.get("MY_AGENT_SIDE_ROUTES")
    return LlmSettings(
        anthropic_cache_ttl=ttl,
        side_routes=parse_routes(side if side is not None else file_values.get("side_routes")),
    )


def provider_fallbacks(env: Mapping[str, str], file_values: Mapping[str, object]) -> bool:
    """Whether OpenRouter may serve from an upstream outside `openrouter_providers`."""
    return as_bool(
        env.get(
            "MY_AGENT_OPENROUTER_PROVIDER_FALLBACKS",
            file_values.get("openrouter_provider_fallbacks", True),
        )
    )
