"""Canvas steps in an eval case, and the check that a chat did not paste a canvas back.

A case's `messages` may hold, between its messages, what the person does in the web panel. Each
step goes over the REST routes the panel uses (`server/routes_artifacts.py`), as the person:

- `create_canvas: {title, content, kind?}` makes a canvas in the conversation and opens it;
- `edit_canvas: {old, new}` replaces the one place `old` is in the open canvas and saves it on
  the version it read, as the editor does;
- `select_canvas: <text>` selects the one place the text is, for the next message to carry.

With no canvas open a step takes the conversation's most recently changed one, as the panel
would show it. Every message after a canvas is open carries it, and a selection goes with the
next message only, as a message from the web does (`server/routes_chat.py`)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from eval_shape import only

from my_agent_crew.memory.search import normalize

if TYPE_CHECKING:
    from eval_client import EvalApi

STEPS = ("create_canvas", "edit_canvas", "select_canvas")
CREATE_KEYS = ("title", "content", "kind")
EDIT_KEYS = ("old", "new")
KINDS = ("markdown", "code")
# A chat repeats a canvas when it has this many of its lines; one line is a quote.
COPY_LINES = 3
COPY_LINE_CHARS = 20  # a shorter line is a heading or a name, fine to say again
SERVER_TEXT_CHARS = 200
_MARKER = re.compile(r"^(?:\s*(?:#+|>|[-*+]|\d+[.)]))+\s*")
_EMPHASIS = re.compile(r"[*_`]+")


@dataclass(frozen=True)
class CanvasStep:
    action: str  # one of STEPS
    title: str = ""
    content: str = ""
    kind: str = "markdown"
    old: str = ""
    new: str = ""
    text: str = ""  # the passage select_canvas selects


@dataclass
class Panel:
    """The canvas open in the person's panel, and the passage selected in it."""

    artifact_id: str = ""
    selection: dict[str, Any] | None = None

    def open(self, artifact_id: str) -> None:
        if artifact_id != self.artifact_id:
            self.artifact_id, self.selection = artifact_id, None

    def carry(self) -> dict[str, Any]:
        """The next message's `canvas` field; none before a canvas is open, so the
        conversation keeps whatever it has open."""
        if not self.artifact_id:
            return {}
        sent = {"artifact_id": self.artifact_id, "selection": self.selection}
        self.selection = None
        return {"canvas": sent}


def parse_messages(raw: object, where: str) -> tuple[str | CanvasStep, ...]:
    """Messages to send and steps between them: at least one message, and a message after
    every selection to carry it."""
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{where}: messages must be a non-empty list of messages and steps")
    items: list[str | CanvasStep] = []
    for item in raw:
        if isinstance(item, Mapping):
            items.append(parse_step(item, where))
        elif isinstance(item, str) and item:
            items.append(item)
        else:
            raise ValueError(f"{where}: messages holds a message or a canvas step, not {item!r}")
    sent = [i for i, item in enumerate(items) if isinstance(item, str)]
    if not sent:
        raise ValueError(f"{where}: messages needs a message, not only canvas steps")
    if any(isinstance(item, CanvasStep) and item.text for item in items[sent[-1] :]):
        raise ValueError(f"{where}: select_canvas needs a message after it to carry the selection")
    return tuple(items)


def parse_step(raw: Mapping[str, Any], where: str) -> CanvasStep:
    """A step is a mapping with one key, its action, holding what the action needs."""
    if len(raw) != 1 or next(iter(raw)) not in STEPS:
        named = ", ".join(map(str, raw)) or "nothing"
        raise ValueError(
            f"{where}: a canvas step in messages is one of {', '.join(STEPS)}, not {named}"
            " (a message with ': ' in it needs quotes)"
        )
    ((action, args),) = raw.items()
    label = f"{where}: {action}"
    if action == "select_canvas":
        text = args.strip("\n") if isinstance(args, str) else ""
        if not text.strip():
            raise ValueError(f"{label} is the text of the passage to select")
        return CanvasStep(action, text=text)
    if not isinstance(args, Mapping):
        raise ValueError(f"{label} must be a mapping")
    if action == "create_canvas":
        only(args, CREATE_KEYS, label)
        title, content, kind = args.get("title"), args.get("content"), args.get("kind", KINDS[0])
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"{label} needs a title")
        if not isinstance(content, str):
            raise ValueError(f"{label} needs its content, as text")
        if kind not in KINDS:
            raise ValueError(f"{label}: kind is one of {', '.join(KINDS)}")
        return CanvasStep(action, title=title, content=content, kind=kind)
    only(args, EDIT_KEYS, label)
    old, new = args.get("old"), args.get("new")
    if not isinstance(old, str) or not old:
        raise ValueError(f"{label}: old is the text to replace")
    if not isinstance(new, str):
        raise ValueError(f"{label}: new is the text to put there, empty to delete it")
    return CanvasStep(action, old=old, new=new)


def perform(api: EvalApi, conv_id: str, step: CanvasStep, panel: Panel) -> str:
    """Does `step`: an empty string when it is done, else why the run cannot go on. A
    request the server refuses fails the run; a server that cannot be reached raises, as it
    does in a turn, and stops the eval."""
    try:
        if step.action == "create_canvas":
            made = api.create_artifact(conv_id, step.title, step.kind, step.content)
            panel.open(str(made["id"]))
            return ""
        target = panel.artifact_id or _newest(api, conv_id)
        if not target:
            return f"{step.action}: the conversation has no canvas"
        panel.open(target)
        canvas = api.artifact(target)
        content, version = str(canvas.get("content") or ""), int(canvas["head_version"])
        wanted = step.text or step.old
        if (times := content.count(wanted)) != 1:
            return f"{step.action}: {wanted!r} is in the canvas {times} times, not once"
        if step.action == "edit_canvas":
            api.save_artifact(target, content.replace(wanted, step.new), version)
        else:
            panel.selection = _pick(content, wanted, version)
        return ""
    except httpx.HTTPStatusError as exc:
        answer = exc.response.text[:SERVER_TEXT_CHARS]
        return f"{step.action}: the server answered {exc.response.status_code}: {answer}"


def copied_lines(said: str, contents: Sequence[str]) -> int:
    """How many distinct lines of the canvases, of `COPY_LINE_CHARS` or more, `said`
    repeats, whatever the markup, case and accents of either."""
    plain = _plain(said)
    lines = {_plain(_MARKER.sub("", line)) for text in contents for line in text.splitlines()}
    return sum(1 for line in lines if len(line) >= COPY_LINE_CHARS and line in plain)


def _plain(text: str) -> str:
    return " ".join(_EMPHASIS.sub("", normalize(text)).split())


def _newest(api: EvalApi, conv_id: str) -> str:
    linked = api.artifacts(conv_id)
    return str(linked[0]["id"]) if linked else ""


def _pick(content: str, text: str, version: int) -> dict[str, Any]:
    """The selection as the panel sends it: its lines count from 1, both ends included
    (`store/canvas_quote.py`)."""
    start = content.count("\n", 0, content.index(text)) + 1
    end = start + text.count("\n")
    return {"version": version, "text": text, "line_start": start, "line_end": end}
