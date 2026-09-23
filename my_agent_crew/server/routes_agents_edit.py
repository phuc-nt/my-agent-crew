"""Creating, editing and removing agents from the web.

An edit is validated, then wired into the running crew, then written to `agent.yaml`.
Building the agent is the last step that can fail, so doing it before the write is what
keeps a refused edit off the disk — the alternative leaves a file claiming a change the
answer said was rejected, which then takes effect at the next restart.

Agents that came from a kit are read-only here. Their profile is a markdown file inside
a project someone else maintains, and writing a `agent.yaml` beside it would shadow the
kit rather than edit it — a surprise worth refusing instead of performing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew import texts
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.agents.profile_edit import (
    check_agent_id,
    check_inside_home,
    restart_reasons,
    validated,
)
from my_agent_crew.agents.profile_write import create_agent_dir, trash_agent, write_raw
from my_agent_crew.server.agent_edit_common import (
    check_editable,
    existing,
    manifest_path,
    patched,
    write_lock,
)
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import check_delegates
from my_agent_crew.server.runtime_connections import channel_key, sync_channel

router = APIRouter(tags=["agents"])


class CreateRequest(BaseModel):
    agent_id: str
    profile: dict[str, Any] = {}


class PatchRequest(BaseModel):
    profile: dict[str, Any]


def save(rt: Runtime, agent_id: str, raw: Any, agent_dir: Path) -> AgentProfile:
    """Validate, then wire, then write — in that order, so a refused edit leaves both the
    file and the running crew as they were.

    Wiring before writing is what makes that true. Building the agent is the step that
    can still fail on a profile that parsed cleanly — an unusable route, a directory that
    cannot be made — and a file already written at that point would say the edit worked
    while the answer said it did not, then take effect at the next restart.
    """
    try:
        profile = validated(agent_id, agent_dir, raw, rt.settings)
        check_inside_home(profile, rt.settings.home)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    peers = [p for p in rt.profiles() if p.id != agent_id] + [profile]
    try:
        check_delegates(peers)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        rt.replace_agent(profile)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    write_raw(manifest_path(rt, agent_id), raw)
    return profile


@router.post("/agents", status_code=201)
async def create_agent(body: CreateRequest, rt: Rt) -> dict[str, Any]:
    try:
        check_agent_id(body.agent_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    async with write_lock:
        if body.agent_id in rt.agents or manifest_path(rt, body.agent_id).is_file():
            raise HTTPException(409, texts.AGENT_EXISTS.format(agent_id=body.agent_id))
        agent_dir = create_agent_dir(rt.settings.home, body.agent_id)
        raw = patched(rt, body.agent_id, body.profile)
        before = channel_key(rt.agents, os.environ)
        profile = save(rt, body.agent_id, raw, agent_dir)
        await sync_channel(rt, before)
    return {"profile": profile.to_dict(), "restart_required": restart_reasons(None, profile)}


@router.patch("/agents/{agent_id}")
async def patch_agent(agent_id: str, body: PatchRequest, rt: Rt) -> dict[str, Any]:
    async with write_lock:
        old = existing(rt, agent_id)
        check_editable(rt, old)
        raw = patched(rt, agent_id, body.profile)
        before = channel_key(rt.agents, os.environ)
        profile = save(rt, agent_id, raw, old.dir)
        # The bot is built from the master's block; a changed chat or token takes effect
        # now rather than after a restart nobody remembers to do. Any other edit only
        # hands the running bot the rebuilt agent, without cutting off its poll.
        await sync_channel(rt, before)
    return {"profile": profile.to_dict(), "restart_required": restart_reasons(old, profile)}


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, rt: Rt) -> dict[str, Any]:
    async with write_lock:
        profile = existing(rt, agent_id)
        if agent_id == DEFAULT_AGENT_ID:
            raise HTTPException(409, texts.AGENT_MASTER_UNDELETABLE)
        check_editable(rt, profile)
        # Removing an agent someone still delegates to would leave that agent's own
        # profile invalid, and the server would refuse to start next time.
        users = [p.id for p in rt.profiles() if agent_id in p.delegates]
        if users:
            raise HTTPException(
                409,
                texts.AGENT_IN_USE_BY.format(agents=", ".join(sorted(users)), agent_id=agent_id),
            )
        try:
            trashed = trash_agent(rt.settings.home, agent_id)
        except OSError as exc:
            raise HTTPException(409, str(exc)) from exc
        rt.remove_agent(agent_id)
        if rt.channel is not None:
            rt.channel.use_agents(rt.agents)
    return {"removed": agent_id, "kept_at": str(trashed)}
