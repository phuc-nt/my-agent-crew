"""Settings: secrets from the environment only, everything else from env or config.yaml.

The yaml never carries a key — a config file gets copied, pasted and committed; an
environment variable does not.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, tzinfo
from pathlib import Path

import yaml

from my_agent_crew.clock import zone_for
from my_agent_crew.config_parse import DEFAULT_SHELL_ASK_PATTERNS, as_bool, ask_patterns

DEFAULT_ROUTES = "openrouter:deepseek/deepseek-v4-flash"
# The chat model is not expected to see pictures; `image_read` sends them here instead.
# An empty value turns the tool off.
DEFAULT_VISION_ROUTES = (
    "openrouter:google/gemini-2.5-flash-lite,openrouter:qwen/qwen3-vl-8b-instruct"
)
YAML_KEYS = (
    "routes",
    "vision_routes",
    "cost_cap_usd",
    "language",
    "timezone",
    "max_steps",
    "autonomous_default",
    "shell_ask_patterns",
    "approval_ttl_seconds",
    "tool_output_chars",
)
# Characters of one tool result the model gets to see; the rest is cut with a notice.
DEFAULT_TOOL_OUTPUT_CHARS = 8000
# How long a tool call waits for a decision before it is treated as denied. A pause
# nobody answers must not hold a conversation (and a job's channel) forever.
DEFAULT_APPROVAL_TTL_SECONDS = 600


@dataclass(frozen=True)
class Route:
    """One (provider, model) pair the chain may try; order in `Settings.routes` is priority."""

    provider: str
    model: str

    @classmethod
    def parse(cls, text: str) -> Route:
        provider, sep, model = text.strip().partition(":")
        if not sep or not provider or not model:
            raise ValueError(f"route must look like provider:model, got {text!r}")
        return cls(provider=provider, model=model)


@dataclass(frozen=True)
class Settings:
    home: Path
    routes: tuple[Route, ...]
    # Routes a picture is sent to; empty means no agent can read images.
    vision_routes: tuple[Route, ...] = ()
    openrouter_api_key: str | None = None
    brave_api_key: str | None = None
    tavily_api_key: str | None = None
    cost_cap_usd: float = 0.50
    language: str = "vi"
    # The person's IANA zone; empty means the machine's. See `clock.py`.
    timezone: str = ""
    max_steps: int = 12
    autonomous_default: bool = False
    shell_ask_patterns: tuple[str, ...] = DEFAULT_SHELL_ASK_PATTERNS
    approval_ttl_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS
    tool_output_chars: int = DEFAULT_TOOL_OUTPUT_CHARS

    @property
    def zone(self) -> tzinfo:
        return zone_for(self.timezone)

    def now(self) -> datetime:
        """The clock every schedule, daily note and chat label reads: aware, in the zone."""
        return datetime.now(self.zone)

    def today(self) -> date:
        return self.now().date()

    @property
    def workspace_dir(self) -> Path:
        return self.home / "workspace"

    @property
    def skills_dir(self) -> Path:
        return self.home / "skills"

    @property
    def users_dir(self) -> Path:
        return self.home / "users"

    @property
    def user_dir(self) -> Path:
        """What every agent knows about the person it works for, shared across the crew."""
        return self.users_dir / "owner"

    @property
    def db_path(self) -> Path:
        return self.home / "agent.sqlite3"


def _routes(value: str | Sequence[str] | None) -> tuple[Route, ...]:
    """Comma-separated text or a yaml list; empty (or null) is an empty tuple."""
    if not value:
        return ()
    parts = value.split(",") if isinstance(value, str) else list(value)
    return tuple(Route.parse(part) for part in parts if str(part).strip())


def _parse_routes(value: str | Sequence[str]) -> tuple[Route, ...]:
    routes = _routes(value)
    if not routes:
        raise ValueError("at least one route is required")
    return routes


def _vision_routes(env: Mapping[str, str], file_values: Mapping) -> tuple[Route, ...]:
    """An empty env value or an empty yaml list turns image reading off on purpose; only
    an absent setting takes the default."""
    from_env = env.get("MY_AGENT_VISION_ROUTES")
    if from_env is not None:
        return _routes(from_env)
    return _routes(file_values.get("vision_routes", DEFAULT_VISION_ROUTES))


def _from_yaml(home: Path) -> dict:
    path = home / "config.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    unknown = set(data) - set(YAML_KEYS)
    if unknown:
        raise ValueError(f"config.yaml: unknown keys {sorted(unknown)}")
    return data


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    home = Path(env.get("MY_AGENT_HOME") or Path.home() / ".my-agent-crew").expanduser()
    file_values = _from_yaml(home)
    routes_text = env.get("MY_AGENT_ROUTES") or file_values.get("routes") or DEFAULT_ROUTES
    settings = Settings(
        home=home,
        routes=_parse_routes(routes_text),
        vision_routes=_vision_routes(env, file_values),
        openrouter_api_key=env.get("OPENROUTER_API_KEY") or None,
        brave_api_key=env.get("BRAVE_API_KEY") or None,
        tavily_api_key=env.get("TAVILY_API_KEY") or None,
        cost_cap_usd=float(
            env.get("MY_AGENT_COST_CAP_USD") or file_values.get("cost_cap_usd", 0.50)
        ),
        language=env.get("MY_AGENT_LANGUAGE") or file_values.get("language", "vi"),
        timezone=str(env.get("MY_AGENT_TIMEZONE") or file_values.get("timezone") or ""),
        max_steps=int(env.get("MY_AGENT_MAX_STEPS") or file_values.get("max_steps", 12)),
        autonomous_default=as_bool(
            env.get("MY_AGENT_AUTONOMOUS", file_values.get("autonomous_default", False))
        ),
        shell_ask_patterns=ask_patterns(
            env.get("MY_AGENT_SHELL_ASK_PATTERNS"), file_values.get("shell_ask_patterns")
        ),
        approval_ttl_seconds=int(
            env.get("MY_AGENT_APPROVAL_TTL_SECONDS")
            or file_values.get("approval_ttl_seconds", DEFAULT_APPROVAL_TTL_SECONDS)
        ),
        tool_output_chars=int(
            env.get("MY_AGENT_TOOL_OUTPUT_CHARS")
            or file_values.get("tool_output_chars", DEFAULT_TOOL_OUTPUT_CHARS)
        ),
    )
    positive = (settings.max_steps, settings.approval_ttl_seconds, settings.tool_output_chars)
    if min(positive) < 1 or settings.cost_cap_usd < 0:
        raise ValueError(
            "max_steps, approval_ttl_seconds and tool_output_chars must be >= 1, cost_cap_usd >= 0"
        )
    zone_for(settings.timezone)  # an unknown zone fails here, not in the first job
    return settings


def ensure_home(settings: Settings) -> Settings:
    facts_dir = settings.user_dir / "facts"
    for path in (settings.home, settings.workspace_dir, settings.skills_dir, facts_dir):
        path.mkdir(parents=True, exist_ok=True)
    return replace(settings, home=settings.home.resolve())
