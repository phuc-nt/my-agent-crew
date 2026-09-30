"""Scheduled jobs: what is planned, when it last ran, a switch to pause one without
touching its profile, its past runs, and a button to run it now."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from my_agent_crew.scheduler.jobs import JOB_SOURCE
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["jobs"])
RUNS_LIMIT = 20
JOB_FROM_PROFILE = "job comes from agent.yaml; edit the profile instead"


class JobPatch(BaseModel):
    enabled: bool


def _job(rt: Rt, job_id: str):
    try:
        return rt.scheduler.get(job_id)
    except KeyError as exc:
        raise HTTPException(404, "job not found") from exc


@router.get("/jobs")
def list_jobs(rt: Rt) -> list[dict[str, Any]]:
    return rt.scheduler.describe()


@router.patch("/jobs/{job_id:path}/state")
def switch_job(job_id: str, body: JobPatch, rt: Rt) -> dict[str, Any]:
    job = _job(rt, job_id)
    rt.scheduler.set_enabled(job.id, body.enabled)
    return next(j for j in rt.scheduler.describe() if j["id"] == job.id)


@router.get("/jobs/{job_id:path}/runs")
def job_runs(job_id: str, rt: Rt, limit: int = Query(RUNS_LIMIT, ge=1, le=200)) -> list[dict]:
    job = _job(rt, job_id)
    source = JOB_SOURCE + job.id
    return [r.to_dict() for r in rt.store.runs.recent(limit, source=source)]


@router.post("/jobs/{job_id:path}/run", status_code=202)
async def run_now(job_id: str, rt: Rt) -> dict[str, Any]:
    job = _job(rt, job_id)
    task = asyncio.create_task(rt.scheduler.run_job(job.id))
    rt.scheduler.keep(task)
    return {"job_id": job.id, "status": "started"}


def _is_profile_schedule(rt: Rt, agent_id: str, schedule_id: str) -> bool:
    agent = rt.agents.get(agent_id)
    return agent is not None and any(s.id == schedule_id for s in agent.agent.schedules)


@router.delete("/jobs/{job_id:path}", status_code=204)
def delete_job(job_id: str, rt: Rt) -> None:
    """Only a chat-created row can be deleted here; a profile schedule is edited in
    `agent.yaml` and needs a restart to change, so this route refuses to touch it.

    Checked against `rt.agents` directly, not `rt.scheduler.get()`: a row whose agent was
    since removed from the crew has no `Job` the scheduler can build at all (`chat_jobs`
    drops it), and that orphan must still be deletable, not raise a 404 that hides it."""
    agent_id, _, schedule_id = job_id.partition("/")
    if _is_profile_schedule(rt, agent_id, schedule_id):
        raise HTTPException(409, JOB_FROM_PROFILE)
    if not rt.store.created_schedules.remove(schedule_id, agent_id):
        raise HTTPException(404, "job not found")
    rt.store.jobs.clear(job_id)
