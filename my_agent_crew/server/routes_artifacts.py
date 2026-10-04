"""Canvases over REST, as the web uses them: list, create, read, save, rename, delete, and the
room they take together. Every write is the person's, from no conversation in particular: no
body names an author or a conversation for it, so no request can pass a write off as an agent's.
The store decides every limit (`artifacts/kinds.py`) and `artifact_errors` turns each refusal
into its status code.

Every route is `async`: it writes the store, and so announces the change, on the event loop
the activity watchers wait on (`activity/watchers.py`)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, StrictInt

from my_agent_crew.artifacts.kinds import STORAGE_CAP
from my_agent_crew.server.artifact_errors import artifact_errors
from my_agent_crew.server.deps import Rt
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store

router = APIRouter(tags=["artifacts"])
LIST_LIMIT = 50


class CreateBody(BaseModel):
    title: str
    # Written out by hand so the schema lists them; a test holds it to `CREATABLE_KINDS`. An
    # image only comes in by import, and anything else is refused with a 422.
    kind: Literal["markdown", "code", "html", "svg", "mermaid"]
    content: str = ""
    # Made in this conversation: shared with it and open there.
    conversation_id: str | None = None


class SaveBody(BaseModel):
    content: str
    # The version the editor loaded; a save on any other is refused, never written over.
    base_version: StrictInt = Field(ge=1)


class RenameBody(BaseModel):
    title: str


def detail(store: Store, artifact_id: str) -> dict[str, Any]:
    """The summary with the newest version's text. Its number, author and text come from the
    one read of that version, so a write landing between the two reads cannot pair one
    version's number with another's text."""
    summary = store.artifacts.get(artifact_id)
    head = store.artifacts.head(artifact_id)
    return {
        **summary.to_dict(),
        "head_version": head.version,
        "head_author": head.author,
        "content": head.content,
        "conversation_ids": store.artifact_links.conversations_for(artifact_id),
    }


@router.get("/artifacts")
async def list_artifacts(
    rt: Rt,
    conversation_id: str | None = None,
    q: str | None = None,
    limit: int = Query(LIST_LIMIT, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Most recently changed first. By conversation: only the canvases linked to it."""
    found = rt.store.artifacts.list(conversation_id, query=q, limit=limit)
    return [summary.to_dict() for summary in found]


@router.post("/artifacts", status_code=201)
async def create_artifact(body: CreateBody, rt: Rt) -> dict[str, Any]:
    """The conversation is checked first, so a missing one makes nothing; then the canvas is
    made, linked and opened there with no `await` in between."""
    store, conv_id = rt.store, body.conversation_id
    if conv_id is not None:
        try:
            store.get(conv_id)
        except KeyError:
            raise HTTPException(404, "conversation not found") from None
    with artifact_errors(store.artifacts):
        made = store.artifacts.create(body.title, body.kind, "", USER, "", body.content)
    if conv_id is not None:
        store.artifact_links.link(conv_id, made.id, shared=True)
        store.artifact_links.set_focus(conv_id, made.id, None)
    with artifact_errors(store.artifacts, made.id):
        return detail(store, made.id)


@router.get("/artifacts/usage")
async def artifact_usage(rt: Rt) -> dict[str, Any]:
    """Every canvas there is, past what one list returns, with the bytes each keeps across all
    its versions and the ceiling they fit under together. Declared ahead of
    `/artifacts/{artifact_id}`, which would otherwise read "usage" as the id of a canvas."""
    sizes = rt.store.artifacts.sizes()
    return {
        "count": len(sizes),
        "bytes": sum(sizes.values()),
        "cap": STORAGE_CAP,
        "by_artifact": sizes,
    }


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str, rt: Rt) -> dict[str, Any]:
    with artifact_errors(rt.store.artifacts, artifact_id):
        return detail(rt.store, artifact_id)


@router.put("/artifacts/{artifact_id}")
async def save_artifact(artifact_id: str, body: SaveBody, rt: Rt) -> dict[str, Any]:
    """The new version's metadata: its `version` is the next save's `base_version`, whether
    this save folded into the burst before it or not."""
    artifacts = rt.store.artifacts
    with artifact_errors(artifacts, artifact_id):
        written = artifacts.write(
            artifact_id, body.content, USER, "", base_version=body.base_version
        )
    return written.meta()


@router.patch("/artifacts/{artifact_id}")
async def rename_artifact(artifact_id: str, body: RenameBody, rt: Rt) -> dict[str, Any]:
    """A new title only; no new version."""
    with artifact_errors(rt.store.artifacts, artifact_id):
        return rt.store.artifacts.rename(artifact_id, body.title).to_dict()


@router.delete("/artifacts/{artifact_id}", status_code=204)
async def delete_artifact(artifact_id: str, rt: Rt) -> None:
    """With every version, link and open panel of it; the conversations stay."""
    with artifact_errors(rt.store.artifacts, artifact_id):
        rt.store.artifacts.delete(artifact_id)
