"""Settings: secrets from the environment only, everything else from env or config.yaml.

The yaml never carries a key — a config file gets copied, pasted and committed; an
environment variable does not.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

DEFAULT_ROUTES = "openrouter:deepseek/deepseek-v4-flash"
YAML_KEYS = ("routes", "cost_cap_usd", "language", "max_steps", "autonomous_default")


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
    openrouter_api_key: str | None = None
    brave_api_key: str | None = None
    tavily_api_key: str | None = None
    cost_cap_usd: float = 0.50
    language: str = "vi"
    max_steps: int = 12
    autonomous_default: bool = False

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


def _parse_routes(value: str | Sequence[str]) -> tuple[Route, ...]:
    parts = value.split(",") if isinstance(value, str) else list(value)
    routes = tuple(Route.parse(part) for part in parts if str(part).strip())
    if not routes:
        raise ValueError("at least one route is required")
    return routes


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
        openrouter_api_key=env.get("OPENROUTER_API_KEY") or None,
        brave_api_key=env.get("BRAVE_API_KEY") or None,
        tavily_api_key=env.get("TAVILY_API_KEY") or None,
        cost_cap_usd=float(
            env.get("MY_AGENT_COST_CAP_USD") or file_values.get("cost_cap_usd", 0.50)
        ),
        language=env.get("MY_AGENT_LANGUAGE") or file_values.get("language", "vi"),
        max_steps=int(env.get("MY_AGENT_MAX_STEPS") or file_values.get("max_steps", 12)),
        autonomous_default=_as_bool(
            env.get("MY_AGENT_AUTONOMOUS", file_values.get("autonomous_default", False))
        ),
    )
    if settings.max_steps < 1 or settings.cost_cap_usd < 0:
        raise ValueError("max_steps must be >= 1 and cost_cap_usd >= 0")
    return settings


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def ensure_home(settings: Settings) -> Settings:
    facts_dir = settings.user_dir / "facts"
    for path in (settings.home, settings.workspace_dir, settings.skills_dir, facts_dir):
        path.mkdir(parents=True, exist_ok=True)
    return replace(settings, home=settings.home.resolve())
