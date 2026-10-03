"""Showing canvas text in little room: a diff that never outgrows its budget, a long line cut
down to the part that matters, and a fence the quoted text cannot close."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from my_agent_crew.texts_canvas import DIFF_HUNK, LINE_CUT_HEAD, LINE_CUT_TAIL, LINES_CUT

# A changed line is shown in at most this many characters, around the part that changed.
DIFF_LINE_CHARS = 300
# The narrowest a cut line may be: both marks fit beside some text even on a 4 MB line.
MIN_LINE_CHARS = 60
# A change is drawn as a diff only while the lines between the ends both texts share number at
# most this many: comparing them line by line takes time in step with the square of that count,
# so past it the change is told in a sentence instead, wherever a diff would have been drawn.
MIDDLE_LINES = 600


def fenced(text: str, info: str = "") -> str:
    """A fence longer than any backtick run inside, so the text cannot close it early."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{info}\n{text}\n{fence}"


def line_span(first: int, last: int) -> str:
    return f"{first}–{last}" if last > first else str(first)


def excerpt(line: str, start: int, end: int, width: int) -> str:
    """At most `width` characters of `line`: centred on `line[start:end]` when that fits, from
    `start` when it does not, with what was left out counted at either end."""
    if len(line) <= width:
        return line
    marks = len(LINE_CUT_HEAD.format(n=len(line))) + len(LINE_CUT_TAIL.format(n=len(line)))
    room = max(1, width - marks)
    span = end - start
    low = min(start if span >= room else max(0, start - (room - span) // 2), len(line) - room)
    high = low + room
    head = LINE_CUT_HEAD.format(n=low) if low else ""
    tail = LINE_CUT_TAIL.format(n=len(line) - high) if high < len(line) else ""
    return f"{head}{line[low:high]}{tail}"


def fenced_diff(before: str, after: str, room: int) -> str:
    """`render_diff` in a diff fence, the whole block in at most `room` characters. A fence
    grows past three backticks only for a diff that quotes a longer run, so the diff is drawn
    again with what that fence leaves."""
    budget = room - len(fenced("", "diff"))
    block = fenced(render_diff(before, after, budget), "diff")
    while len(block) > room and budget > 0:
        budget -= len(block) - room
        block = fenced(render_diff(before, after, budget), "diff")
    return block


@dataclass(frozen=True)
class DiffText:
    """A drawn diff, and whether it shows every changed line in full: no line cut short and
    none counted in a mark instead of shown."""

    text: str
    whole: bool


def render_diff(before: str, after: str, budget: int) -> str:
    """The lines `after` changed from `before`, under headings numbered as in `after`, with no
    context. Removed lines take at most half the budget, so what was written always shows;
    whatever does not fit is counted in a closing mark."""
    return diff_text(before, after, budget).text


def diff_text(before: str, after: str, budget: int) -> DiffText:
    """`render_diff`, told apart from a diff that had to leave something out."""
    old, new, head, tail = _ends(before, after)
    # The default junk heuristic keeps a run of repeated lines from making this quadratic.
    matcher = SequenceMatcher(None, old[head : len(old) - tail], new[head : len(new) - tail])
    hunks = [
        (i1 + head, i2 + head, j1 + head, j2 + head)
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
        if op != "equal"
    ]
    changed = sum(i2 - i1 + j2 - j1 for i1, i2, j1, j2 in hunks)
    out = _Diff(room=budget - len(LINES_CUT.format(n=changed)) - 1, removed_room=budget // 2)
    for i1, i2, j1, j2 in hunks:
        first = min(j1 + 1, len(new))
        if not out.hunk(line_span(first, max(first, j2)), old[i1:i2], new[j1:j2]):
            break
    if out.counted < changed:
        out.lines.append(LINES_CUT.format(n=changed - out.counted))
    return DiffText("\n".join(out.lines), out.whole and out.counted == changed)


def middle_lines(before: str, after: str) -> int:
    """How many lines of the longer text lie between the ends both texts share: what a diff
    has to compare line by line."""
    old, new, head, tail = _ends(before, after)
    return max(len(old), len(new)) - head - tail


def _ends(before: str, after: str) -> tuple[list[str], list[str], int, int]:
    """Both texts' lines and how many lines they share at the start and, after that, at the
    end."""
    old, new = before.split("\n"), after.split("\n")
    head = _shared(old, new)
    return old, new, head, _shared(old[head:][::-1], new[head:][::-1])


@dataclass
class _Diff:
    room: int  # characters left, with the closing mark already set aside
    removed_room: int  # characters removed lines may still take
    lines: list[str] = field(default_factory=list)
    counted: int = 0  # changed lines shown, or counted in a mark of their own
    whole: bool = True  # no line cut short and none counted instead of shown

    def add(self, line: str) -> bool:
        if len(line) + 1 > self.room:
            return False
        self.lines.append(line)
        self.room -= len(line) + 1
        return True

    def hunk(self, span: str, removed: list[str], added: list[str]) -> bool:
        """Adds one change; False once the diff is out of room."""
        if not self.add(DIFF_HUNK.format(span=span)):
            return False
        shown = 0
        for index, line in enumerate(removed):
            text = "- " + self.cut(line, added[index] if index < len(added) else None)
            if len(text) + 1 > self.removed_room or not self.add(text):
                break
            self.removed_room -= len(text) + 1
            shown += 1
        self.counted += shown
        if shown < len(removed):
            self.whole = False
            if not self.add(LINES_CUT.format(n=len(removed) - shown)):
                return False
            self.counted += len(removed) - shown
        for index, line in enumerate(added):
            partner = removed[index] if index < len(removed) else None
            if not self.add("+ " + self.cut(line, partner)):
                # An added line too long for what is left is cut to fit, and ends the diff.
                if self.room - 3 >= MIN_LINE_CHARS and self.add(
                    "+ " + self.cut(line, partner, self.room - 3)
                ):
                    self.counted += 1
                return False
            self.counted += 1
        return True

    def cut(self, line: str, partner: str | None, width: int = DIFF_LINE_CHARS) -> str:
        """`_cut`, remembering that the diff is no longer whole when it shortened the line."""
        shown = _cut(line, partner, width)
        self.whole = self.whole and shown == line
        return shown


def _cut(line: str, partner: str | None, width: int = DIFF_LINE_CHARS) -> str:
    """`line` cut around where it differs from the line it replaced, or from its start."""
    if partner is None:
        return excerpt(line, 0, 0, width)
    start = _shared(line, partner)
    end = len(line) - _shared(line[start:][::-1], partner[start:][::-1])
    return excerpt(line, start, end, width)


def _shared(a: Sequence, b: Sequence) -> int:
    """How many leading items `a` and `b` have in common, found by halving."""
    low, high = 0, min(len(a), len(b))
    while low < high:
        middle = (low + high + 1) // 2
        if a[:middle] == b[:middle]:
            low = middle
        else:
            high = middle - 1
    return low
