"""Agents and the files they produce. `/files` serves anything inside an agent's
workspace (charts the model wrote, reports) and nothing outside it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from my_agent_crew import texts
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["agents"])


def _inside_workspace(workspace: Path, path: str) -> Path:
    root = workspace.resolve()
    candidate = Path(path).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(403, texts.FILE_OUTSIDE_WORKSPACE)
    return resolved


@router.get("/agents")
def list_agents(rt: Rt) -> list[dict[str, Any]]:
    out = []
    for deps in rt.agents.values():
        data = deps.agent.to_dict()
        data["tools"] = deps.tools.names()
        data["skills"] = [sk.name for sk in deps.skills]
        out.append(data)
    return out


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, rt: Rt) -> dict[str, Any]:
    try:
        deps = rt.deps_for(agent_id)
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc
    data = deps.agent.to_dict()
    data["tools"] = deps.tools.describe()
    data["skills"] = [sk.to_dict() for sk in deps.skills]
    return data


@router.get("/agents/{agent_id}/files")
def get_file(agent_id: str, path: str, rt: Rt) -> FileResponse:
    try:
        deps = rt.deps_for(agent_id)
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc
    resolved = _inside_workspace(deps.agent.workspace, path)
    if not resolved.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(resolved)
