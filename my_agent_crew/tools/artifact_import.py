"""`artifact_import`: a file already in the workspace becomes a canvas, or the newest version
of one that is there, without its text passing through the model. A turn on a channel with no
canvas, a path that leaves the workspace, or a turn that has written its share is refused
before the file is opened. A file never goes over versions the conversation has not seen
unless `replace` says the person wants that, and even then those versions stay unseen. A file
that changes nothing shares nothing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from my_agent_crew.agent.turn_context import note_canvas_write
from my_agent_crew.artifacts.kinds import KINDS
from my_agent_crew.artifacts.tag import artifact_tag
from my_agent_crew.store.artifact_authors import authors_line
from my_agent_crew.store.artifact_models import IMPORT_NOTE
from my_agent_crew.tools.artifact_context import CanvasAgent, flag_arg, optional_text, text_arg
from my_agent_crew.tools.artifact_edit import unchanged, written
from my_agent_crew.tools.artifact_file_texts import (
    IMPORT_CREATED,
    IMPORT_KEPT_IN_HISTORY,
    IMPORT_KIND_MISMATCH,
    IMPORT_REPLACED,
    IMPORT_SOURCE_RECORDED,
    IMPORT_UNKNOWN_KIND,
    IMPORT_WOULD_OVERWRITE,
    SOURCE_WORKSPACE,
)
from my_agent_crew.tools.artifact_import_lines import default_title, imported_line, source_lines
from my_agent_crew.tools.artifact_scope import (
    NEW_CANVAS,
    canvas_errors,
    check_budget,
    check_channel,
    send_lines,
)
from my_agent_crew.tools.artifact_source import (
    SourceFile,
    code_language,
    infer_kind,
    inside_workspace,
    read_source,
)
from my_agent_crew.tools.artifact_source_ref import (
    check_path,
    relative_ref_count,
    source_for,
    web_url,
    workspace_path,
)
from my_agent_crew.tools.registry import ToolError

if TYPE_CHECKING:
    from my_agent_crew.store.models import Conversation

# The kinds a canvas runs as a page, which so lose the files that sat beside them.
_PAGE_KINDS = ("html", "svg")


@dataclass(frozen=True)
class _Asked:
    """The arguments as checked, before any file is opened. An optional one sent blank counts
    as one left out."""

    path: str
    title: str
    kind: str
    language: str
    url: str
    replace: bool


async def run_import(agent: CanvasAgent, root: Path, args: dict[str, Any]) -> str:
    conv = agent.conversation()
    check_channel(conv)
    path = check_path(text_arg(args, "path"))
    # Before its suffix, its kind or its canvas: a path that leaves is wrong whatever those are.
    inside_workspace(root, path)
    artifact_id, title, kind, url = (
        (optional_text(args, name) or "").strip() for name in ("id", "title", "kind", "source_url")
    )
    if kind and kind not in KINDS:
        raise ToolError(IMPORT_UNKNOWN_KIND.format(kinds=", ".join(KINDS)))
    if url:
        web_url(url)
    language = optional_text(args, "language") or ""
    asked = _Asked(path, title, kind, language, url, flag_arg(args.get("replace")))
    if artifact_id:
        return await _replace(agent, root, conv, artifact_id, asked)
    return await _create(agent, root, conv, asked)


async def _create(agent: CanvasAgent, root: Path, conv: Conversation, asked: _Asked) -> str:
    check_budget(NEW_CANVAS)
    if asked.kind:
        kind, guessed = asked.kind, code_language(asked.path) if asked.kind == "code" else ""
    else:
        kind, guessed = infer_kind(asked.path)
    file, refs = await asyncio.to_thread(_read, root, asked.path, kind)
    relative = workspace_path(root, file.path)
    with canvas_errors():
        summary = agent.store.artifacts.create(
            asked.title or default_title(relative),
            kind,
            agent.agent_id,
            agent.author,
            conv.id,
            content=file.content,
            data=file.data,
            language=asked.language or guessed,
            source=asked.url or source_for(agent.agent_id, root, file.path),
        )
    note_canvas_write(NEW_CANVAS)
    agent.share(conv, summary.id)
    agent.store.artifact_links.mark_seen(conv.id, summary.id, 1)
    done = imported_line(IMPORT_CREATED, relative, summary, file)
    shown = asked.url or SOURCE_WORKSPACE.format(path=relative)
    told = [*source_lines(kind, shown, refs), *send_lines(conv, summary.id)]
    return "\n".join([artifact_tag(summary.id, 1), done, *told])


async def _replace(
    agent: CanvasAgent, root: Path, conv: Conversation, artifact_id: str, asked: _Asked
) -> str:
    canvases = agent.store.artifacts
    # Reach is settled first, so a refusal over its kind never tells of a canvas out of reach.
    agent.reach(conv, artifact_id)
    with canvas_errors(artifact_id):
        kind = canvases.get(artifact_id).kind
    if asked.kind and asked.kind != kind:
        raise ToolError(IMPORT_KIND_MISMATCH.format(id=artifact_id, kind=kind))
    check_budget(artifact_id)
    file, refs = await asyncio.to_thread(_read, root, asked.path, kind)
    # No `await` from here to the write: the newest version is looked up only now, with the
    # file in hand, so a save made while the disk was read is seen and never written over.
    relative = workspace_path(root, file.path)
    source = asked.url or source_for(agent.agent_id, root, file.path)
    shown = asked.url or SOURCE_WORKSPACE.format(path=relative)
    with canvas_errors(artifact_id):
        head, recorded = canvases.head(artifact_id), canvases.get(artifact_id).source
    seen = agent.seen(conv, artifact_id)
    title = asked.title or None
    if (file.content, file.data) == (head.content, head.data):
        # No version, no count against the turn, nothing made seen and nothing shared: only
        # the link, the title and the place the file sits are brought up to date.
        agent.link(conv, artifact_id)
        told = unchanged(agent, artifact_id, head.version, title)
        if source == recorded:
            return told
        with canvas_errors(artifact_id):
            canvases.set_source(artifact_id, source)
        return f"{told}\n{IMPORT_SOURCE_RECORDED.format(source=shown)}"
    over: list[str] = []
    if seen < head.version:
        with canvas_errors(artifact_id):
            unseen = authors_line(canvases.versions(artifact_id), seen, head.version)
        if not asked.replace:
            authors = f" {unseen}" if unseen else ""
            refusal = IMPORT_WOULD_OVERWRITE.format(
                id=artifact_id, head=head.version, authors=authors
            )
            raise ToolError(refusal)
        over = [*([unseen] if unseen else []), IMPORT_KEPT_IN_HISTORY]
    with canvas_errors(artifact_id):
        version = canvases.write(
            artifact_id,
            file.content,
            agent.author,
            conv.id,
            base_version=head.version,
            title=title,
            note=IMPORT_NOTE,
            data=file.data,
            source=source,
        )
        summary = canvases.get(artifact_id)
    written(agent, conv, artifact_id, version.version, moved=seen == head.version)
    done = imported_line(IMPORT_REPLACED, relative, summary, file, replaced=head.version)
    lines = [artifact_tag(artifact_id, version.version), done, *over]
    return "\n".join([*lines, *source_lines(kind, shown, refs)])


def _read(root: Path, path: str, kind: str) -> tuple[SourceFile, int]:
    """The file, and how many files beside it a page points at. It blocks: run in a thread."""
    file = read_source(root, path, kind)
    return file, relative_ref_count(file.content or "") if kind in _PAGE_KINDS else 0
