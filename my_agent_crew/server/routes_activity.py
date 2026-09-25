"""What the agents are doing: recent runs, a live stream of run events, and spend
totals per agent, model and day."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import tzinfo
from typing import Any
from weakref import WeakKeyDictionary

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.clock import local_day
from my_agent_crew.server.deps import Rt
from my_agent_crew.store import Store
from my_agent_crew.store.runs import RunRecord

router = APIRouter(tags=["activity"])
STATS_RUNS = 500
# The last stats answer per store, with the store's change count it was computed at. The
# rail asks again after every finished run and on every page load; between two writes
# the answer cannot differ, so it is not computed twice.
_stats_memo: WeakKeyDictionary[Store, tuple[int, dict[str, Any]]] = WeakKeyDictionary()


@router.get("/activity/runs")
def list_runs(
    rt: Rt,
    limit: int = 50,
    agent_id: str | None = None,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    """Recent runs, narrowed to one agent or to one conversation.

    A conversation's activity includes what it delegated: the work happened on the child's
    own run, and hiding it would leave the parent looking idle while a delegate works."""
    family = conversation_family(rt, conversation_id) if conversation_id else None
    runs = rt.hub.recent(min(max(limit, 1), 500), conversation_ids=family)
    if agent_id:
        runs = [r for r in runs if r.agent_id == agent_id]
    return [r.to_dict() for r in runs]


def conversation_family(rt: Rt, conversation_id: str) -> set[str]:
    """A conversation's id together with those of the conversations it delegated.

    One level deep: a delegate may not delegate again (`depth=1` in `delegate.py`), so
    there is no deeper tree to walk."""
    children = rt.store.delegated_children(conversation_id, DELEGATE_TOOL_NAME)
    return {conversation_id, *(child.id for child in children)}


@router.get("/activity/runs/{run_id}")
def get_run(run_id: str, rt: Rt) -> dict[str, Any]:
    for run in rt.hub.live():
        if run.id == run_id:
            return run.to_dict()
    try:
        return rt.store.runs.get(run_id).to_dict()
    except KeyError as exc:
        raise HTTPException(404, "run not found") from exc


@router.get("/activity/stream")
async def stream(rt: Rt) -> EventSourceResponse:
    async def events() -> AsyncIterator[dict[str, str]]:
        async for payload in rt.hub.subscribe():
            yield {"event": payload["type"], "data": json.dumps(payload, ensure_ascii=False)}

    return EventSourceResponse(events())


def summarize(runs: list[RunRecord], zone: tzinfo | None = None) -> dict[str, Any]:
    """Days are the person's (`zone`), not the UTC the runs are stamped in."""
    by_agent: dict[str, float] = defaultdict(float)
    by_model: dict[str, float] = defaultdict(float)
    by_day: dict[str, float] = defaultdict(float)
    unknown = 0
    calls = 0
    for run in runs:
        by_agent[run.agent_id] += run.spent_usd
        by_day[local_day(run.started_at, zone)] += run.spent_usd
        unknown += run.unknown_cost_calls
        for step in run.steps:
            if step.get("kind") == "model":
                calls += 1
                model = f"{step.get('provider')}:{step.get('model')}"
                by_model[model] += step.get("cost_usd") or 0.0
    return {
        "runs": len(runs),
        "model_calls": calls,
        "spent_usd": round(sum(by_agent.values()), 6),
        "unknown_cost_calls": unknown,
        "by_agent": {k: round(v, 6) for k, v in sorted(by_agent.items())},
        "by_model": {k: round(v, 6) for k, v in sorted(by_model.items())},
        "by_day": {k: round(v, 6) for k, v in sorted(by_day.items())},
    }


@router.get("/stats")
def stats(rt: Rt) -> dict[str, Any]:
    """Run totals for the rail, plus the message-log ledger (`days`, `models`), which is
    the honest number: it counts what providers billed, with tokens, over every run."""
    version = rt.store.changes
    memo = _stats_memo.get(rt.store)
    if memo is not None and memo[0] == version:
        return memo[1]
    data = summarize(rt.hub.recent(STATS_RUNS), rt.settings.zone)
    data["pending_proposals"] = len(rt.store.proposals.list())
    data["days"] = rt.store.usage.by_day(zone=rt.settings.zone)
    data["models"] = rt.store.usage.by_model()
    _stats_memo[rt.store] = (version, data)
    return data
