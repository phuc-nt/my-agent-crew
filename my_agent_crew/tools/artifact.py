"""The canvas tools an agent is given: creating a canvas and listing those it reaches here,
built with reading (`artifact_read`) and changing (`artifact_edit`) one. Each acts for one
agent in the conversation the turn belongs to. None asks for approval: a canvas keeps every
version, so nothing an agent writes there is lost to the person, and only a turn from the web
chat, where the person sees the canvas open beside the reply, may write at all."""

from __future__ import annotations

from datetime import tzinfo
from functools import partial
from typing import TYPE_CHECKING, Any

from my_agent_crew.agent.turn_context import note_canvas_write
from my_agent_crew.artifacts.kinds import prepare
from my_agent_crew.artifacts.tag import artifact_tag
from my_agent_crew.clock import day_and_time
from my_agent_crew.tools.artifact_context import (
    CanvasAgent,
    kind_label,
    line_count,
    optional_text,
    text_arg,
)
from my_agent_crew.tools.artifact_edit import run_edit, run_rewrite
from my_agent_crew.tools.artifact_read import run_read
from my_agent_crew.tools.artifact_scope import (
    AGENT_KINDS,
    NEW_CANVAS,
    canvas_errors,
    check_agent_kind,
    check_budget,
    check_channel,
)
from my_agent_crew.tools.artifact_texts import (
    ARTIFACT_CREATE_DESCRIPTION,
    ARTIFACT_CREATED,
    ARTIFACT_EDIT_DESCRIPTION,
    ARTIFACT_LIST_DESCRIPTION,
    ARTIFACT_LIST_EMPTY,
    ARTIFACT_LIST_NEWER,
    ARTIFACT_LIST_NO_MATCH,
    ARTIFACT_LIST_ROW,
    ARTIFACT_LIST_UNREAD,
    ARTIFACT_READ_DESCRIPTION,
    ARTIFACT_REWRITE_DESCRIPTION,
    PARAM_CONTENT,
    PARAM_FROM_LINE,
    PARAM_ID,
    PARAM_KIND,
    PARAM_LANGUAGE,
    PARAM_LINES,
    PARAM_NEW,
    PARAM_NEW_TITLE,
    PARAM_OLD,
    PARAM_QUERY,
    PARAM_REPLACE_ALL,
    PARAM_TITLE,
    PARAM_VERSION,
)
from my_agent_crew.tools.registry import Tool

if TYPE_CHECKING:
    from my_agent_crew.store import Store
    from my_agent_crew.store.artifact_models import ArtifactSummary

# Rows a list shows: the canvases changed most recently, which are the ones a turn is after.
LIST_LIMIT = 30


async def _create(agent: CanvasAgent, args: dict[str, Any]) -> str:
    conv = agent.conversation()
    check_channel(conv)
    title, kind, content = (text_arg(args, name) for name in ("title", "kind", "content"))
    language = optional_text(args, "language") or ""
    check_agent_kind(kind)
    check_budget(NEW_CANVAS)
    with canvas_errors():
        text, size = prepare(kind, content, None)
        summary = agent.store.artifacts.create(
            title, kind, agent.agent_id, agent.author, conv.id, content=content, language=language
        )
    note_canvas_write(NEW_CANVAS)
    agent.share(conv, summary.id)
    agent.store.artifact_links.mark_seen(conv.id, summary.id, 1)
    lines = line_count(text)
    done = ARTIFACT_CREATED.format(title=summary.title, kind=kind, size=size, lines=lines)
    return f"{artifact_tag(summary.id, 1)}\n{done}"


async def _list(agent: CanvasAgent, args: dict[str, Any]) -> str:
    conv = agent.conversation()
    query = (optional_text(args, "query") or "").strip() or None
    canvases = agent.store.artifacts
    if agent.is_master:
        found = canvases.list(query=query, limit=LIST_LIMIT)
    else:
        found = canvases.reachable(conv.id, conv.root_id, agent.agent_id, query, LIST_LIMIT)
    if not found:
        return ARTIFACT_LIST_NO_MATCH.format(query=query) if query else ARTIFACT_LIST_EMPTY
    links = agent.store.artifact_links.links_for(conv.id)
    seen = {link.artifact_id: link.seen_version for link in links}
    return "\n".join(_row(agent, summary, seen.get(summary.id, 0)) for summary in found)


def _row(agent: CanvasAgent, summary: ArtifactSummary, seen: int) -> str:
    """One canvas, flagged when this conversation has not seen its newest version."""
    if seen == 0:
        flag = ARTIFACT_LIST_UNREAD
    elif seen < summary.head_version:
        flag = ARTIFACT_LIST_NEWER.format(seen=seen)
    else:
        flag = ""
    return ARTIFACT_LIST_ROW.format(
        id=summary.id,
        title=summary.title,
        kind=kind_label(summary),
        version=summary.head_version,
        when=day_and_time(summary.updated_at, agent.zone),
        flag=flag,
    )


def _text(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _number(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def _schema(required: list[str], **properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def build_artifact_tools(
    store: Store, agent_id: str, is_master: bool, limit: int, zone: tzinfo | None = None
) -> list[Tool]:
    """The five canvas tools for one agent. `limit` is its registry's output cap, which a
    page and a diff are sized to fit; `zone` is the owner's, for the times a list shows."""
    agent = CanvasAgent(store, agent_id, is_master, limit, zone)
    kind = {"type": "string", "enum": list(AGENT_KINDS), "description": PARAM_KIND}
    create = _schema(
        ["title", "kind", "content"],
        title=_text(PARAM_TITLE),
        kind=kind,
        content=_text(PARAM_CONTENT),
        language=_text(PARAM_LANGUAGE),
    )
    read = _schema(
        ["id"],
        id=_text(PARAM_ID),
        version=_number(PARAM_VERSION),
        from_line=_number(PARAM_FROM_LINE),
        lines=_number(PARAM_LINES),
    )
    edit = _schema(
        ["id", "old", "new"],
        id=_text(PARAM_ID),
        old=_text(PARAM_OLD),
        new=_text(PARAM_NEW),
        replace_all={"type": "boolean", "description": PARAM_REPLACE_ALL},
        title=_text(PARAM_NEW_TITLE),
    )
    rewrite = _schema(
        ["id", "content"],
        id=_text(PARAM_ID),
        content=_text(PARAM_CONTENT),
        title=_text(PARAM_NEW_TITLE),
    )
    return [
        Tool("artifact_create", ARTIFACT_CREATE_DESCRIPTION, create, partial(_create, agent)),
        Tool(
            "artifact_list",
            ARTIFACT_LIST_DESCRIPTION,
            _schema([], query=_text(PARAM_QUERY)),
            partial(_list, agent),
        ),
        Tool("artifact_read", ARTIFACT_READ_DESCRIPTION, read, partial(run_read, agent)),
        Tool("artifact_edit", ARTIFACT_EDIT_DESCRIPTION, edit, partial(run_edit, agent)),
        Tool(
            "artifact_rewrite", ARTIFACT_REWRITE_DESCRIPTION, rewrite, partial(run_rewrite, agent)
        ),
    ]
