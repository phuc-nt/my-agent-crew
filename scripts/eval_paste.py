"""Whether the chat pasted a canvas back, for `canvas_not_in_chat`.

A canvas holds the document so that the chat does not have to. The check reads a canvas as one
run of words, line after line, and each message the agent wrote the same way, without markup,
case or accents, and takes the share of the canvas's three-word runs that some message repeats.
Half or more is a paste, whatever shape the lines took in the chat: as written, as a table, with
another separator, on one line.

Two things are fine to say again. The title, and a heading the canvas opens with, are how the
chat names the canvas, so they are not counted. A single line is a quote, the line the agent
changed above all: when every run the chat repeats lies within one line, nothing was pasted.
A paste that leaves out the label of every short line, the day of a plan with a room a day
say, keeps too few runs to be caught."""

from __future__ import annotations

import re
from typing import NamedTuple

from my_agent_crew.memory.search import normalize

PASTE_SHARE = 0.5  # the chat repeats this share of a canvas's runs or more: it pasted the canvas
RUN_WORDS = 3
_MARKER = re.compile(r"^(?:\s*(?:#+|>|[-*+]|\d+[.)]))+\s*")
_WORD = re.compile(r"[^\W_]+")


class Canvas(NamedTuple):
    title: str
    content: str


def pasted_share(canvas: Canvas, *said: str) -> float:
    """The share of the canvas's distinct runs that the messages in `said` repeat, no run
    spanning two messages; 0 when all they repeat lies within one line of the canvas."""
    lines = _counted_lines(canvas)
    runs = _runs([word for line in lines for word in line])
    heard: set[tuple[str, ...]] = set()
    for text in said:
        heard |= _runs(_words(text))
    repeated = runs & heard
    if not repeated or any(repeated <= _runs(line) for line in lines):
        return 0.0
    return len(repeated) / len(runs)


def _counted_lines(canvas: Canvas) -> list[list[str]]:
    """The words of each line the chat should not repeat: every line with words, but the
    heading the canvas opens with and any line that is its title."""
    written = [line for line in canvas.content.splitlines() if line.strip()]
    if written and written[0].startswith("#"):
        written = written[1:]
    title = _words(canvas.title)
    return [words for words in map(_line_words, written) if words and words != title]


def _words(text: str) -> list[str]:
    return [word for line in text.splitlines() for word in _line_words(line)]


def _line_words(line: str) -> list[str]:
    """The line's words, lower case and without accents, after its list or heading marker."""
    return _WORD.findall(normalize(_MARKER.sub("", line)))


def _runs(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i : i + RUN_WORDS]) for i in range(len(words) - RUN_WORDS + 1)}
