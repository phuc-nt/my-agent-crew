"""How an answer of the desktop tools is laid out.

Whatever the screen has a say in (the names of applications and windows, the outline of an
application, what a model read off a picture) is put between two fence lines made for this
one answer, under a line saying it is data. Outside the fence stand only words of this
program and of the agent's own file. An outline is sized so the whole answer stays under the
registry's cap: an answer cut by the registry would lose its closing fence.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts_desktop as t
from my_agent_crew.browser.fence import CUT_ROOM
from my_agent_crew.browser.kit import one_line

ROLE_CHARS, TITLE_CHARS, VALUE_CHARS, APP_CHARS = 60, 120, 200, 80
# How far a line is pushed in for its depth, at most.
DEEPEST = 20
# Left for the notes written once the screen's own text is sized.
NOTE_ROOM = 300
REF = re.compile(r"a[0-9]{1,6}")
# A role is a word of the system's, like AXButton. One of another shape is not shown: it
# stands before the screen's own text on a line, where this program's words are read.
ROLE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
SECURE_ROLE = "AXSecureTextField"


def fence() -> tuple[str, str, str]:
    """The line that says what the fence is, and the two lines of the fence itself. The
    number in them is made anew each time: nothing on the screen can write a line that
    closes it."""
    nonce = secrets.token_hex(8)
    opening, closing = t.SCREEN_OPEN.format(nonce=nonce), t.SCREEN_CLOSE.format(nonce=nonce)
    return t.SCREEN_FENCE.format(opening=opening, closing=closing), opening, closing


def fenced(body: str) -> str:
    said, opening, closing = fence()
    return "\n".join([said, opening, body, closing])


def room(limit: int, *written: str) -> int:
    """What is left under the cap for the screen's own text, beside everything else an
    answer holds, its fence, the notes written afterwards and the widest mark of a cut the
    registry may write. Nothing, under a cap that small."""
    used = sum(len(part) + 1 for part in (*written, *fence()))
    return max(0, limit - used - NOTE_ROOM - CUT_ROOM)


def no_room(limit: int) -> str:
    return t.SCREEN_NO_ROOM.format(limit=limit)


def answer(limit: int, outside: list[str], body: str) -> str:
    """What a tool answers: its own lines, then what the screen had a say in between the
    fence lines, cut to the room left. Under a cap with no room for it, why it is missing."""
    most = room(limit, *outside)
    return "\n".join([*outside, fenced(body[:most]) if most else no_room(limit)])


def with_data(limit: int, said: str, data: str, *, used: int = 0) -> str:
    """`said` with `data` fenced under it when the whole stays under the cap, beside `used`
    and the widest mark of a cut; `said` alone otherwise. Never a fence a cut would open
    and not close."""
    whole = "\n".join([said, fenced(data)])
    return whole if used + len(whole) + CUT_ROOM <= limit else said


def words(value: Any, limit: int) -> str:
    """A text of the helper on one line; anything that is no text is nothing."""
    return one_line(value, limit) if isinstance(value, str) else ""


def app_line(row: dict) -> str:
    """An application as an answer names it, inside the fence."""
    name, bundle = words(row.get("app"), APP_CHARS), words(row.get("bundle_id"), APP_CHARS)
    named = f"{name} ({bundle})" if name and bundle else name or bundle
    return t.APP_HIDDEN.format(app=named) if row.get("hidden") is True else named


def is_secure(node: dict) -> bool:
    return node.get("secure") is True or node.get("role") == SECURE_ROLE


def label(node: dict) -> str:
    """What an element is called: its title, or what it holds when it has none. A secure
    field is never called by what it holds."""
    if title := words(node.get("title"), TITLE_CHARS):
        return title
    return "" if is_secure(node) else words(node.get("value"), VALUE_CHARS)


def node_line(node: dict, tag: str) -> str:
    """One element of an outline. What this program says of it comes first (its ref with
    the tag of this outline, then what it marks it as), and what the screen says of it
    after: nothing the screen wrote stands where a ref or a mark is read. A secure field
    shows that it is one and never a value, whatever the helper sent with it."""
    depth = node.get("depth")
    indent = "  " * min(depth, DEEPEST) if isinstance(depth, int) and depth > 0 else ""
    marks = [t.NODE_SECURE] if is_secure(node) else []
    marks += [t.NODE_FOCUSED] if node.get("focused") is True else []
    marks += [t.NODE_DISABLED] if node.get("enabled") is False else []
    line = f"{indent}- [ref={node['ref']}-{tag}]" + (f" ({'; '.join(marks)})" if marks else "")
    role = words(node.get("role"), ROLE_CHARS)
    line += f" {role if ROLE.fullmatch(role) else '?'}"
    if title := words(node.get("title"), TITLE_CHARS):
        line += f' "{title}"'
    value = "" if is_secure(node) else words(node.get("value"), VALUE_CHARS)
    return f"{line}: {value}" if value else line


@dataclass(frozen=True)
class Outline:
    text: str
    shown: int
    total: int
    # The refs of secure fields, of the whole outline and not only of what fitted.
    secure: frozenset[str]
    # What each row that fitted is called, by its ref.
    named: dict[str, str]


def outline(nodes: Any, chars: int, tag: str) -> Outline:
    """The elements the helper listed, one line each, as many as fit `chars`, each ref
    with `tag`. An element without a ref of the helper's own shape is left out: a ref is
    all an action can name."""
    rows = [
        node
        for node in (nodes if isinstance(nodes, list) else [])
        if isinstance(node, dict)
        and isinstance(node.get("ref"), str)
        and REF.fullmatch(node["ref"])
    ]
    lines: list[str] = []
    named: dict[str, str] = {}
    used = 0
    for node in rows:
        line = node_line(node, tag)
        if used + len(line) + 1 > chars:
            break
        lines.append(line)
        named[node["ref"]] = label(node)
        used += len(line) + 1
    secure = frozenset(node["ref"] for node in rows if is_secure(node))
    return Outline("\n".join(lines), len(lines), len(rows), secure, named)
