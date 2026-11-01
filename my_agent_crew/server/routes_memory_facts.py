"""The facts about the person over HTTP, one at a time: edit by hand, read the versions a
fact went through, retract it (kept in the history) or purge it (gone for good).

A hand edit is the person's own word, so it lands whatever an agent wrote before it; the
version it replaces stays in the history like any other.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew.memory import fact_dates, fact_history, fact_recall, user_store
from my_agent_crew.memory.fact_model import OPERATOR, WEB, Fact, state_on
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["memory"])


class FactBody(BaseModel):
    description: str = ""
    type: str = "reference"
    body: str = ""
    valid_from: str = ""
    valid_until: str = ""


def fact_view(fact: Fact, recalls: dict[str, dict], today: date, directory) -> dict[str, Any]:
    """A fact as the web shows it: the stored fields plus what follows from them today."""
    data = fact.to_dict()
    data["stale"] = fact_dates.is_stale(fact.confirmed or fact.updated, today)
    data["state"] = state_on(fact, today)
    recall = recalls.get(fact.name) or {}
    data["recalls"] = int(recall.get("count", 0))
    data["recalled_at"] = str(recall.get("last", ""))
    data["history_count"] = len(fact_history.versions(directory, fact.name))
    return data


def facts_payload(rt: Rt) -> dict[str, Any]:
    user_dir = rt.settings.user_dir
    directory = user_store.facts_dir(user_dir)
    today = date.today()
    recalls = fact_recall.read(directory)
    return {
        "facts": [fact_view(f, recalls, today, directory) for f in user_store.list_facts(user_dir)],
        "retracted": [v.to_dict() for v in fact_history.retracted(directory)],
    }


def _name(name: str) -> str:
    try:
        return user_store.check_name(name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/memory/user/facts/{name}")
def put_fact(name: str, body: FactBody, rt: Rt) -> dict[str, Any]:
    try:
        fact = user_store.write_fact(
            rt.settings.user_dir,
            name=_name(name),
            description=body.description,
            type=body.type,
            body=body.body,
            written_by=WEB,
            source=WEB,
            basis=OPERATOR,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return fact.to_dict()


@router.get("/memory/user/facts/{name}/history")
def fact_history_route(name: str, rt: Rt) -> dict[str, Any]:
    directory = user_store.facts_dir(rt.settings.user_dir)
    name = _name(name)
    return {"versions": [v.to_dict() for v in reversed(fact_history.versions(directory, name))]}


@router.delete("/memory/user/facts/{name}", status_code=204)
def delete_fact(name: str, rt: Rt, purge: bool = False) -> None:
    """Retract by default; `purge=true` also erases the history and the recall count, and
    works on a fact already retracted."""
    name = _name(name)
    user_dir = rt.settings.user_dir
    remove = user_store.purge_fact if purge else user_store.delete_fact
    if not remove(user_dir, name):
        raise HTTPException(404, "fact not found")
