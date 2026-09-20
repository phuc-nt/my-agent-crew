"""One agent's own memory over HTTP: `MEMORY.md` and the dated notes beside it.

These are the files the agent re-reads at the start of every turn, so an edit here takes
effect on its next message with no restart and no separate copy.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew import texts
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.memory import agent_store
from my_agent_crew.memory.consolidate import JOB_SOURCE, consolidate_memory
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["memory"])


class MemoryBody(BaseModel):
    memory_md: str


class NoteBody(BaseModel):
    body: str


def _profile(rt: Rt, agent_id: str) -> AgentProfile:
    try:
        return rt.deps_for(agent_id).profile
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc


def _checked_day(day: str) -> str:
    try:
        return agent_store.check_day(day)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/agents/{agent_id}/memory")
def get_agent_memory(agent_id: str, rt: Rt) -> dict[str, Any]:
    profile = _profile(rt, agent_id)
    notes = agent_store.list_notes(profile.memory_dir)
    return {
        "memory_md": agent_store.read_memory_md(profile.memory_file),
        "notes": [n.to_dict() for n in notes],
        "note_count": len(notes),
    }


@router.put("/agents/{agent_id}/memory")
def put_agent_memory(agent_id: str, body: MemoryBody, rt: Rt) -> dict[str, Any]:
    profile = _profile(rt, agent_id)
    agent_store.write_memory_md(profile.memory_file, body.memory_md)
    return get_agent_memory(agent_id, rt)


@router.get("/agents/{agent_id}/memory/notes/{day}")
def get_note(agent_id: str, day: str, rt: Rt) -> dict[str, Any]:
    profile = _profile(rt, agent_id)
    return {"day": _checked_day(day), "body": agent_store.read_note(profile.memory_dir, day)}


@router.put("/agents/{agent_id}/memory/notes/{day}")
def put_note(agent_id: str, day: str, body: NoteBody, rt: Rt) -> dict[str, Any]:
    profile = _profile(rt, agent_id)
    agent_store.write_note(profile.memory_dir, _checked_day(day), body.body)
    return get_note(agent_id, day, rt)


@router.post("/agents/{agent_id}/memory/consolidate", status_code=202)
async def consolidate(agent_id: str, rt: Rt) -> dict[str, Any]:
    """Starts the rewrite and returns at once; the run shows its progress in Activity."""
    _profile(rt, agent_id)
    if agent_id in rt.consolidating:
        raise HTTPException(409, texts.CONSOLIDATE_BUSY)
    deps = rt.deps_for(agent_id)
    rt.consolidating.add(agent_id)

    async def run() -> None:
        try:
            await consolidate_memory(deps, rt.hub)
        finally:
            rt.consolidating.discard(agent_id)

    rt.scheduler.keep(asyncio.create_task(run()))
    return {"agent_id": agent_id, "run_source": JOB_SOURCE}
