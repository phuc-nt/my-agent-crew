from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.memory.session_summary import summarize_conversation
from my_agent_crew.server.deps import ConvDeps, Rt
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT

router = APIRouter(tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = CONVERSATION_TITLE_DEFAULT
    agent_id: str = DEFAULT_AGENT_ID
    autonomous: bool | None = None
    cost_cap_usd: float | None = Field(default=None, ge=0)
    skills: list[str] = []


class ConversationPatch(BaseModel):
    title: str | None = None
    autonomous: bool | None = None
    cost_cap_usd: float | None = Field(default=None, ge=0)
    skills: list[str] | None = None
    # Tools that run without asking in this conversation; an empty list asks again.
    auto_approve: list[str] | None = None


@router.get("/conversations")
def list_conversations(rt: Rt, agent_id: str | None = None) -> list[dict[str, Any]]:
    return [c.to_dict() for c in rt.store.list(agent_id)]


@router.post("/conversations", status_code=201)
async def create_conversation(body: ConversationCreate, rt: Rt) -> dict[str, Any]:
    try:
        deps = rt.deps_for(body.agent_id)
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc
    settings = deps.settings
    previous = deps.store.latest_for_channel(body.agent_id, "")
    conv = deps.store.create(
        title=body.title,
        autonomous=settings.autonomous_default if body.autonomous is None else body.autonomous,
        cost_cap_usd=settings.cost_cap_usd if body.cost_cap_usd is None else body.cost_cap_usd,
        skills=tuple(body.skills),
        agent_id=body.agent_id,
    )
    if previous is not None:
        rt.summarize_replaced(deps, previous.id)
    return conv.to_dict()


@router.post("/conversations/{conv_id}/summary", status_code=202)
async def resummarize_conversation(conv_id: str, deps: ConvDeps) -> dict[str, Any]:
    deps.store.get(conv_id)
    summary = await summarize_conversation(deps, conv_id, force=True)
    return {"id": conv_id, "summary": summary}


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, deps: ConvDeps) -> dict[str, Any]:
    conv = deps.store.get(conv_id)
    data = conv.to_dict()
    data["messages"] = [m.to_dict() for m in deps.store.history(conv_id)]
    pending = deps.store.approvals.pending(conv_id)
    data["pending_approval"] = pending.to_dict() if pending else None
    return data


@router.patch("/conversations/{conv_id}")
def patch_conversation(conv_id: str, body: ConversationPatch, deps: ConvDeps) -> dict[str, Any]:
    fields = body.model_dump(exclude_none=True)
    for key in ("skills", "auto_approve"):
        if key in fields:
            fields[key] = tuple(fields[key])
    return deps.store.update(conv_id, **fields).to_dict()


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, deps: ConvDeps) -> None:
    deps.store.delete(conv_id)
