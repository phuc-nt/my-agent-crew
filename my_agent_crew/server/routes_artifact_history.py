"""A canvas's history over REST: its versions, one version whole, a restore that writes an old
version as the person's newest, and the raw text. The raw text always goes out as plain text,
whatever the canvas's kind, so a page an agent wrote never runs as one of the app's
(`untrusted_content.py`). A version a later save folded away is 404 with the newest number,
so the web can show what is there instead."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field, StrictInt

from my_agent_crew.artifacts.filenames import filename_for
from my_agent_crew.server.artifact_errors import artifact_errors
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.untrusted_content import untrusted_text
from my_agent_crew.store.artifact_models import USER

router = APIRouter(tags=["artifacts"])


class RestoreBody(BaseModel):
    version: StrictInt = Field(ge=1)


@router.get("/artifacts/{artifact_id}/versions")
async def list_versions(artifact_id: str, rt: Rt) -> list[dict[str, Any]]:
    """Newest first, without the text."""
    with artifact_errors(rt.store.artifacts, artifact_id):
        versions = rt.store.artifacts.versions(artifact_id)
    return [version.meta() for version in reversed(versions)]


@router.get("/artifacts/{artifact_id}/versions/{version}")
async def get_version(artifact_id: str, version: int, rt: Rt) -> dict[str, Any]:
    with artifact_errors(rt.store.artifacts, artifact_id):
        found = rt.store.artifacts.version(artifact_id, version)
    return {**found.meta(), "content": found.content}


@router.post("/artifacts/{artifact_id}/restore")
async def restore_version(artifact_id: str, body: RestoreBody, rt: Rt) -> dict[str, Any]:
    """A new version with the old one's text, noted as its restore; the versions between
    stay."""
    with artifact_errors(rt.store.artifacts, artifact_id):
        restored = rt.store.artifacts.restore(artifact_id, body.version, USER, "")
    return restored.meta()


@router.get("/artifacts/{artifact_id}/raw")
async def raw_text(
    artifact_id: str,
    rt: Rt,
    version: int | None = Query(None, ge=1),
    download: bool = False,
) -> Response:
    """The newest version's text, or `version`'s. `download` saves it under the title with
    the extension of its kind instead of showing it."""
    artifacts = rt.store.artifacts
    with artifact_errors(artifacts, artifact_id):
        summary = artifacts.get(artifact_id)
        if version is None:
            found = artifacts.head(artifact_id)
        else:
            found = artifacts.version(artifact_id, version)
    name = filename_for(summary.title, summary.kind, summary.language)
    return untrusted_text(found.content or "", name, download=download)
