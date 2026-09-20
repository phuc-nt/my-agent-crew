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
    runs = rt.store.runs.recent(limit, source_prefix=source)
    return [r.to_dict() for r in runs if r.source == source]


@router.post("/jobs/{job_id:path}/run", status_code=202)
async def run_now(job_id: str, rt: Rt) -> dict[str, Any]:
    job = _job(rt, job_id)
    task = asyncio.create_task(rt.scheduler.run_job(job.id))
    rt.scheduler.keep(task)
    return {"job_id": job.id, "status": "started"}
