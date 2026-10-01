"""`artifact_edit` and `artifact_rewrite`: changing a canvas the agent reaches. An edit replaces
one passage and needs no read first, since it only lands where `old` still stands; a rewrite
replaces everything, so it must start from the newest version this conversation has seen
whole, and never writes over what a person or another agent changed since. Both make their
change inside the store's lock and quote back a diff of what changed."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from my_agent_crew.agent.turn_context import note_canvas_write
from my_agent_crew.artifacts.diff import fenced_diff
from my_agent_crew.artifacts.kinds import cap_bytes, clean_title, prepare
from my_agent_crew.artifacts.tag import artifact_tag
from my_agent_crew.store.artifact_authors import authors_line
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import ARTIFACT_REWRITE_UNSEEN, ARTIFACT_VERSION_CONFLICT
from my_agent_crew.tools.artifact_context import (
    CUT_MARK_ROOM,
    CanvasAgent,
    flag_arg,
    line_count,
    optional_text,
    text_arg,
)
from my_agent_crew.tools.artifact_scope import (
    canvas_errors,
    check_agent_kind,
    check_budget,
    check_channel,
)
from my_agent_crew.tools.artifact_texts import (
    ARTIFACT_CONFLICT_DIFF,
    ARTIFACT_EDITED,
    ARTIFACT_RENAMED,
    ARTIFACT_REWRITTEN,
    ARTIFACT_UNCHANGED,
)
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.text_edit import EditNotFound, apply_edit
from my_agent_crew.tools.text_nearest import explain_miss

if TYPE_CHECKING:
    from my_agent_crew.store.artifact_models import ArtifactVersion
    from my_agent_crew.store.models import Conversation

# The most a diff takes in a result: enough to check that an edit landed where it was meant,
# and to see what someone else changed before trying a rewrite again.
EDIT_DIFF_CHARS = 1500
CONFLICT_DIFF_CHARS = 4000


class _Unchanged(Exception):
    """The write would leave the newest version as it is."""

    def __init__(self, version: int):
        self.version = version


class _Stale(Exception):
    """A rewrite from a version older than the newest."""

    def __init__(self, head: ArtifactVersion):
        self.head = head


async def run_edit(agent: CanvasAgent, args: dict[str, Any]) -> str:
    conv = agent.conversation()
    check_channel(conv)
    artifact_id, old, new = (text_arg(args, name) for name in ("id", "old", "new"))
    title = optional_text(args, "title")
    replace_all = flag_arg(args.get("replace_all"))
    kind = _writable_kind(agent, conv, artifact_id)
    check_budget(artifact_id)
    seen = agent.seen(conv, artifact_id)
    before: dict[str, Any] = {}

    def change(head: ArtifactVersion) -> str:
        before["head"] = head
        cap = cap_bytes(kind)
        text, before["count"] = apply_edit(head.content or "", old, new, replace_all, cap)
        if prepare(kind, text, None)[0] == head.content:
            raise _Unchanged(head.version)
        return text

    try:
        with canvas_errors(artifact_id):
            written = agent.store.artifacts.apply(
                artifact_id, change, agent.author, conv.id, title=title
            )
    except EditNotFound:
        # Looked for once the lock is let go: the search may take a while on a long canvas.
        raise await explain_miss(before["head"].content or "", old) from None
    except _Unchanged as exc:
        return _unchanged(agent, artifact_id, exc.version, title)
    head = before["head"]
    _written(agent, conv, artifact_id, written.version, moved=head.version == seen)
    lines = line_count(written.content)
    edited = ARTIFACT_EDITED.format(count=before["count"], size=written.size, lines=lines)
    parts = [artifact_tag(artifact_id, written.version), edited]
    if head.version != seen:
        with canvas_errors(artifact_id):
            history = agent.store.artifacts.versions(artifact_id)
        authors = authors_line(history, seen, head.version)
        if authors:
            parts.append(authors)
    room = min(EDIT_DIFF_CHARS, agent.limit - sum(len(p) + 1 for p in parts) - CUT_MARK_ROOM)
    parts.append(fenced_diff(head.content or "", written.content or "", room))
    return "\n".join(parts)


async def run_rewrite(agent: CanvasAgent, args: dict[str, Any]) -> str:
    conv = agent.conversation()
    check_channel(conv)
    artifact_id, content = text_arg(args, "id"), text_arg(args, "content")
    title = optional_text(args, "title")
    kind = _writable_kind(agent, conv, artifact_id)
    check_budget(artifact_id)
    seen = agent.seen(conv, artifact_id)
    if seen == 0:
        raise ToolError(ARTIFACT_REWRITE_UNSEEN.format(id=artifact_id))

    def change(head: ArtifactVersion) -> str:
        if head.version != seen:
            raise _Stale(head)
        if prepare(kind, content, None)[0] == head.content:
            raise _Unchanged(head.version)
        return content

    try:
        with canvas_errors(artifact_id):
            written = agent.store.artifacts.apply(
                artifact_id, change, agent.author, conv.id, title=title
            )
    except _Stale as exc:
        raise await _conflict(agent, artifact_id, seen, exc.head) from None
    except _Unchanged as exc:
        return _unchanged(agent, artifact_id, exc.version, title)
    _written(agent, conv, artifact_id, written.version, moved=True)
    done = ARTIFACT_REWRITTEN.format(size=written.size, lines=line_count(written.content))
    return f"{artifact_tag(artifact_id, written.version)}\n{done}"


def _writable_kind(agent: CanvasAgent, conv: Conversation, artifact_id: str) -> str:
    """The canvas's kind, asked only once the canvas is known to be in reach, so a refusal
    never tells an agent the kind of a canvas it cannot open."""
    agent.reach(conv, artifact_id)
    with canvas_errors(artifact_id):
        kind = agent.store.artifacts.get(artifact_id).kind
    check_agent_kind(kind)
    return kind


def _written(
    agent: CanvasAgent, conv: Conversation, artifact_id: str, version: int, *, moved: bool
) -> None:
    """Counts the write against the turn and shares the canvas with the conversation and its
    root. What the conversation has seen moves only when it had seen the version written
    over: a write on top of versions it never saw does not make them seen."""
    note_canvas_write(artifact_id)
    agent.share(conv, artifact_id)
    if moved:
        agent.store.artifact_links.mark_seen(conv.id, artifact_id, version)


def _unchanged(agent: CanvasAgent, artifact_id: str, version: int, title: str | None) -> str:
    """A write that changed nothing adds no version and is not counted; a new title sent with
    it still renames the canvas."""
    lines = [artifact_tag(artifact_id, version, unchanged=True), ARTIFACT_UNCHANGED]
    if title is not None:
        with canvas_errors(artifact_id):
            if clean_title(title) != agent.store.artifacts.get(artifact_id).title:
                renamed = agent.store.artifacts.rename(artifact_id, title)
                lines.append(ARTIFACT_RENAMED.format(title=renamed.title))
    return "\n".join(lines)


async def _conflict(
    agent: CanvasAgent, artifact_id: str, seen: int, head: ArtifactVersion
) -> ToolError:
    """The refusal of a rewrite over versions the conversation has not seen: who wrote them
    and what they changed since its version, so the agent can redo its change on theirs."""
    with canvas_errors(artifact_id):
        old = agent.store.artifacts.version(artifact_id, seen)
        history = agent.store.artifacts.versions(artifact_id)
    parts = [ARTIFACT_VERSION_CONFLICT.format(head=head.version)]
    authors = authors_line(history, seen, head.version)
    if authors:
        parts.append(authors)
    parts.append(ARTIFACT_CONFLICT_DIFF.format(seen=seen, head=head.version))
    taken = len(TOOL_FAILED.format(error="")) + sum(len(p) + 1 for p in parts) + CUT_MARK_ROOM
    room = min(CONFLICT_DIFF_CHARS, agent.limit - taken)
    block = await asyncio.to_thread(fenced_diff, old.content or "", head.content or "", room)
    return ToolError("\n".join([*parts, block]))
