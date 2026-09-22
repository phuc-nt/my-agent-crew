"""What the crew knows about the person, over HTTP: USER.md, the facts, search across
every scope, and the proposals a scheduled job left for review.

Everything the agent sees in its prompt is editable here, so the person is never in the
position of arguing with a memory they cannot reach.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew.memory import user_store
from my_agent_crew.memory.proposals_apply import apply_proposal
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.memory_search import search_all
from my_agent_crew.store.memory_proposals import PENDING

router = APIRouter(tags=["memory"])

WEB = "web"
ALL = "all"


class UserMdBody(BaseModel):
    user_md: str


class FactBody(BaseModel):
    description: str = ""
    type: str = "reference"
    body: str = ""


class DecisionBody(BaseModel):
    approve: bool


@router.get("/memory/user")
def get_user_memory(rt: Rt) -> dict[str, Any]:
    user_dir = rt.settings.user_dir
    return {
        "user_md": user_store.read_user_md(user_dir),
        "facts": [f.to_dict() for f in user_store.list_facts(user_dir)],
        "index_md": user_store.read_index(user_dir),
    }


@router.put("/memory/user")
def put_user_md(body: UserMdBody, rt: Rt) -> dict[str, Any]:
    user_store.write_user_md(rt.settings.user_dir, body.user_md)
    return get_user_memory(rt)


@router.put("/memory/user/facts/{name}")
def put_fact(name: str, body: FactBody, rt: Rt) -> dict[str, Any]:
    try:
        user_store.check_name(name)
        user_store.check_type(body.type)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    fact = user_store.write_fact(
        rt.settings.user_dir,
        name=name,
        description=body.description,
        type=body.type,
        body=body.body,
        written_by=WEB,
        source=WEB,
    )
    return fact.to_dict()


@router.delete("/memory/user/facts/{name}", status_code=204)
def delete_fact(name: str, rt: Rt) -> None:
    try:
        user_store.check_name(name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not user_store.delete_fact(rt.settings.user_dir, name):
        raise HTTPException(404, "fact not found")


@router.get("/memory/search")
def search(rt: Rt, q: str = "", agent_id: str | None = None) -> dict[str, Any]:
    if agent_id is not None and agent_id not in rt.agents:
        raise HTTPException(404, "agent not found")
    return {"hits": [hit.to_dict() for hit in search_all(rt, q, agent_id)]}


@router.get("/memory/proposals")
def list_proposals(rt: Rt, status: str = PENDING) -> dict[str, Any]:
    """`status=all` includes the ones already decided, which the panel shows as history."""
    wanted = None if status == ALL else status
    return {"proposals": [p.to_dict() for p in rt.store.proposals.list(status=wanted)]}


@router.post("/memory/proposals/{proposal_id}")
def decide_proposal(proposal_id: str, body: DecisionBody, rt: Rt) -> dict[str, Any]:
    memory_files = {agent_id: d.profile.memory_file for agent_id, d in rt.agents.items()}
    memory_dirs = {agent_id: d.profile.memory_dir for agent_id, d in rt.agents.items()}
    try:
        proposal = apply_proposal(
            rt.store,
            proposal_id,
            approve=body.approve,
            user_dir=rt.settings.user_dir,
            memory_files=memory_files,
            memory_dirs=memory_dirs,
        )
    except KeyError as exc:
        raise HTTPException(_missing_or_decided(rt, proposal_id), "proposal not decidable") from exc
    return proposal.to_dict()


def _missing_or_decided(rt: Rt, proposal_id: str) -> int:
    """Deciding twice is a conflict, not a missing row: the UI should say so, not 404."""
    try:
        rt.store.proposals.get(proposal_id)
    except KeyError:
        return 404
    return 409
