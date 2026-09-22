"""What the agent-editing routes share.

The lock lives here rather than in either route module because both of them write to
the same files: two edits arriving together must queue, whichever endpoint they came in
through. One lock object, imported in both places, is what makes that true.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from ruamel.yaml import YAMLError

from my_agent_crew import texts
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.agents.profile_edit import apply_patch, check_agent_id
from my_agent_crew.agents.profile_write import MANIFEST, read_raw
from my_agent_crew.agents.profile_yaml import MASTER_MANIFEST
from my_agent_crew.server.runtime import Runtime

write_lock = asyncio.Lock()


def manifest_path(rt: Runtime, agent_id: str) -> Path:
    """The master's profile is the home's own `agent.yaml`; everyone else has one in
    their folder.

    The id becomes a path segment here, so it is checked rather than trusted. Today every
    caller has already matched it against a live agent, which would catch anything odd —
    but that is a property of the callers, not of this function, and it is the kind of
    thing a later refactor quietly removes.
    """
    if agent_id == DEFAULT_AGENT_ID:
        return rt.settings.home / MASTER_MANIFEST
    try:
        check_agent_id(agent_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return rt.settings.home / "agents" / agent_id / MANIFEST


def patched(rt: Runtime, agent_id: str, patch: dict[str, Any]) -> Any:
    """The manifest on disk with the patch applied, or a 422 saying what is wrong with it.

    A hand-edited file that no longer parses is the person's to fix, not something to
    overwrite: the edit they sent names a few keys and would silently drop everything
    the broken file still holds.
    """
    try:
        return apply_patch(read_raw(manifest_path(rt, agent_id)), patch)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except YAMLError as exc:
        raise HTTPException(422, texts.MANIFEST_BROKEN.format(error=str(exc))) from exc


def existing(rt: Runtime, agent_id: str) -> AgentProfile:
    try:
        return rt.deps_for(agent_id).agent
    except KeyError as exc:
        raise HTTPException(404, texts.AGENT_UNKNOWN.format(agent_id=agent_id)) from exc


def check_editable(rt: Runtime, profile: AgentProfile) -> None:
    """A kit agent has no manifest of its own; its persona file is where it came from."""
    if profile.id == DEFAULT_AGENT_ID or manifest_path(rt, profile.id).is_file():
        return
    source = profile.persona_files[0] if profile.persona_files else profile.dir
    raise HTTPException(409, texts.AGENT_FROM_KIT.format(agent_id=profile.id, path=str(source)))
