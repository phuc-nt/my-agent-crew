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

from my_agent_crew.agents.approval_ttl import parse_approval_ttl
from my_agent_crew.agents.channels import parse_telegram
from my_agent_crew.agents.profile import (
    ASSISTANT,
    DEFAULT_AGENT_ID,
    MODES,
    PERSONA_FILES,
    PROFILE_KEYS,
    WORK,
    WORK_DEFAULTS,
    AgentProfile,
    consolidate_schedule,
    default_profile,
)
from my_agent_crew.agents.profile_places import followed, persona_names
from my_agent_crew.agents.profile_settings import listed, names, settings_from
from my_agent_crew.agents.schedule import ACTIONS, SCHEDULE_KEYS, Schedule
from my_agent_crew.config import Settings
from my_agent_crew.script.check import parse
from my_agent_crew.script.limits import MAX_SOURCE_CHARS, ScriptError

MASTER_MANIFEST = "agent.yaml"


def _script(raw: dict[str, Any], where: str) -> tuple[str | None, str | None]:
    """A script job's own two keys: the script, and the prompt what it prints goes on with.

    The script is read here as far as it can be without running it, with the check a script
    of a turn meets before it runs. One that cannot be read would fail every time its job
    came round, long after the file was written, so the file is refused instead."""
    script, then_prompt = raw.get("script"), raw.get("then_prompt")
    if then_prompt is not None and not (isinstance(then_prompt, str) and then_prompt.strip()):
        raise ValueError(f"{where}: then_prompt must be a non-empty string")
    if not script:
        return None, None
    if not isinstance(script, str) or not script.strip():
        raise ValueError(f"{where}: script must be a non-empty string")
    if len(script) > MAX_SOURCE_CHARS:
        raise ValueError(f"{where}: script is longer than {MAX_SOURCE_CHARS} characters")
    try:
        parse(script)
    except ScriptError as exc:
        raise ValueError(f"{where}: script: {exc}") from exc
    return script, then_prompt


def _schedule(raw: dict[str, Any], agent_id: str, index: int) -> Schedule:
    unknown = set(raw) - SCHEDULE_KEYS
    if unknown:
        raise ValueError(f"agent {agent_id}: schedule has unknown keys {sorted(unknown)}")
    if bool(raw.get("cron")) == bool(raw.get("every")):
        raise ValueError(f"agent {agent_id}: schedule needs exactly one of cron / every")
    if sum(bool(raw.get(action)) for action in ACTIONS) != 1:
        raise ValueError(
            f"agent {agent_id}: schedule needs exactly one of prompt / command / script"
        )
    if raw.get("then_prompt") is not None and not raw.get("script"):
        raise ValueError(f"agent {agent_id}: schedule takes then_prompt only beside script")
    job_id = str(raw.get("id") or f"job-{index}")
    where = f"agent {agent_id}: schedule {job_id}"
    script, then_prompt = _script(raw, where)
    return Schedule(
        id=job_id,
        name=str(raw.get("name") or job_id),
        cron=raw.get("cron"),
        every=raw.get("every"),
        # A row's two other actions are absent beside a script, not blank.
        prompt=raw.get("prompt") if script is None else None,
        command=raw.get("command") if script is None else None,
        enabled=bool(raw.get("enabled", True)),
        skills=tuple(str(s) for s in listed(raw, "skills", where)),
        approval_ttl_seconds=parse_approval_ttl(raw.get("approval_ttl_seconds"), where),
        script=script,
        then_prompt=then_prompt,
    )


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
    except (TypeError, OverflowError) as exc:
        # float({}) and int([]) raise TypeError, int(.inf) OverflowError: no number of the
        # kind asked. The caller reports a bad profile by catching ValueError.
        raise ValueError(f"agent {agent_id}: {exc}") from exc
    if settings.tool_output_chars < 1:
        raise ValueError(f"agent {agent_id}: tool_output_chars must be >= 1")
    who = f"agent {agent_id}"
    workspace = followed(agent_dir, str(raw.get("workspace") or "workspace"), who, "workspace")
    # A writable path outside the workspace could be ~/.zshrc or a LaunchAgent plist.
    for key in ("shell_write_paths", "write_paths"):
        for path in getattr(settings, key):
            if not (workspace / path).resolve().is_relative_to(workspace.resolve()):
                raise ValueError(f"agent {agent_id}: {key} {path!r} leaves the workspace")
    skills_dirs = [agent_dir / "skills"] + [
        followed(agent_dir, str(d), who, "skills_dirs")
        for d in listed(raw, "skills_dirs", who, "folders")
    ]
    # A row that is no mapping has no field to read.
    rows = listed(raw, "schedules", who, "mappings", dict)
    schedules = [_schedule(row, agent_id, i) for i, row in enumerate(rows)]
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
        # A name that is no text names no file: kept, it fails the next listing of the agents
        # and every turn of this one. So does one the folder cannot be asked for.
        persona_files=persona_names(
            listed(raw, "persona_files", who, each=str) or PERSONA_FILES, agent_dir, who
        ),
        skills_dirs=tuple(skills_dirs),
        schedules=tuple(schedules),
        telegram=telegram,
        memory_consolidate=consolidate_cron,
        mode=mode,
        delegates=names(raw, "delegates", agent_id),
        tools=names(raw, "tools", agent_id),
        mcp=names(raw, "mcp", agent_id),
    )


def read_profile(
    agent_id: str, agent_dir: Path, raw: dict[str, Any], settings: Settings
) -> AgentProfile:
    """What an agent's file, once read, makes of the agent. The start goes through here for
    every file and a save from the web for the file it is about to write, so the two cannot
    read one file two ways. The master goes by the default's name when its file gives
    none, and not by its id."""
    if agent_id == DEFAULT_AGENT_ID:
        raw = {"name": default_profile(settings).name} | raw
    return parse_profile(agent_id, agent_dir, raw, settings)


def load_master_profile(settings: Settings) -> AgentProfile:
    """The default agent, read from `MY_AGENT_HOME/agent.yaml` when the person wrote one.
    Its workspace and skills default to the home's own, the same places the settings
    describe, so writing the file changes only what it states."""
    manifest = settings.home / MASTER_MANIFEST
    if not manifest.is_file():
        return default_profile(settings)
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    return read_profile(DEFAULT_AGENT_ID, settings.home, raw, settings)


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
        profiles.append(read_profile(agent_dir.name, agent_dir.resolve(), raw, settings))
    return profiles
