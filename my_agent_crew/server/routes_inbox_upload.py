"""A file the person adds to a message in the web box: a photo pasted or picked, a PDF.

It lands in the agent's inbox exactly as a Telegram attachment does (`inbox_files`), and
the answer carries the line the message then leads with, so the web writes it the way the
channel does and the thread shows it as a thumbnail either way. The body is the file's
bytes as they are, not a form: one file per request, named in the query."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from my_agent_crew import texts
from my_agent_crew.inbox_files import INBOX_DIR, free_path, inbox_file
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["agents"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("/agents/{agent_id}/inbox", status_code=201)
async def upload(agent_id: str, name: str, request: Request, rt: Rt) -> dict[str, str]:
    """`path` is where the file was saved, `line` the words that name it in a message."""
    try:
        workspace = rt.deps_for(agent_id).agent.workspace
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc
    too_large = HTTPException(413, texts.UPLOAD_TOO_LARGE.format(limit=MAX_UPLOAD_BYTES >> 20))
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise too_large
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_UPLOAD_BYTES:
            raise too_large
    if not body:
        raise HTTPException(422, texts.UPLOAD_EMPTY)
    target = inbox_file(workspace / INBOX_DIR, name, "file", datetime.now())
    path = await asyncio.to_thread(_save, target, bytes(body))
    return {"path": str(path), "line": texts.TELEGRAM_ATTACHMENT_LINE.format(path=path)}


def _save(target: Path, data: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    path = free_path(target)
    path.write_bytes(data)
    return path
