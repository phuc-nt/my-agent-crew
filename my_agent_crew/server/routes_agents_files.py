"""The persona files an agent reads at the start of every turn, and picking up agents
added to disk outside the web.

Separate from the profile routes because these two do not touch `agent.yaml`: one
writes the markdown beside it, the other only reads what is already there.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew import texts
from my_agent_crew.agent.prompt import system_prompt_for
from my_agent_crew.agent.turn_notes import opening_block
from my_agent_crew.agents.profile import PERSONA_FILES
from my_agent_crew.server.agent_edit_common import check_editable, existing, write_lock
from my_agent_crew.server.agent_install import joined, read_crew
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["agents"])


class FileRequest(BaseModel):
    content: str


def _checked(name: str) -> None:
    if name not in PERSONA_FILES:
        raise HTTPException(
            404, texts.PERSONA_FILE_UNKNOWN.format(name=name, names=", ".join(PERSONA_FILES))
        )


@router.get("/agents/{agent_id}/prompt")
def get_prompt(agent_id: str, rt: Rt) -> dict[str, Any]:
    """The system prompt this agent would be given for a fresh conversation.

    Built by the same function the turn uses, so what the person reads here is what the
    model is told — not a rendering of the profile that happens to look similar. It is
    "as of now": the persona files are re-read on every turn, so a prompt shown for a
    past turn would be a guess. `opening` is what the first message of that conversation
    would be read after: the daily notes, which are no part of the system prompt.
    """
    try:
        deps = rt.deps_for(agent_id)
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc
    text, opening = system_prompt_for(deps), opening_block(deps)
    return {
        "prompt": text,
        "chars": len(text),
        "opening": opening,
        "opening_chars": len(opening),
    }


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
    without a restart, their schedules with them. An agent that already runs is not read
    again here: a file of its edited by hand is read at the next start, or when a key or
    the crew's routes are saved, which builds every running agent from its file again."""
    async with write_lock:
        try:
            added = joined(rt, read_crew(rt))
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc
    return {"added": added}
