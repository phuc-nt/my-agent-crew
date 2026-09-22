"""Agents and the files they produce. `/files` serves anything inside an agent's
workspace (charts the model wrote, reports) and nothing outside it. `/agents/install`
copies a bundled template into the home and brings it into the running crew."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from my_agent_crew import texts
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import DEFAULT_AGENT_ID, load_profiles
from my_agent_crew.agents.roster import delegate_targets
from my_agent_crew.agents.templates_cli import add_template
from my_agent_crew.server.agent_edit_common import manifest_path
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import check_delegates
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace import resolve_inside

router = APIRouter(tags=["agents"])


class InstallRequest(BaseModel):
    template: str
    agent_id: str = ""
    workspace: str = ""
    force: bool = False


def _inside_workspace(workspace: Path, path: str) -> Path:
    """Same containment rule as the workspace tools, so what the model can read, the UI can show."""
    try:
        return resolve_inside(workspace, path)
    except ToolError as exc:
        raise HTTPException(403, texts.FILE_OUTSIDE_WORKSPACE) from exc


def _describe(rt: Runtime, deps: AgentDeps) -> dict[str, Any]:
    """`delegates` is what the agent can actually reach, not only what its file lists:
    the master names nobody and reaches everyone."""
    data = deps.agent.to_dict()
    data["delegates"] = list(delegate_targets(deps.agent, {p.id: p for p in rt.profiles()}))
    # Whether an edit would be accepted, so a UI can say so before the person fills in a
    # form the write route is going to refuse. It answers the same question
    # `check_editable` does, from the same fact: a kit agent has no manifest to patch.
    agent_id = deps.agent.id
    data["editable"] = agent_id == DEFAULT_AGENT_ID or manifest_path(rt, agent_id).is_file()
    return data


@router.get("/agents")
def list_agents(rt: Rt) -> list[dict[str, Any]]:
    out = []
    for deps in rt.agents.values():
        data = _describe(rt, deps)
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
    data = _describe(rt, deps)
    data["tools"] = deps.tools.describe()
    data["skills"] = [sk.to_dict() for sk in deps.skills]
    return data


@router.post("/agents/install", status_code=201)
def install_agent(body: InstallRequest, rt: Rt) -> dict[str, Any]:
    """Writes the template (and the peers it names) into the home, then loads the new
    profiles into the running crew so the master can delegate to them at once. Schedules
    only start at boot, so an agent that has any reports `needs_restart`."""
    workspace = Path(body.workspace) if body.workspace else None
    try:
        agent_dir, peers = add_template(
            body.template, rt.settings.home, body.agent_id, body.force, workspace=workspace
        )
    except KeyError as exc:
        raise HTTPException(404, texts.TEMPLATE_UNKNOWN.format(template=body.template)) from exc
    except FileExistsError as exc:
        taken = Path(str(exc.args[0])).name
        raise HTTPException(409, texts.AGENT_EXISTS.format(agent_id=taken)) from exc
    installed = [agent_dir.name, *peers]
    profiles = load_profiles(rt.settings)
    check_delegates(profiles)
    try:
        added = rt.add_agents(profiles)
    except RuntimeError:
        added = []
    live = [agent_id for agent_id in installed if agent_id in added]
    needs_restart = any(p.id in installed and p.schedules for p in profiles) or set(
        installed
    ) - set(live)
    return {"installed": installed, "live": live, "needs_restart": bool(needs_restart)}


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
