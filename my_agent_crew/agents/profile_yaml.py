"""Reading `MY_AGENT_HOME/agents/<id>/agent.yaml` into an `AgentProfile`.

Kept apart from the profile dataclasses so what an agent *is* stays readable without the
validation that turns a hand-written file into one. Unknown keys are an error rather than
a silent no-op: a typo in a profile should say so, not quietly change nothing.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from my_agent_crew.agents.channels import parse_telegram
from my_agent_crew.agents.profile import (
    DEFAULT_AGENT_ID,
    PERSONA_FILES,
    PROFILE_KEYS,
    SCHEDULE_KEYS,
    AgentProfile,
    Schedule,
    consolidate_schedule,
    default_profile,
)
from my_agent_crew.config import Settings, _parse_routes


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
    consolidate_cron = str(raw.get("memory_consolidate") or "")
    if consolidate_cron:
        schedules.append(consolidate_schedule(consolidate_cron))
    telegram = parse_telegram(raw["telegram"], agent_id) if raw.get("telegram") else None
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
        telegram=telegram,
        memory_consolidate=consolidate_cron,
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
