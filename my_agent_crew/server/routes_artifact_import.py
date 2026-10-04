"""Reading a canvas's workspace file again, for the person who edits that file outside the
app. The canvas says which file: the source its import recorded, in the workspace of the agent
that imported it. The request names no path and no conversation, so it can aim the read
nowhere, and it links nothing and makes nothing seen. The file becomes the person's newest
version unless something was saved since the version the panel loaded; a file that holds what
the newest version holds adds none."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StrictInt

from my_agent_crew.server.artifact_errors import artifact_errors
from my_agent_crew.server.deps import Rt
from my_agent_crew.store.artifact_models import IMPORT_NOTE, USER
from my_agent_crew.texts import FILE_OUTSIDE_WORKSPACE
from my_agent_crew.texts_canvas import REIMPORT_AGENT_GONE, REIMPORT_NO_SOURCE
from my_agent_crew.tools.artifact_source import SourceError, read_source
from my_agent_crew.tools.artifact_source_ref import parse_source

router = APIRouter(tags=["artifacts"])


class ReimportBody(BaseModel):
    # The version the panel loaded; a file never goes over one saved since.
    base_version: StrictInt = Field(ge=1)


@router.post("/artifacts/{artifact_id}/reimport")
async def reimport(artifact_id: str, body: ReimportBody, rt: Rt) -> dict[str, Any]:
    """`changed` says whether the file became a version; `artifact` is the canvas as it is
    now, without its text."""
    canvases = rt.store.artifacts
    with artifact_errors(canvases, artifact_id):
        summary = canvases.get(artifact_id)
    named = parse_source(summary.source)
    if named is None:
        raise HTTPException(422, REIMPORT_NO_SOURCE)
    agent_id, path = named
    try:
        workspace = rt.deps_for(agent_id).agent.workspace
    except KeyError:
        raise HTTPException(410, REIMPORT_AGENT_GONE) from None
    try:
        file = await asyncio.to_thread(read_source, workspace, path, summary.kind)
    except SourceError as exc:
        raise _refusal(exc) from None
    # No `await` from here to the write: the newest version is looked up only now, with the
    # file in hand, so a save made while the disk was read is what the file is compared with.
    with artifact_errors(canvases, artifact_id):
        head = canvases.head(artifact_id)
        changed = (file.content, file.data) != (head.content, head.data)
        if changed:
            canvases.write(
                artifact_id,
                file.content,
                USER,
                "",
                base_version=body.base_version,
                note=IMPORT_NOTE,
                data=file.data,
            )
        return {"changed": changed, "artifact": canvases.get(artifact_id).to_dict()}


def _refusal(error: SourceError) -> HTTPException:
    """A file that is gone is 410, not 404: the canvas is there, and its source is what left.
    A path outside the workspace is worded for a person, not with the advice an agent gets.
    Every other refusal goes out as the sentence an agent's import would get."""
    if error.status == 404:
        return HTTPException(410, str(error))
    if error.status == 403:
        return HTTPException(403, FILE_OUTSIDE_WORKSPACE)
    return HTTPException(error.status, str(error))
