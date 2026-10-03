"""The canvas a conversation has open on the web, with the passage the person selected in it,
which the next turn's note names or quotes (`store/canvas_quote.py`). Opening a canvas shares
it with the conversation, so the agents it delegates to reach it too (`artifact_reach.py`).
A selection is checked the way the note will read it: one the note would drop is refused,
never stored.

`check_focus` and `apply_focus` also serve the chat route, where each message carries the
canvas open in the tab that sent it."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, StrictInt

from my_agent_crew.server.artifact_errors import NOT_FOUND
from my_agent_crew.server.deps import Rt
from my_agent_crew.store.canvas_quote import valid_pick
from my_agent_crew.store.db import Store

router = APIRouter(tags=["artifacts"])
# As long as the longest message the chat takes.
SELECTION_MAX = 20000


class Selection(BaseModel):
    version: StrictInt
    text: str
    line_start: StrictInt
    line_end: StrictInt


class FocusBody(BaseModel):
    artifact_id: str | None  # required; null closes the canvas
    selection: Selection | None = None


def check_focus(store: Store, body: FocusBody) -> bool:
    """Whether `body` opens a canvas that is there, refusing with a 422 a selection the note
    would drop. False for a close, and for a canvas deleted since the tab loaded it."""
    selection = body.selection
    if body.artifact_id is None:
        if selection is not None:
            raise HTTPException(422, "a selection needs the canvas it was made in")
        return False
    try:
        head = store.artifacts.get(body.artifact_id).head_version
    except KeyError:
        return False
    if selection is not None and not _quotable(selection, head):
        raise HTTPException(422, f"the selection does not fit the canvas at version {head}")
    return True


def apply_focus(store: Store, conversation_id: str, body: FocusBody, present: bool) -> None:
    """Opens what `check_focus` let through, shared with the conversation; anything else
    closes what was open. Call it with no `await` since `check_focus`."""
    if not present or body.artifact_id is None:
        store.artifact_links.clear_focus(conversation_id)
        return
    selection = None if body.selection is None else body.selection.model_dump()
    store.artifact_links.link(conversation_id, body.artifact_id, shared=True)
    store.artifact_links.set_focus(conversation_id, body.artifact_id, selection)


@router.get("/conversations/{conv_id}/canvas")
async def get_canvas(conv_id: str, rt: Rt) -> dict[str, Any] | None:
    _check_conversation(rt.store, conv_id)
    return _shown(rt.store, conv_id)


@router.put("/conversations/{conv_id}/canvas")
async def put_canvas(conv_id: str, body: FocusBody, rt: Rt) -> dict[str, Any] | None:
    """What `GET` reads next. Unlike a message, which still goes and closes it, a canvas
    missing here is 404."""
    store = rt.store
    _check_conversation(store, conv_id)
    present = check_focus(store, body)
    if body.artifact_id is not None and not present:
        raise HTTPException(404, NOT_FOUND)
    apply_focus(store, conv_id, body, present)
    return _shown(store, conv_id)


def _quotable(selection: Selection, head: int) -> bool:
    """As the note reads it (`valid_pick`), with its lines in order, no longer than a message
    and made of characters a row can hold: a lone surrogate, which a cut between the two code
    units of a character leaves, would fail the write of the focus once the message is queued."""
    return (
        valid_pick(selection.model_dump(), head)
        and selection.line_end >= selection.line_start
        and len(selection.text) <= SELECTION_MAX
        and _encodable(selection.text)
    )


def _encodable(text: str) -> bool:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _check_conversation(store: Store, conversation_id: str) -> None:
    try:
        store.get(conversation_id)
    except KeyError:
        raise HTTPException(404, "conversation not found") from None


def _shown(store: Store, conversation_id: str) -> dict[str, Any] | None:
    focus = store.artifact_links.focus(conversation_id)
    if focus is None:
        return None
    return {"artifact_id": focus.artifact_id, "selection": focus.selection}
