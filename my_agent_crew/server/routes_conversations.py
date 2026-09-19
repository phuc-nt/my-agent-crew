from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from my_agent_crew.server.deps import Deps
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT

router = APIRouter(tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = CONVERSATION_TITLE_DEFAULT
    autonomous: bool | None = None
    cost_cap_usd: float | None = Field(default=None, ge=0)
    skills: list[str] = []


class ConversationPatch(BaseModel):
    title: str | None = None
    autonomous: bool | None = None
    cost_cap_usd: float | None = Field(default=None, ge=0)
    skills: list[str] | None = None


@router.get("/conversations")
def list_conversations(deps: Deps) -> list[dict[str, Any]]:
    return [c.to_dict() for c in deps.store.list()]


@router.post("/conversations", status_code=201)
def create_conversation(body: ConversationCreate, deps: Deps) -> dict[str, Any]:
    settings = deps.settings
    conv = deps.store.create(
        title=body.title,
        autonomous=settings.autonomous_default if body.autonomous is None else body.autonomous,
        cost_cap_usd=settings.cost_cap_usd if body.cost_cap_usd is None else body.cost_cap_usd,
        skills=tuple(body.skills),
    )
    return conv.to_dict()


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, deps: Deps) -> dict[str, Any]:
    try:
        conv = deps.store.get(conv_id)
    except KeyError as exc:
        raise HTTPException(404, "conversation not found") from exc
    data = conv.to_dict()
    data["messages"] = [m.to_dict() for m in deps.store.history(conv_id)]
    pending = deps.store.approvals.pending(conv_id)
    data["pending_approval"] = pending.to_dict() if pending else None
    return data


@router.patch("/conversations/{conv_id}")
def patch_conversation(conv_id: str, body: ConversationPatch, deps: Deps) -> dict[str, Any]:
    fields = body.model_dump(exclude_none=True)
    if "skills" in fields:
        fields["skills"] = tuple(fields["skills"])
    try:
        return deps.store.update(conv_id, **fields).to_dict()
    except KeyError as exc:
        raise HTTPException(404, "conversation not found") from exc


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, deps: Deps) -> None:
    try:
        deps.store.delete(conv_id)
    except KeyError as exc:
        raise HTTPException(404, "conversation not found") from exc
