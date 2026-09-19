"""Agent profiles. `MY_AGENT_HOME/agents/<id>/agent.yaml` describes one agent: its
persona files, workspace, model routes and schedules. The `default` agent always exists
and is described by the top-level settings, so a fresh home works with no profile at all."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

from my_agent_crew.config import Settings, _parse_routes

DEFAULT_AGENT_ID = "default"
PERSONA_FILES = ("AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md")
PROFILE_KEYS = {
    "name",
    "description",
    "routes",
    "workspace",
    "persona_files",
    "skills_dirs",
    "cost_cap_usd",
    "max_steps",
    "autonomous",
    "schedules",
}
SCHEDULE_KEYS = {"id", "name", "cron", "every", "prompt", "command", "enabled"}


@dataclass(frozen=True)
class Schedule:
    id: str
    name: str
    cron: str | None = None
    every: str | None = None
    prompt: str | None = None
    command: str | None = None
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "cron": self.cron,
            "every": self.every,
            "prompt": self.prompt,
            "command": self.command,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    dir: Path
    workspace: Path
    settings: Settings
    description: str = ""
    persona_files: tuple[str, ...] = PERSONA_FILES
    skills_dirs: tuple[Path, ...] = ()
    schedules: tuple[Schedule, ...] = field(default_factory=tuple)

    @property
    def memory_dir(self) -> Path:
        return self.dir / "memory"

    @property
    def memory_file(self) -> Path:
        return self.dir / "MEMORY.md"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "dir": str(self.dir),
            "workspace": str(self.workspace),
            "routes": [{"provider": r.provider, "model": r.model} for r in self.settings.routes],
            "cost_cap_usd": self.settings.cost_cap_usd,
            "max_steps": self.settings.max_steps,
            "autonomous": self.settings.autonomous_default,
            "persona_files": [f for f in self.persona_files if (self.dir / f).is_file()],
            "schedules": [s.to_dict() for s in self.schedules],
        }


def default_profile(settings: Settings) -> AgentProfile:
    return AgentProfile(
        id=DEFAULT_AGENT_ID,
        name="Trợ lý",
        dir=settings.home,
        workspace=settings.workspace_dir,
        settings=settings,
        skills_dirs=(settings.skills_dir,),
    )


def _schedule(raw: dict[str, Any], agent_id: str, index: int) -> Schedule:
    unknown = set(raw) - SCHEDULE_KEYS
    if unknown:
        raise ValueError(f"agent {agent_id}: schedule has unknown keys {sorted(unknown)}")
    if bool(raw.get("cron")) == bool(raw.get("every")):
        raise ValueError(f"agent {agent_id}: schedule needs exactly one of cron / every")
    if bool(raw.get("prompt")) == bool(raw.get("command")):
        raise ValueError(f"agent {agent_id}: schedule needs exactly one of prompt / command")
    job_id = str(raw.get("id") or f"job-{index}")
    return Schedule(
        id=job_id,
        name=str(raw.get("name") or job_id),
        cron=raw.get("cron"),
        every=raw.get("every"),
        prompt=raw.get("prompt"),
        command=raw.get("command"),
        enabled=bool(raw.get("enabled", True)),
    )


def _resolve(base: Path, value: str) -> Path:
    return (base / Path(value).expanduser()).resolve()


def parse_profile(
    agent_id: str, agent_dir: Path, raw: dict[str, Any], base: Settings
) -> AgentProfile:
    unknown = set(raw) - PROFILE_KEYS
    if unknown:
        raise ValueError(f"agent {agent_id}: unknown keys {sorted(unknown)}")
    settings = replace(
        base,
        routes=_parse_routes(raw["routes"]) if raw.get("routes") else base.routes,
        cost_cap_usd=float(raw.get("cost_cap_usd", base.cost_cap_usd)),
        max_steps=int(raw.get("max_steps", base.max_steps)),
        autonomous_default=bool(raw.get("autonomous", base.autonomous_default)),
    )
    workspace = _resolve(agent_dir, str(raw.get("workspace") or "workspace"))
    skills_dirs = [agent_dir / "skills"] + [
        _resolve(agent_dir, str(d)) for d in raw.get("skills_dirs") or []
    ]
    schedules = [_schedule(s, agent_id, i) for i, s in enumerate(raw.get("schedules") or [])]
    return AgentProfile(
        id=agent_id,
        name=str(raw.get("name") or agent_id),
        dir=agent_dir,
        workspace=workspace,
        settings=settings,
        description=str(raw.get("description") or ""),
        persona_files=tuple(raw.get("persona_files") or PERSONA_FILES),
        skills_dirs=tuple(skills_dirs),
        schedules=tuple(schedules),
    )


def load_profiles(settings: Settings) -> list[AgentProfile]:
    """The default agent first, then every `agents/<id>/agent.yaml`, sorted by id."""
    profiles = [default_profile(settings)]
    root = settings.home / "agents"
    if not root.is_dir():
        return profiles
    for agent_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest = agent_dir / "agent.yaml"
        if not manifest.is_file():
            continue
        if agent_dir.name == DEFAULT_AGENT_ID:
            raise ValueError(f"agent id {DEFAULT_AGENT_ID!r} is reserved")
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        profiles.append(parse_profile(agent_dir.name, agent_dir.resolve(), raw, settings))
    return profiles


def profile_ids(profiles: Sequence[AgentProfile]) -> list[str]:
    return [p.id for p in profiles]
