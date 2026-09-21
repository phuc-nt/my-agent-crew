"""Agents written as markdown, the way Claude Code and opencode keep their subagents:
`agents/<id>.md` with a front matter (`name`, `description`, `model`, `tools`, `mode`,
`delegates`, `workspace`) and the persona as the body. Each becomes a crew member next to
the ones described by `agents/<id>/agent.yaml`; on the same id the yaml wins, so a kit
copied in never silently replaces an agent the person configured by hand.

`load_profiles` is the crew: the master, the yaml agents, then the kit agents, every one
of them with its kits attached."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from my_agent_crew.agents.kit import Kit, agent_kits, crew_kits, split_front_matter, with_kits
from my_agent_crew.agents.kit_hooks import TOOL_ALIASES
from my_agent_crew.agents.profile import DEFAULT_AGENT_ID, MODES, WORK, AgentProfile
from my_agent_crew.agents.profile_yaml import load_yaml_profiles, parse_profile
from my_agent_crew.config import Settings

logger = logging.getLogger(__name__)

_UNSAFE_ID = re.compile(r"[^a-z0-9_-]+")
MAX_DESCRIPTION_CHARS = 240
# The harness names for our tools, the other way round from `TOOL_ALIASES`, plus the
# names that mean the same tool in more than one harness.
TOOL_NAMES = {alias.lower(): name for name, alias in TOOL_ALIASES.items()}
TOOL_NAMES.update({"multiedit": "workspace_edit", "agent": "delegate", "ls": "workspace_list"})
# Tools no harness front matter can name; an agent that lists tools keeps these.
IMPLICIT_TOOLS = (
    "memory_save",
    "memory_search",
    "user_memory_save",
    "user_memory_forget",
    "skill_read",
    "image_read",
)
EDITING_TOOLS = {"workspace_edit", "workspace_write"}


def agent_id_for(meta: dict[str, Any], path: Path) -> str:
    raw = str(meta.get("name") or path.stem).strip().lower()
    return _UNSAFE_ID.sub("-", raw).strip("-") or path.stem


def _list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def tool_names(value: Any) -> list[str]:
    """Harness tool names mapped to ours; a name we have no tool for is dropped, since
    the harness-only tools (`TaskCreate`, `NotebookEdit`) have no meaning here."""
    names: list[str] = []
    for raw in _list(value):
        name = TOOL_NAMES.get(raw.lower(), raw if raw == raw.lower() else "")
        if name and name not in names:
            names.append(name)
    if names:
        names += [t for t in IMPLICIT_TOOLS if t not in names]
    return names


def routes_for(model: Any) -> list[str]:
    """`provider:model` is a route; a harness alias (`sonnet`, `inherit`) means the
    crew's own routes."""
    return [m for m in _list(model) if ":" in m]


def agent_raw(meta: dict[str, Any], body_path: Path, kit: Kit) -> dict[str, Any]:
    tools = tool_names(meta.get("tools"))
    mode = str(meta.get("mode") or "")
    if mode not in MODES:
        mode = WORK if EDITING_TOOLS & set(tools) else ""
    raw: dict[str, Any] = {
        "name": str(meta.get("name") or body_path.stem),
        "description": " ".join(str(meta.get("description") or "").split())[:MAX_DESCRIPTION_CHARS],
        "persona_files": [str(body_path)],
        "workspace": str(meta.get("workspace") or kit.workspace),
        "tools": tools,
        "delegates": _list(meta.get("delegates")),
    }
    if mode:
        raw["mode"] = mode
    if routes_for(meta.get("model")):
        raw["routes"] = routes_for(meta.get("model"))
    return raw


def parse_agent_md(path: Path, kit: Kit, settings: Settings) -> AgentProfile:
    """The profile lives in `home/agents/<id>` like any other (memory goes there); only
    its persona is read from the kit's markdown."""
    meta, _ = split_front_matter(path.read_text(encoding="utf-8"))
    agent_id = agent_id_for(meta, path)
    agent_dir = settings.home / "agents" / agent_id
    raw = agent_raw(meta, path.resolve(), kit)
    if not Path(raw["workspace"]).is_absolute():
        raw["workspace"] = str(kit.project / raw["workspace"])
    return parse_profile(agent_id, agent_dir, raw, settings)


def load_kit_agents(
    kits: Sequence[Kit], settings: Settings, taken: Sequence[str]
) -> list[AgentProfile]:
    """Kit agents whose id no yaml agent holds; a later kit shadows an earlier one."""
    found: dict[str, AgentProfile] = {}
    for kit in kits:
        if not kit.brings_agents:
            continue
        for path in kit.agent_files:
            try:
                profile = parse_agent_md(path, kit, settings)
            except ValueError as exc:
                logger.warning("kit agent %s skipped: %s", path, exc)
                continue
            if profile.id in taken or profile.id == DEFAULT_AGENT_ID:
                logger.info("kit agent %s: id %s already taken, yaml wins", path, profile.id)
                continue
            found[profile.id] = profile
    return list(found.values())


def load_profiles(settings: Settings) -> list[AgentProfile]:
    """The default agent first, the yaml agents sorted by id, then the kit agents of the
    home and of every yaml agent's own kit, in that order."""
    profiles = load_yaml_profiles(settings)
    kits = crew_kits(settings.home)
    for profile in profiles[1:]:
        kits += [k for k in agent_kits(profile) if k.brings_agents and k not in kits]
    profiles += load_kit_agents(kits, settings, [p.id for p in profiles])
    return [with_kits(profile) for profile in profiles]
