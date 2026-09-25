"""Reading `MY_AGENT_HOME/agents/<id>/agent.yaml` (and the master's own
`MY_AGENT_HOME/agent.yaml`) into an `AgentProfile`.

Kept apart from the profile dataclasses so what an agent *is* stays readable without the
validation that turns a hand-written file into one. Unknown keys are an error rather than
a silent no-op: a typo in a profile should say so, not quietly change nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from my_agent_crew.agents.channels import parse_telegram
from my_agent_crew.agents.profile import (
    ASSISTANT,
    DEFAULT_AGENT_ID,
    MODES,
    PERSONA_FILES,
    PROFILE_KEYS,
    SCHEDULE_KEYS,
    WORK,
    WORK_DEFAULTS,
    AgentProfile,
    Schedule,
    consolidate_schedule,
    default_profile,
)
from my_agent_crew.agents.profile_settings import names, settings_from
from my_agent_crew.config import Settings

MASTER_MANIFEST = "agent.yaml"


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
        skills=tuple(str(s) for s in raw.get("skills") or []),
    )


def _resolve(base: Path, value: str) -> Path:
    return (base / Path(value).expanduser()).resolve()


def _mode(raw: dict[str, Any], agent_id: str) -> str:
    mode = str(raw.get("mode") or ASSISTANT)
    if mode not in MODES:
        raise ValueError(f"agent {agent_id}: mode must be one of {list(MODES)}, got {mode!r}")
    return mode


def parse_profile(
    agent_id: str, agent_dir: Path, raw: dict[str, Any], base: Settings
) -> AgentProfile:
    unknown = set(raw) - PROFILE_KEYS
    if unknown:
        raise ValueError(f"agent {agent_id}: unknown keys {sorted(unknown)}")
    mode = _mode(raw, agent_id)
    # Work mode moves the defaults; anything the profile states itself still wins.
    defaults = WORK_DEFAULTS if mode == WORK else {}
    try:
        settings = settings_from(raw, agent_id, base, defaults)
    except TypeError as exc:
        # float({}) and int([]) raise TypeError: a number written as something else. The
        # caller reports a bad profile by catching ValueError.
        raise ValueError(f"agent {agent_id}: {exc}") from exc
    if settings.tool_output_chars < 1:
        raise ValueError(f"agent {agent_id}: tool_output_chars must be >= 1")
    workspace = _resolve(agent_dir, str(raw.get("workspace") or "workspace"))
    # A writable path outside the workspace could be ~/.zshrc or a LaunchAgent plist.
    for key in ("shell_write_paths", "write_paths"):
        for path in getattr(settings, key):
            if not (workspace / path).resolve().is_relative_to(workspace.resolve()):
                raise ValueError(f"agent {agent_id}: {key} {path!r} leaves the workspace")
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
        mode=mode,
        delegates=names(raw, "delegates", agent_id),
        tools=names(raw, "tools", agent_id),
    )


def load_master_profile(settings: Settings) -> AgentProfile:
    """The default agent, read from `MY_AGENT_HOME/agent.yaml` when the person wrote one.
    Its workspace and skills default to the home's own, the same places the settings
    describe, so writing the file changes only what it states."""
    manifest = settings.home / MASTER_MANIFEST
    if not manifest.is_file():
        return default_profile(settings)
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    raw.setdefault("name", default_profile(settings).name)
    return parse_profile(DEFAULT_AGENT_ID, settings.home, raw, settings)


def load_yaml_profiles(settings: Settings) -> list[AgentProfile]:
    """The default agent first, then every `agents/<id>/agent.yaml`, sorted by id. The
    whole crew, kits included, is `agents.load_profiles`."""
    profiles = [load_master_profile(settings)]
    root = settings.home / "agents"
    if not root.is_dir():
        return profiles
    # A removed agent is moved aside rather than deleted, and it keeps its manifest.
    # Skipping the whole dot-prefixed set keeps those out and leaves room for other
    # bookkeeping folders without every one of them resurrecting an agent.
    for agent_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name[:1] != "."):
        manifest = agent_dir / "agent.yaml"
        if not manifest.is_file():
            continue
        if agent_dir.name == DEFAULT_AGENT_ID:
            raise ValueError(f"agent id {DEFAULT_AGENT_ID!r} is reserved")
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        profiles.append(parse_profile(agent_dir.name, agent_dir.resolve(), raw, settings))
    return profiles
