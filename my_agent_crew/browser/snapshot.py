"""A page as the model is given it, and as the gate reads it.

Playwright draws a page as an outline: one element a line, its role, its name in quotes, and
a `[ref=…]` that finds the element again. The model acts by ref and says the name it read;
this module reads the same outline back into a table of ref, role and name, so an action can
be checked against the page as it is now and not as the model remembers it.

A line that is not drawn the way an element is gives no entry, and so nothing to act on: a
name is never guessed from a line half understood. Each entry also carries the first of the
agent's ask words found in its own text or in anything under it, since a click on a box
lands on whatever the box holds.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urldefrag

from my_agent_crew.browser.policy import AskWords

# role, then the name as JSON, then attributes in square brackets.
KEY = re.compile(r'([^\s":\[]+)(?: ("(?:[^"\\]|\\.)*"))?((?: \[[^\]]*\])*)')
REF = re.compile(r"\[ref=(\w+)\]")
POINTER = "[cursor=pointer]"


@dataclass(frozen=True)
class Node:
    ref: str
    role: str
    name: str
    # The ask word its own text or anything under it holds, "" for none.
    word: str = ""


@dataclass(frozen=True)
class Line:
    indent: int
    drawn: str  # the line without its indent
    role: str  # "" for a line that was not understood
    name: str
    text: str  # name and value, what a search looks in
    ref: str
    parent: int  # the line it stands under, -1 at the top
    pointer: bool


@dataclass(frozen=True)
class Snapshot:
    lines: tuple[Line, ...]
    nodes: Mapping[str, Node]


@dataclass(frozen=True)
class Shown:
    """What a tab last gave the model: the page it was and every element on it."""

    url: str
    nodes: Mapping[str, Node]


def address(url: str) -> str:
    """A page's address without the part after `#`, which moves within the same page."""
    return urldefrag(url).url


def same_name(one: str, other: str) -> bool:
    """Two names a person would read as the same: spacing and case aside."""
    return " ".join(one.split()).casefold() == " ".join(other.split()).casefold()


def _key(item: str) -> tuple[str, str] | None:
    """A line's key and what follows it. A key that holds a colon or a hash is drawn inside
    single quotes, with a quote of its own doubled."""
    if not item.startswith("'"):
        match = KEY.match(item)
        return (match.group(0), item[match.end() :]) if match else None
    end = 1
    while (end := item.find("'", end)) >= 0 and item[end + 1 : end + 2] == "'":
        end += 2
    return (item[1:end].replace("''", "'"), item[end + 1 :]) if end >= 0 else None


def _value(rest: str) -> str:
    value = rest[2:]
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return str(json.loads(value))
        except ValueError:
            return value[1:-1]
    return value


def _element(item: str) -> tuple[str, str, str, str, bool] | None:
    """Role, name, value, ref and whether it shows a pointer, for a line drawn the way an
    element is; None for any other."""
    split = _key(item)
    if split is None:
        return None
    key, rest = split
    match = KEY.fullmatch(key)
    if match is None or not (rest in ("", ":") or rest.startswith(": ")):
        return None
    role, quoted, attributes = match.groups()
    refs = REF.findall(attributes)
    try:
        name = json.loads(quoted) if quoted else ""
    except ValueError:
        return None
    if len(refs) > 1:
        return None
    return role, name, _value(rest), refs[0] if refs else "", POINTER in attributes


def read(outline: str, ask: AskWords) -> Snapshot:
    lines: list[Line] = []
    found: dict[int, str] = {}
    times: dict[str, int] = {}
    above: list[int] = []
    for whole in outline.splitlines():
        drawn = whole.lstrip(" ")
        if not drawn:
            continue
        indent = len(whole) - len(drawn)
        while above and lines[above[-1]].indent >= indent:
            above.pop()
        element = _element(drawn[2:]) if drawn.startswith("- ") else None
        role, name, value, ref, pointer = element or ("", "", "", "", False)
        text = f"{name} {value}".strip() if element else drawn
        index, parent = len(lines), above[-1] if above else -1
        lines.append(Line(indent, drawn, role, name, text, ref, parent, pointer))
        # An address is not something a person reads on the page, so it asks for nothing.
        word = "" if role.startswith("/") else ask.find(text)
        if word:
            for holder in (*above, index):
                found.setdefault(holder, word)
        above.append(index)
        if ref:
            times[ref] = times.get(ref, 0) + 1
    nodes = {
        line.ref: Node(line.ref, line.role, line.name, found.get(i, ""))
        for i, line in enumerate(lines)
        if line.ref and times[line.ref] == 1  # a ref drawn twice finds nothing for certain
    }
    return Snapshot(tuple(lines), nodes)
