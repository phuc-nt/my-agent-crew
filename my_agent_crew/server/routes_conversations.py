from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.tool_gate import ask_reason_text
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.memory.session_summary import summarize_conversation
from my_agent_crew.server.deps import ConvDeps, Rt
from my_agent_crew.store.runs import AWAITING, FAILED
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT
from my_agent_crew.tools.output_spill import remove_conversation

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
    return conversation_detail(deps, conv_id)


def conversation_detail(deps: AgentDeps, conv_id: str) -> dict[str, Any]:
    """The conversation as it is stored now: its messages, the request it waits on and what
    is queued behind its turn. A tab that joins a running turn is sent the same thing."""
    conv = deps.store.get(conv_id)
    data = conv.to_dict()
    data["messages"] = [m.to_dict() for m in deps.store.history(conv_id)]
    pending = deps.store.approvals.pending(conv_id)
    data["pending_approval"] = None
    if pending:
        # Why an ask pattern stopped the call is not stored: it is worked out again from the
        # call, as it was for the live event, so a request read later still says it.
        reason = ask_reason_text(deps, pending.tool_name, pending.arguments)
        data["pending_approval"] = {**pending.to_dict(), "reason": reason}
    # Read, not taken: what waits for the running turn stays queued after a reload shows it.
    data["queued"] = [item.to_dict() for item in deps.store.queue.peek_all(conv_id)]
    return data


@router.patch("/conversations/{conv_id}")
def patch_conversation(conv_id: str, body: ConversationPatch, deps: ConvDeps) -> dict[str, Any]:
    fields = body.model_dump(exclude_none=True)
    for key in ("skills", "auto_approve"):
        if key in fields:
            fields[key] = tuple(fields[key])
    return deps.store.update(conv_id, **fields).to_dict()


@router.delete("/conversations/{conv_id}", status_code=204)
async def delete_conversation(conv_id: str, deps: ConvDeps, rt: Rt) -> None:
    deps.store.delete(conv_id)
    # After the store: an unknown id never reaches here, and a failed delete keeps its files
    # and its turn.
    remove_conversation(deps.settings.home, conv_id)
    # The turn the server reads for it ends with it: nothing on the web can stop it after.
    rt.drain.cancel(conv_id)
    rt.inbound.host.cancel(conv_id)
    # Its pending requests went with it, so a run paused on one can never be continued.
    for run in rt.hub.live():
        if run.conversation_id == conv_id and run.status == AWAITING:
            rt.hub.finish(run, status=FAILED, summary="interrupted")
