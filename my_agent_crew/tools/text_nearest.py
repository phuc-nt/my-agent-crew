"""Where an edit that matched nothing was probably aimed: the passage most like its `old`,
quoted with a little context so the agent can copy the right text on its next try. Runs off
the event loop, and at a bounded cost: a canvas or an `old` past its ceiling is not searched,
and the edit is refused without a passage quoted."""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import accumulate, islice

from my_agent_crew.artifacts.diff import MIN_LINE_CHARS, excerpt, fenced, line_span
from my_agent_crew.texts_canvas import ARTIFACT_EDIT_NEAREST, ARTIFACT_EDIT_NO_MATCH, LINES_CUT
from my_agent_crew.tools.text_edit import EditNotFound, normalize_for_match

_TOKEN = re.compile(r"\w+|[^\w\s]")

MISS_MAX_OLD = 20_000  # an `old` longer than this is not searched for
# Characters. Tokenising and weighing the text takes memory that grows with its length: about
# 70 MB at this size for the densest text measured (minified script), about 20 MB for prose.
# A markdown, code or mermaid canvas is at most half of it and an html page may fill it; a
# larger one, mostly a deck carrying its images inline, gets the plain not-found error.
MISS_MAX_TEXT = 1024 * 1024
MATCH_TOKENS = 500  # only the start of a longer `old` is compared
MISS_WINDOWS = 3  # candidate passages compared closely
SIMILAR_ENOUGH = 0.5
TIE = 0.05  # two passages closer than this are a guess, so neither is shown
MISS_CHARS = 2400
MISS_LINES = 40
MISS_CONTEXT = 3  # lines shown on either side of the passage
CONTEXT_WIDTH = 160
PAD = 120  # characters kept on either side of the part of a long line that matched


@dataclass(frozen=True)
class Region:
    """Lines `first` to `last` (from 1) as shown: long lines cut, and a count of the lines
    left out at the end when the passage ran out of room."""

    first: int
    last: int
    text: str


async def explain_miss(text: str, old: str) -> EditNotFound:
    """The not-found error, with the closest passage quoted when there is a clear one."""
    region = await asyncio.to_thread(nearest_region, text, old)
    if region is None:
        return EditNotFound(ARTIFACT_EDIT_NO_MATCH)
    nearest = ARTIFACT_EDIT_NEAREST.format(span=line_span(region.first, region.last))
    return EditNotFound(f"{ARTIFACT_EDIT_NO_MATCH}\n{nearest}\n{fenced(region.text)}")


def nearest_region(text: str, old: str) -> Region | None:
    """The passage most like `old`, with its context. None when nothing is close enough, or
    when two passages are about as close, since quoting either would be a guess."""
    if len(old) > MISS_MAX_OLD or len(text) > MISS_MAX_TEXT:
        return None
    loose = normalize_for_match(text)
    words = [word.lower() for word in _TOKEN.findall(loose)]
    wanted = [word.lower() for word in _TOKEN.findall(normalize_for_match(old))][:MATCH_TOKENS]
    if not wanted or not words:
        return None
    size = min(len(wanted), len(words))
    ratios = sorted(
        (
            (SequenceMatcher(None, words[at : at + size], wanted, autojunk=False).ratio(), at)
            for at in _candidates(words, wanted, size)
        ),
        reverse=True,
    )
    if not ratios or ratios[0][0] < SIMILAR_ENOUGH:
        return None
    if len(ratios) > 1 and ratios[0][0] - ratios[1][0] < TIE:
        return None
    window = list(islice(_TOKEN.finditer(loose), ratios[0][1], ratios[0][1] + size))
    return _region(text, window[0].start(), window[-1].end())


def _candidates(words: list[str], wanted: list[str], size: int) -> list[int]:
    """Where the few windows of `size` words that share the most rare words with `wanted`
    start. A word counts for less the more often the text repeats it, so a line found all
    over, a fence or a table rule, cannot pull a window away. Each window is then lined up on
    its rarest word that `wanted` has once, and windows overlapping it are passed over."""
    counts, wanted_set, repeats = Counter(words), set(wanted), Counter(wanted)
    weight = [1 / counts[word] if word in wanted_set else 0.0 for word in words]
    sums = list(accumulate(weight, initial=0.0))
    scores = [sums[at + size] - sums[at] for at in range(len(words) - size + 1)]
    once = {word: at for at, word in enumerate(wanted) if repeats[word] == 1}
    picks = []
    for _ in range(MISS_WINDOWS):
        start = max(range(len(scores)), key=scores.__getitem__)
        if scores[start] < 1e-9:
            break
        anchor = max(range(start, start + size), key=lambda at: weight[at] * (words[at] in once))
        if words[anchor] in once:
            start = min(max(anchor - once[words[anchor]], 0), len(scores) - 1)
        picks.append(start)
        for masked in range(max(0, start - size + 1), min(len(scores), start + size)):
            scores[masked] = -1.0
    return picks


def _region(text: str, start: int, end: int) -> Region:
    """The lines holding `text[start:end]`, long ones cut around the match. A passage shown
    whole gets up to three lines either side while there is room; one that runs out of room
    ends with a count of the lines left out instead."""
    lines = text.split("\n")
    first, last = text.count("\n", 0, start), text.count("\n", 0, end - 1)
    mark = len(LINES_CUT.format(n=last - first + 1)) + 1
    room, slots = MISS_CHARS - mark, MISS_LINES - 1
    core, offset = [], text.rfind("\n", 0, start) + 1
    for line in lines[first : last + 1]:
        low, high = max(start - offset, 0), min(end - offset, len(line))
        width = min(room - 1, max(CONTEXT_WIDTH, high - low + 2 * PAD))
        if len(core) == slots or width < MIN_LINE_CHARS:
            break
        core.append(excerpt(line, low, high, width))
        room -= len(core[-1]) + 1
        offset += len(line) + 1
    complete = len(core) == last - first + 1
    before, after = [], []
    if complete:
        room, slots = room + mark, slots + 1
        for distance in range(1, MISS_CONTEXT + 1):
            for side, index in ((before, first - distance), (after, last + distance)):
                if len(side) < distance - 1 or not 0 <= index < len(lines):
                    continue  # this side already stopped short, or the text ends here
                shown = excerpt(lines[index], 0, 0, CONTEXT_WIDTH)
                if len(core) + len(before) + len(after) < slots and len(shown) + 1 <= room:
                    side.append(shown)
                    room -= len(shown) + 1
    tail = [] if complete else [LINES_CUT.format(n=last - first + 1 - len(core))]
    body = "\n".join([*before[::-1], *core, *after, *tail])
    return Region(first - len(before) + 1, first + len(core) + len(after), body)
