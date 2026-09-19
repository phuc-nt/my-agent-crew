"""Scheduled jobs: what is planned, when it last ran, and a button to run one now."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs(rt: Rt) -> list[dict[str, Any]]:
    return rt.scheduler.describe()


@router.post("/jobs/{job_id:path}/run", status_code=202)
async def run_now(job_id: str, rt: Rt) -> dict[str, Any]:
    try:
        job = rt.scheduler.get(job_id)
    except KeyError as exc:
        raise HTTPException(404, "job not found") from exc
    task = asyncio.create_task(rt.scheduler.run_job(job.id))
    rt.scheduler.keep(task)
    return {"job_id": job.id, "status": "started"}
