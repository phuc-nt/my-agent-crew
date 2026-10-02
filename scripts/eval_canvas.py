"""Canvas steps in an eval case: what the person does on a canvas between two messages.

A case's `messages` may hold, between its messages, what the person does in the web panel. Each
step goes over the REST routes the panel uses (`server/routes_artifacts.py`), as the person:

- `create_canvas: {title, content, kind?}` makes a canvas in the conversation and opens it;
- `edit_canvas: {old, new}` replaces the one place `old` is in the open canvas and saves it on
  the version it read, as the editor does;
- `select_canvas: <text>` selects the one place the text is, for the next message to carry.

With no canvas open a step takes the conversation's most recently changed one, as the panel
would show it. Every message after a canvas is open carries it, and a selection goes with the
next message only, as a message from the web does (`server/routes_chat.py`). Each message also
records what its canvas note owes the agent, for `eval_note.py` to check."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
from eval_shape import only

if TYPE_CHECKING:
    from eval_client import EvalApi

STEPS = ("create_canvas", "edit_canvas", "select_canvas")
CREATE_KEYS = ("title", "content", "kind")
EDIT_KEYS = ("old", "new")
KINDS = ("markdown", "code")
SERVER_TEXT_CHARS = 200


@dataclass(frozen=True)
class CanvasStep:
    action: str  # one of STEPS
    title: str = ""
    content: str = ""
    kind: str = "markdown"
    old: str = ""
    new: str = ""
    text: str = ""  # the passage select_canvas selects


@dataclass(frozen=True)
class NoteDue:
    """What the canvas note of one message must tell: each canvas the person made or saved
    since the message before, at the version they left it, and the passage the message
    carries."""

    saved: Mapping[str, int] = field(default_factory=dict)
    passage: str = ""


@dataclass
class Panel:
    """The canvas open in the person's panel, the passage selected in it, the canvases the
    person made or saved since their last message, and what each message they sent owes."""

    artifact_id: str = ""
    selection: dict[str, Any] | None = None
    saved: dict[str, int] = field(default_factory=dict)
    due: list[NoteDue] = field(default_factory=list)

    def open(self, artifact_id: str) -> None:
        if artifact_id != self.artifact_id:
            self.artifact_id, self.selection = artifact_id, None

    def carry(self) -> dict[str, Any]:
        """The next message's `canvas` field; none before a canvas is open, so the
        conversation keeps whatever it has open. What that message's note owes joins `due`."""
        passage = str(self.selection["text"]) if self.selection else ""
        self.due.append(NoteDue(self.saved, passage))
        self.saved = {}
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
    if new == old:
        raise ValueError(f"{label}: new is the same as old, so the edit changes nothing")
    return CanvasStep(action, old=old, new=new)


def perform(api: EvalApi, conv_id: str, step: CanvasStep, panel: Panel) -> str:
    """Does `step`: an empty string when it is done, else why the run cannot go on. A
    request the server refuses fails the run; a server that cannot be reached raises, as it
    does in a turn, and stops the eval."""
    try:
        if step.action == "create_canvas":
            made = api.create_artifact(conv_id, step.title, step.kind, step.content)
            panel.open(str(made["id"]))
            panel.saved[panel.artifact_id] = int(made["head_version"])
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
            written = api.save_artifact(target, content.replace(wanted, step.new), version)
            panel.saved[target] = int(written["version"])
        else:
            panel.selection = _pick(content, wanted, version)
        return ""
    except httpx.HTTPStatusError as exc:
        answer = exc.response.text[:SERVER_TEXT_CHARS]
        return f"{step.action}: the server answered {exc.response.status_code}: {answer}"


def _newest(api: EvalApi, conv_id: str) -> str:
    linked = api.artifacts(conv_id)
    return str(linked[0]["id"]) if linked else ""


def _pick(content: str, text: str, version: int) -> dict[str, Any]:
    """The selection as the panel sends it: its lines count from 1, both ends included
    (`store/canvas_quote.py`)."""
    start = content.count("\n", 0, content.index(text)) + 1
    end = start + text.count("\n")
    return {"version": version, "text": text, "line_start": start, "line_end": end}
