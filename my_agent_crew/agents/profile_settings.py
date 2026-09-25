"""The runtime settings one `agent.yaml` overrides: routes and how hard they think, the
cost and step caps, and what the agent's shell may do. Split out of `profile_yaml` so the
file that reads a profile stays readable."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from my_agent_crew.config import Route, Settings
from my_agent_crew.config_parse import parse_routes

# OpenRouter's `reasoning.effort` levels. Empty means the request says nothing and the
# model thinks as much as its provider defaults to.
REASONING_EFFORTS = ("minimal", "low", "medium", "high")


def names(raw: dict[str, Any], key: str, agent_id: str) -> tuple[str, ...]:
    value = raw.get(key) or []
    if isinstance(value, str) or not isinstance(value, list):
        raise ValueError(f"agent {agent_id}: {key} must be a list of names")
    # A non-string entry is a typo in the manifest; coercing it would invent a name that
    # matches no agent and no tool, and the failure would only surface mid-task.
    if any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(f"agent {agent_id}: {key} must be a list of names")
    return tuple(v.strip() for v in value)


def settings_from(
    raw: dict[str, Any], agent_id: str, base: Settings, defaults: dict[str, Any]
) -> Settings:
    return replace(
        base,
        routes=_with_reasoning(
            parse_routes(raw["routes"]) if raw.get("routes") else base.routes,
            _reasoning(raw, agent_id),
        ),
        cost_cap_usd=float(
            raw.get("cost_cap_usd", defaults.get("cost_cap_usd", base.cost_cap_usd))
        ),
        max_steps=int(raw.get("max_steps", defaults.get("max_steps", base.max_steps))),
        autonomous_default=bool(
            raw.get("autonomous", defaults.get("autonomous", base.autonomous_default))
        ),
        shell_ask_patterns=(
            tuple(names(raw, "shell_ask_patterns", agent_id))
            if "shell_ask_patterns" in raw
            else base.shell_ask_patterns
        ),
        shell_allow_patterns=(
            tuple(names(raw, "shell_allow_patterns", agent_id))
            if "shell_allow_patterns" in raw
            else base.shell_allow_patterns
        ),
        tool_output_chars=int(raw.get("tool_output_chars", base.tool_output_chars)),
        shell_network=shell_network(raw, agent_id),
        shell_write_paths=names(raw, "shell_write_paths", agent_id),
        shell_deny_patterns=names(raw, "shell_deny_patterns", agent_id),
        write_paths=names(raw, "write_paths", agent_id),
    )


def shell_network(raw: dict[str, Any], agent_id: str) -> bool:
    value = raw.get("shell_network", True)
    # Only a real YAML bool: `"false"` read as truthy would leave the network open on
    # exactly the agent someone meant to close it for.
    if not isinstance(value, bool):
        raise ValueError(f"agent {agent_id}: shell_network must be true or false")
    return value


def _reasoning(raw: dict[str, Any], agent_id: str) -> str:
    value = raw.get("reasoning") or ""
    if value and value not in REASONING_EFFORTS:
        raise ValueError(
            f"agent {agent_id}: reasoning must be one of {list(REASONING_EFFORTS)}, got {value!r}"
        )
    return str(value)


def _with_reasoning(routes: tuple[Route, ...], effort: str) -> tuple[Route, ...]:
    """The effort goes on every route the agent may fall back to, so a fallback model
    thinks as hard as the first one rather than silently at its provider's default."""
    return tuple(replace(r, reasoning=effort) for r in routes) if effort else routes
