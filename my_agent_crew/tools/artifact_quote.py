"""What a canvas write quotes back of what it changed: an edit shows the lines it changed, and a
rewrite refused over versions its conversation never saw shows who wrote them and what they
changed. Finding the changed lines takes time in step with the square of the lines between the
ends two texts share, so a change spread over more than `MIDDLE_LINES` is not drawn: the result
says so and sends the agent to read the canvas. A diff that is drawn is drawn off the event
loop, which every conversation of the server shares."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from my_agent_crew.artifacts.diff import MIDDLE_LINES, fenced_diff, middle_lines
from my_agent_crew.store.artifact_authors import authors_line
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_CONFLICT_WIDE,
    ARTIFACT_EDIT_DIFF_WIDE,
    ARTIFACT_VERSION_CONFLICT,
)
from my_agent_crew.tools.artifact_context import CUT_MARK_ROOM, CanvasAgent
from my_agent_crew.tools.artifact_scope import canvas_errors
from my_agent_crew.tools.artifact_texts import ARTIFACT_CONFLICT_DIFF
from my_agent_crew.tools.registry import ToolError

if TYPE_CHECKING:
    from my_agent_crew.store.artifact_models import ArtifactVersion

# The most a diff takes in a result: enough to check that an edit landed where it was meant,
# and to see what someone else changed before trying a rewrite again.
EDIT_DIFF_CHARS = 1500
CONFLICT_DIFF_CHARS = 4000


def _too_wide(before: str, after: str) -> bool:
    return middle_lines(before, after) > MIDDLE_LINES


async def edit_diff(limit: int, parts: list[str], before: str, after: str) -> str:
    """What an edit quotes of its change, to follow `parts`, the rest of its result, inside the
    output cap `limit`."""
    if _too_wide(before, after):
        return ARTIFACT_EDIT_DIFF_WIDE
    room = min(EDIT_DIFF_CHARS, limit - sum(len(p) + 1 for p in parts) - CUT_MARK_ROOM)
    return await asyncio.to_thread(fenced_diff, before, after, room)


async def rewrite_conflict(
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
    before, after = old.content or "", head.content or ""
    if _too_wide(before, after):
        parts.append(ARTIFACT_CONFLICT_WIDE.format(seen=seen, head=head.version))
        return ToolError("\n".join(parts))
    parts.append(ARTIFACT_CONFLICT_DIFF.format(seen=seen, head=head.version))
    taken = len(TOOL_FAILED.format(error="")) + sum(len(p) + 1 for p in parts) + CUT_MARK_ROOM
    room = min(CONFLICT_DIFF_CHARS, agent.limit - taken)
    block = await asyncio.to_thread(fenced_diff, before, after, room)
    return ToolError("\n".join([*parts, block]))
