"""The runtime settings one `agent.yaml` overrides: routes and how hard they think, the
cost and step caps, and what the agent's shell may do. Split out of `profile_yaml` so the
file that reads a profile stays readable."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from my_agent_crew.agents.profile_browser import browser_of
from my_agent_crew.agents.profile_desktop import desktop_of
from my_agent_crew.config import SCRIPT_GATED, SCRIPT_NONE, SCRIPT_READ_ONLY, Route, Settings
from my_agent_crew.config_parse import parse_routes

# OpenRouter's `reasoning.effort` levels. Empty means the request says nothing and the
# model thinks as much as its provider defaults to.
REASONING_EFFORTS = ("minimal", "low", "medium", "high")
# The words `script_calls` takes, from the least a script may do to the most.
SCRIPT_CALLS = (SCRIPT_NONE, SCRIPT_READ_ONLY, SCRIPT_GATED)


def names(raw: dict[str, Any], key: str, agent_id: str) -> tuple[str, ...]:
    value = raw.get(key) or []
    if isinstance(value, str) or not isinstance(value, list):
        raise ValueError(f"agent {agent_id}: {key} must be a list of names")
    # A non-string entry is a typo in the manifest; coercing it would invent a name that
    # matches no agent and no tool, and the failure would only surface mid-task.
    if any(not isinstance(v, str) or not v.strip() for v in value):
        raise ValueError(f"agent {agent_id}: {key} must be a list of names")
    return tuple(v.strip() for v in value)


def listed(
    raw: dict[str, Any], key: str, where: str, of: str = "names", each: type | None = None
) -> tuple[Any, ...]:
    """What a key that holds a list holds, and nothing where the file leaves it out.

    A value with nothing to go through (a number, a switch) is a bad profile and is told as
    one here: gone through as a list, it raised an error nobody reads as a bad profile, and
    a start or an edit died on it. So is an entry that is not `each`, where the reader can
    do nothing with any other: kept, it failed whoever listed the agent next."""
    refusal = ValueError(f"{where}: {key} must be a list of {of}")
    try:
        entries = tuple(raw.get(key) or ())
    except TypeError:
        raise refusal from None
    if each is not None and not all(isinstance(entry, each) for entry in entries):
        raise refusal
    return entries


def settings_from(
    raw: dict[str, Any], agent_id: str, base: Settings, defaults: dict[str, Any]
) -> Settings:
    effort = _reasoning(raw, agent_id)
    return replace(
        base,
        routes=_with_reasoning(
            parse_routes(raw["routes"]) if raw.get("routes") else base.routes, effort
        ),
        escalation_route=_escalation_route(raw, agent_id, effort),
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
        script_calls=script_calls(raw, agent_id),
        script_llm=script_llm(raw, agent_id),
        write_paths=names(raw, "write_paths", agent_id),
        browser=browser_of(raw, agent_id, base.browser),
        desktop=desktop_of(raw, agent_id, base.desktop),
    )


def shell_network(raw: dict[str, Any], agent_id: str) -> bool:
    value = raw.get("shell_network", True)
    # Only a real YAML bool: `"false"` read as truthy would leave the network open on
    # exactly the agent someone meant to close it for.
    if not isinstance(value, bool):
        raise ValueError(f"agent {agent_id}: shell_network must be true or false")
    return value


def script_calls(raw: dict[str, Any], agent_id: str) -> str:
    """What a script of the agent may call, or that it is handed no script tool at all.
    Read from the agent's own file and never from the settings it inherits: a script that
    changes things is on only where somebody wrote so, and a value nobody knows is a
    mistake to be told of, not a default."""
    value = raw.get("script_calls", SCRIPT_READ_ONLY)
    known = f"agent {agent_id}: script_calls must be {', '.join(SCRIPT_CALLS[:-1])}"
    known += f" or {SCRIPT_CALLS[-1]}"
    if isinstance(value, bool):
        # What switching the scripts off is first written as, and none of the three words.
        raise ValueError(
            f"{known}, not a boolean (YAML reads a bare off, no, false, on, yes or true as"
            f" one): write {SCRIPT_NONE} to hand the agent no tool_script, or the one of the"
            " three meant"
        )
    if value not in SCRIPT_CALLS:
        raise ValueError(known)
    return value


def script_llm(raw: dict[str, Any], agent_id: str) -> bool:
    """Whether a script of the agent may ask a model itself. From the agent's own file."""
    value = raw.get("script_llm", True)
    # Only a real YAML bool: `"false"` read as truthy would leave the scripts paying for
    # a model on exactly the agent someone meant to stop.
    if not isinstance(value, bool):
        raise ValueError(f"agent {agent_id}: script_llm must be true or false")
    return value


def _reasoning(raw: dict[str, Any], agent_id: str) -> str:
    value = raw.get("reasoning") or ""
    if value and value not in REASONING_EFFORTS:
        raise ValueError(
            f"agent {agent_id}: reasoning must be one of {list(REASONING_EFFORTS)}, got {value!r}"
        )
    return str(value)


def _escalation_route(raw: dict[str, Any], agent_id: str, effort: str) -> Route | None:
    """The route a stuck turn of this agent moves to (`agent/escalation.py`), thinking as
    hard as its other routes. Read from the agent's own file and never from the settings
    it inherits, so it is on only where somebody wrote it."""
    value = raw.get("escalation_route")
    if not value:
        return None
    try:
        return replace(Route.parse(value), reasoning=effort)
    except ValueError as exc:
        raise ValueError(f"agent {agent_id}: escalation_route: {exc}") from exc


def _with_reasoning(routes: tuple[Route, ...], effort: str) -> tuple[Route, ...]:
    """The effort goes on every route the agent may fall back to, so a fallback model
    thinks as hard as the first one rather than silently at its provider's default."""
    return tuple(replace(r, reasoning=effort) for r in routes) if effort else routes
