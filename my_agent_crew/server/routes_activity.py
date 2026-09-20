"""What the agents are doing: recent runs, a live stream of run events, and spend
totals per agent, model and day."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from my_agent_crew.server.deps import Rt
from my_agent_crew.store.runs import RunRecord

router = APIRouter(tags=["activity"])
STATS_RUNS = 500


@router.get("/activity/runs")
def list_runs(rt: Rt, limit: int = 50, agent_id: str | None = None) -> list[dict[str, Any]]:
    runs = rt.hub.recent(min(max(limit, 1), 500))
    if agent_id:
        runs = [r for r in runs if r.agent_id == agent_id]
    return [r.to_dict() for r in runs]


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


def summarize(runs: list[RunRecord]) -> dict[str, Any]:
    by_agent: dict[str, float] = defaultdict(float)
    by_model: dict[str, float] = defaultdict(float)
    by_day: dict[str, float] = defaultdict(float)
    unknown = 0
    calls = 0
    for run in runs:
        by_agent[run.agent_id] += run.spent_usd
        by_day[run.started_at[:10]] += run.spent_usd
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
    data = summarize(rt.hub.recent(STATS_RUNS))
    data["pending_proposals"] = len(rt.store.proposals.list())
    return data
