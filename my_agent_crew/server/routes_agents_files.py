"""The persona files an agent reads at the start of every turn, and picking up agents
added to disk outside the web.

Separate from the profile routes because these two do not touch `agent.yaml`: one
writes the markdown beside it, the other only reads what is already there.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ruamel.yaml import YAMLError

from my_agent_crew import texts
from my_agent_crew.agents import load_profiles
from my_agent_crew.agents.profile import PERSONA_FILES
from my_agent_crew.server.agent_edit_common import check_editable, existing, write_lock
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.runtime_build import check_delegates

router = APIRouter(tags=["agents"])


class FileRequest(BaseModel):
    content: str


def _checked(name: str) -> None:
    if name not in PERSONA_FILES:
        raise HTTPException(
            404, texts.PERSONA_FILE_UNKNOWN.format(name=name, names=", ".join(PERSONA_FILES))
        )


@router.get("/agents/{agent_id}/files/{name}")
def get_persona_file(agent_id: str, name: str, rt: Rt) -> dict[str, Any]:
    """Read one persona file. A name the agent may have but has not written yet reads as
    empty rather than as an error: that is the state every new agent starts in, and an
    editor that refuses to open it would leave no way to write the first line."""
    _checked(name)
    profile = existing(rt, agent_id)
    target = profile.dir / name
    content = target.read_text(encoding="utf-8") if target.is_file() else ""
    return {"name": name, "content": content, "chars": len(content)}


@router.put("/agents/{agent_id}/files/{name}")
async def put_persona_file(agent_id: str, name: str, body: FileRequest, rt: Rt) -> dict[str, Any]:
    """Only the persona files, by name. The path never comes from the request, so there
    is nothing to escape out of."""
    _checked(name)
    async with write_lock:
        profile = existing(rt, agent_id)
        check_editable(rt, profile)
        target = profile.dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.content, encoding="utf-8")
    return {"name": name, "chars": len(body.content)}


@router.post("/agents/reload")
async def reload_agents(rt: Rt) -> dict[str, Any]:
    """Pick up agents added on disk outside the web (a kit installed, a folder copied in)
    without a restart."""
    async with write_lock:
        # Any file under the home can be the broken one, including a folder copied in by
        # hand, so this says which rather than failing as a traceback.
        try:
            profiles = load_profiles(rt.settings)
            check_delegates(profiles)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except YAMLError as exc:
            raise HTTPException(422, texts.MANIFEST_BROKEN.format(error=str(exc))) from exc
        try:
            added = rt.add_agents(profiles)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
    return {"added": added}
