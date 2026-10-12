"""What an agent's scripts have kept (`store`, `load`), for a person to look at and to
clear out.

A value is written by a script that ended well and by nothing else
(`script/store_session.py`), so no route here writes one. What is kept can be wrong for good
all the same: a list of what was already told, holding what never was, keeps it from ever
being told. So a person may read a value whole and forget it, one key or all a namespace
holds.

Each namespace is shown with its size as the limit on it counts, keys and values together,
and with whose runs keep there (`_described`); each value with the beginning of its JSON
text, since a value may be as long as a short book.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import groupby
from typing import Any

from fastapi import APIRouter, HTTPException

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.script.limits import MAX_STORE_TOTAL_CHARS
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.db import Store
from my_agent_crew.store.script_store import CONVERSATION, JOB, KeptValue, held_chars

router = APIRouter(tags=["agents"])
# How much of a value's JSON text is shown. The whole length is told beside it.
PREVIEW_CHARS = 200
# What a namespace is told as, by how its name begins: whose runs keep there.
KINDS = {JOB: "job", CONVERSATION: "conv"}
OTHER = "other"


def _agent(rt: Runtime, agent_id: str) -> AgentDeps:
    try:
        return rt.deps_for(agent_id)
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc


def _schedules(rt: Runtime, agent_id: str) -> dict[str, str]:
    """The agent's schedules by id, with what each is called: the ones the jobs page lists
    for it, those a chat made among them."""
    return {
        job.schedule.id: job.schedule.name
        for job in rt.scheduler.jobs()
        if job.agent_id == agent_id
    }


def _described(namespace: str, schedules: Mapping[str, str], store: Store) -> dict[str, Any]:
    """Whose runs keep in a namespace, what that schedule or conversation is called, and
    whether it is gone: what it left behind is read by no script again. A namespace that is
    neither's is told by its name, and has nothing to be left behind by."""
    prefix = next((prefix for prefix in KINDS if namespace.startswith(prefix)), None)
    if prefix is None:
        return {"kind": OTHER, "ref": namespace, "title": None, "orphan": False}
    ref = namespace[len(prefix) :]
    if prefix == JOB:
        title, orphan = schedules.get(ref), ref not in schedules
    else:
        try:
            title, orphan = store.get(ref).title, False
        except KeyError:
            title, orphan = None, True
    # A name of nothing but space says nothing: the id beside it is what there is to show.
    named = title if title and title.strip() else None
    return {"kind": KINDS[prefix], "ref": ref, "title": named, "orphan": orphan}


def _entry(kept: KeptValue) -> dict[str, Any]:
    cut = len(kept.text) > PREVIEW_CHARS
    return {
        "key": kept.key,
        "preview": kept.text[:PREVIEW_CHARS] + "…" if cut else kept.text,
        "chars": len(kept.text),
        "updated_at": kept.updated_at,
    }


@router.get("/agents/{agent_id}/script-store")
def get_script_store(agent_id: str, rt: Rt) -> dict[str, Any]:
    deps = _agent(rt, agent_id)
    schedules = _schedules(rt, deps.agent.id)
    kept = deps.store.script_store.kept_by(deps.agent.id)
    namespaces = []
    for namespace, rows in groupby(kept, key=lambda row: row.namespace):
        entries = list(rows)
        namespaces.append(
            {
                "namespace": namespace,
                **_described(namespace, schedules, deps.store),
                "chars": held_chars({row.key: row.text for row in entries}),
                "entries": [_entry(row) for row in entries],
            }
        )
    # The most each namespace may hold, which the size of each is measured against.
    return {"limit_chars": MAX_STORE_TOTAL_CHARS, "namespaces": namespaces}


@router.get("/agents/{agent_id}/script-store/value")
def get_kept_value(agent_id: str, rt: Rt, namespace: str, key: str) -> dict[str, Any]:
    """One value whole, as the JSON text that is kept."""
    deps = _agent(rt, agent_id)
    kept = deps.store.script_store.value(deps.agent.id, namespace, key)
    if kept is None:
        raise HTTPException(404, "value not found")
    return {
        "namespace": kept.namespace,
        "key": kept.key,
        "text": kept.text,
        "chars": len(kept.text),
        "updated_at": kept.updated_at,
    }


@router.delete("/agents/{agent_id}/script-store")
def forget_kept(agent_id: str, rt: Rt, namespace: str, key: str | None = None) -> dict[str, int]:
    """Forgets one key, or all a namespace holds when no key is named, and says how many
    values went: none is no mistake, since what was to be gone is. A namespace must be
    named: nothing here forgets all an agent kept at once."""
    deps = _agent(rt, agent_id)
    return {"deleted": deps.store.script_store.forget(deps.agent.id, namespace, key)}
