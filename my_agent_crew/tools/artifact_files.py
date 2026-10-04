"""The two tools that carry a canvas to and from a workspace file, and `artifact_export`
itself. An import adds a version a person can go back from, so it does not ask; an export
writes over a file nothing keeps a version of, so it asks first, like `workspace_write`. An
export writes only where the file would really land inside the workspace and the agent's write
paths, never through a link, and whole or not at all. It writes no canvas, so it is open on
every channel, costs the turn nothing and makes nothing seen."""

from __future__ import annotations

import asyncio
import os
import secrets
import stat
from collections.abc import Sequence
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from my_agent_crew.artifacts.kinds import KINDS
from my_agent_crew.texts import WORKSPACE_ESCAPE, WORKSPACE_IS_DIR, WORKSPACE_WRITE_OUTSIDE
from my_agent_crew.tools.artifact import number_param, schema, text_param
from my_agent_crew.tools.artifact_context import CanvasAgent, int_arg, text_arg
from my_agent_crew.tools.artifact_file_texts import (
    ARTIFACT_EXPORT_DESCRIPTION,
    ARTIFACT_IMPORT_DESCRIPTION,
    EXPORT_DONE,
    EXPORT_FAILED,
    EXPORT_REPLACED,
    EXPORT_TARGET_IS_LINK,
    PARAM_EXPORT_PATH,
    PARAM_EXPORT_VERSION,
    PARAM_IMPORT_ID,
    PARAM_IMPORT_KIND,
    PARAM_IMPORT_PATH,
    PARAM_IMPORT_TITLE,
    PARAM_REPLACE,
    PARAM_SOURCE_URL,
)
from my_agent_crew.tools.artifact_import import run_import
from my_agent_crew.tools.artifact_scope import canvas_errors
from my_agent_crew.tools.artifact_source_ref import check_path, workspace_path
from my_agent_crew.tools.artifact_texts import PARAM_ID, PARAM_LANGUAGE
from my_agent_crew.tools.registry import Tool, ToolError
from my_agent_crew.tools.workspace import resolve_writable

if TYPE_CHECKING:
    from my_agent_crew.store import Store


async def run_export(
    agent: CanvasAgent, root: Path, write_paths: Sequence[str], args: dict[str, Any]
) -> str:
    conv = agent.conversation()
    artifact_id = text_arg(args, "id")
    path = check_path(text_arg(args, "path"))
    number = int_arg(args.get("version"), 0)
    agent.reach(conv, artifact_id)
    canvases = agent.store.artifacts
    with canvas_errors(artifact_id):
        title = canvases.get(artifact_id).title
        doc = canvases.head(artifact_id) if number <= 0 else canvases.version(artifact_id, number)
    target, shown = _target(root, path, write_paths)
    payload = (doc.data or b"") if doc.content is None else doc.content.encode("utf-8")
    try:
        existed = await asyncio.to_thread(_write_whole, target, payload)
    except OSError:  # worded here: the error's own text names the path on this machine
        raise ToolError(EXPORT_FAILED.format(path=shown)) from None
    agent.share(conv, artifact_id)
    done = EXPORT_DONE.format(
        version=doc.version, id=artifact_id, title=title, size=len(payload), path=shown
    )
    return done + (EXPORT_REPLACED if existed else "")


def _target(root: Path, path: str, write_paths: Sequence[str]) -> tuple[Path, str]:
    """Where the export will really land, and that place as the result names it. The path as
    written may pass through a folder linked elsewhere, so the checks `resolve_writable` made
    on it are made again on the folder the file would truly be put in."""
    try:
        target = resolve_writable(root, path, write_paths)
    except RuntimeError:  # "~name" for a user this machine lacks
        raise ToolError(WORKSPACE_ESCAPE) from None
    base = root.resolve()
    real = target.parent.resolve() / target.name
    if not real.is_relative_to(base):
        raise ToolError(WORKSPACE_ESCAPE)
    if write_paths and not any(
        real.is_relative_to((base / held).resolve()) for held in write_paths
    ):
        refusal = WORKSPACE_WRITE_OUTSIDE.format(paths=", ".join(write_paths), path=path)
        raise ToolError(refusal)
    if real.is_symlink():
        raise ToolError(EXPORT_TARGET_IS_LINK.format(path=path))
    if real.is_dir():
        raise ToolError(WORKSPACE_IS_DIR.format(path=path))
    return real, workspace_path(root, target)


def _write_whole(target: Path, payload: bytes) -> bool:
    """Puts `payload` at `target` whole or not at all, and says whether a file was there. It
    is written beside the target and moved into place, so a write that fails half way leaves
    the old file as it was and nothing else behind. A new file gets the mode any written file
    gets; one that replaces another keeps the other's. Moving a file into place needs no leave
    from the one it replaces, so a file marked read-only is refused here, as a plain write
    would be. It blocks: run in a thread."""
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else None
    if mode is not None and not os.access(target, os.W_OK):
        raise PermissionError(target.name)
    temp = target.with_name(f".export-{secrets.token_hex(8)}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o666)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            if mode is not None:
                os.fchmod(out.fileno(), mode)
        os.replace(temp, target)
    except OSError:
        with suppress(OSError):
            temp.unlink()
        raise
    return mode is not None


def build_artifact_file_tools(
    store: Store,
    agent_id: str,
    is_master: bool,
    limit: int,
    root: Path,
    write_paths: Sequence[str],
) -> list[Tool]:
    """`artifact_import` and `artifact_export` for one agent, over its workspace `root`.
    `limit` is its registry's output cap, which the agent the other canvas tools act for
    carries too; `write_paths` holds the export to where the file tools may write."""
    agent = CanvasAgent(store, agent_id, is_master, limit)
    taking = schema(
        ["path"],
        path=text_param(PARAM_IMPORT_PATH),
        id=text_param(PARAM_IMPORT_ID),
        title=text_param(PARAM_IMPORT_TITLE),
        kind={"type": "string", "enum": list(KINDS), "description": PARAM_IMPORT_KIND},
        language=text_param(PARAM_LANGUAGE),
        source_url=text_param(PARAM_SOURCE_URL),
        replace={"type": "boolean", "description": PARAM_REPLACE},
    )
    giving = schema(
        ["id", "path"],
        id=text_param(PARAM_ID),
        path=text_param(PARAM_EXPORT_PATH),
        version=number_param(PARAM_EXPORT_VERSION),
    )
    held = tuple(write_paths)
    return [
        Tool(
            "artifact_import", ARTIFACT_IMPORT_DESCRIPTION, taking, partial(run_import, agent, root)
        ),
        Tool(
            "artifact_export",
            ARTIFACT_EXPORT_DESCRIPTION,
            giving,
            partial(run_export, agent, root, held),
            requires_approval=True,
        ),
    ]
