"""`artifact_read`: a canvas one page at a time, the text exactly as stored. A page is sized to
fit the agent's output cap whole, with room left for a hook's note; each page moves the
conversation's read cursor, and only a cursor that reaches the end of a version counts as
having seen it, so a page cut short or skipped never lets a rewrite through."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from my_agent_crew.artifacts.diff import line_span
from my_agent_crew.texts_canvas import ARTIFACT_READ_BINARY, ARTIFACT_READ_PAST_END, LINE_CUT_TAIL
from my_agent_crew.tools.artifact_context import (
    CUT_MARK_ROOM,
    CanvasAgent,
    int_arg,
    kind_label,
    text_arg,
)
from my_agent_crew.tools.artifact_scope import authors_line, canvas_errors
from my_agent_crew.tools.artifact_texts import (
    ARTIFACT_READ_BEHIND,
    ARTIFACT_READ_END,
    ARTIFACT_READ_HEADER,
    ARTIFACT_READ_MORE,
)
from my_agent_crew.tools.registry import ToolError

if TYPE_CHECKING:
    from my_agent_crew.store.artifact_models import ArtifactSummary, ArtifactVersion


async def run_read(agent: CanvasAgent, args: dict[str, Any]) -> str:
    conv = agent.conversation()
    artifact_id = text_arg(args, "id")
    agent.reach(conv, artifact_id)
    canvases = agent.store.artifacts
    number = int_arg(args.get("version"), 0)
    with canvas_errors(artifact_id):
        summary = canvases.get(artifact_id)
        doc = canvases.head(artifact_id) if number <= 0 else canvases.version(artifact_id, number)
        history = canvases.versions(artifact_id)
    if doc.content is None:
        raise ToolError(ARTIFACT_READ_BINARY.format(kind=summary.kind))
    lines = doc.content.split("\n")
    first = max(int_arg(args.get("from_line"), 1), 1)
    if first > len(lines):
        raise ToolError(ARTIFACT_READ_PAST_END.format(version=doc.version, total=len(lines)))
    authors = authors_line(history, agent.seen(conv, artifact_id), doc.version)
    page = _Page(summary, doc, lines)
    room = agent.limit - page.widest(authors) - CUT_MARK_ROOM
    body, upto, cut = _fill(lines, first - 1, max(room, 1), int_arg(args.get("lines"), 0))
    start = sum(len(line) + 1 for line in lines[: first - 1])
    end = start + cut if cut else min(start + sum(len(line) + 1 for line in body), len(doc.content))
    agent.store.artifact_links.mark_read(
        conv.id, artifact_id, doc.version, start, end, len(doc.content)
    )
    shown = [page.header(line_span(first, upto)), *([authors] if authors else []), *body]
    return "\n".join([*shown, page.footer(upto)])


class _Page:
    """The lines around a page's text, and the most they can take."""

    def __init__(self, summary: ArtifactSummary, doc: ArtifactVersion, lines: list[str]):
        self.summary, self.doc, self.total = summary, doc, len(lines)

    def header(self, span: str) -> str:
        head = self.summary.head_version
        behind = ARTIFACT_READ_BEHIND.format(head=head) if self.doc.version < head else ""
        return ARTIFACT_READ_HEADER.format(
            title=self.summary.title,
            id=self.summary.id,
            version=self.doc.version,
            kind=kind_label(self.summary),
            span=span,
            total=self.total,
            behind=behind,
        )

    def footer(self, upto: int) -> str:
        """Where to read on, or that this was the last page."""
        if upto >= self.total:
            return ARTIFACT_READ_END
        line = upto + 1
        return ARTIFACT_READ_MORE.format(id=self.summary.id, version=self.doc.version, line=line)

    def widest(self, authors: str) -> int:
        """What everything but the text takes at most, with the newlines between them."""
        header = len(self.header(f"{self.total}–{self.total}"))
        footer = max(len(self.footer(self.total - 1)), len(ARTIFACT_READ_END))
        return header + footer + (len(authors) + 1 if authors else 0) + 2


def _fill(lines: list[str], index: int, room: int, cap: int) -> tuple[list[str], int, int]:
    """The whole lines from `index` (from 0) that fit in `room` characters, at most `cap` of
    them when `cap` is above 0; the number (from 1) of the last one; and how many characters
    of it were kept when even the first was too long and had to be cut, 0 otherwise."""
    body: list[str] = []
    used = 0
    while index < len(lines) and (cap <= 0 or len(body) < cap):
        cost = len(lines[index]) + (1 if body else 0)
        if used + cost > room:
            break
        body.append(lines[index])
        used += cost
        index += 1
    if body:
        return body, index, 0
    line = lines[index]
    keep = max(room - len(LINE_CUT_TAIL.format(n=len(line))), 1)
    return [line[:keep] + LINE_CUT_TAIL.format(n=len(line) - keep)], index + 1, keep
