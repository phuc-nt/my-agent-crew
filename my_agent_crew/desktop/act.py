"""A `computer_act` call, read from its arguments alone: what the helper would be sent, or
the sentence the call is refused with, and whether it stops for a person.

Everything here is decided before anybody is asked and without a word to the helper, so a
call that can only be refused never reaches an approval card, and what a person approved is
what is sent. The helper checks the same shapes again on its side; this side is stricter
where it differs (a frame id for every kind but `focus_app`), never looser.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew import texts_desktop as t
from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.browser.kit import one_line, text_of
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.desktop import keys
from my_agent_crew.desktop.policy import (
    FRAME_ID,
    app_named,
    frame_size,
    spotlight_allowed,
    typed_refusal,
)
from my_agent_crew.tools.registry import ToolError

CLICKS = ("click", "double_click", "right_click")
DRAG, SCROLL, TYPE, KEY = "drag", "scroll", "type", "key"
SET_VALUE, FOCUS_APP = "set_value", "focus_app"
KINDS = (*CLICKS, DRAG, SCROLL, TYPE, KEY, SET_VALUE, FOCUS_APP)
# The most characters the helper types in one go, and the most lines it scrolls.
MAX_TYPED, MAX_SCROLL = 2000, 50
# The most characters a field is set to. The helper names no limit of its own, but a request
# is one line of at most 64 KiB, and a character can take six bytes of it.
MAX_SET = 8000
NAME_CHARS = 80


@dataclass(frozen=True)
class Act:
    kind: str
    app: str
    # What the helper is sent beside the command, and nothing a kind does not read.
    send: dict[str, Any] = field(default_factory=dict)
    ref: str = ""  # the element a text goes to, when the call named one
    text: str | None = None  # what is typed or set
    combo: keys.Combo | None = None


def _point(args: dict[str, Any], kind: str, frame_id: str, *names: str) -> dict[str, float]:
    """Pixels of the picture the frame names. Its id says how large that picture is, so a
    point off it, which the helper can only refuse, is refused here."""
    width, height = frame_size(frame_id)
    found = {}
    for name in names:
        value = args.get(name)
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if value is None:
            raise ToolError(ta.ACT_NEEDS.format(kind=kind, what=name))
        if not number or not math.isfinite(value) or value < 0:
            raise ToolError(ta.ACT_NUMBER.format(kind=kind, what=name))
        if value >= (width if name.endswith("x") else height):
            off = ta.ACT_OUTSIDE.format(kind=kind, what=name, width=width, height=height)
            raise ToolError(off)
        found[name] = value
    return found


def _lines(args: dict[str, Any], name: str) -> int:
    value = args.get(name, 0)
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > MAX_SCROLL:
        raise ToolError(ta.ACT_WHOLE.format(what=name))
    return value


def _text(args: dict[str, Any], kind: str) -> str:
    text = args.get("text")
    if not isinstance(text, str) or (kind == TYPE and not text):
        raise ToolError(ta.ACT_NEEDS.format(kind=kind, what="text"))
    most = MAX_TYPED if kind == TYPE else MAX_SET
    if len(text) > most:
        raise ToolError(ta.ACT_TEXT_LONG.format(kind=kind, limit=most))
    if refusal := typed_refusal(text):
        raise ToolError(refusal)
    return text


def _combo(args: dict[str, Any], apps: Sequence[str]) -> keys.Combo:
    written = text_of(args, "keys")
    if not written:
        raise ToolError(ta.ACT_NEEDS.format(kind=KEY, what="keys"))
    combo = keys.parse(written)
    if combo is None:
        raise ToolError(ta.ACT_KEYS.format(keys=one_line(written, NAME_CHARS)))
    if keys.never_sent(combo, spotlight=True):
        raise ToolError(ta.ACT_KEYS_NEVER.format(keys=combo.spelled))
    if keys.never_sent(combo, spotlight_allowed(apps)):
        raise ToolError(ta.ACT_KEYS_SPOTLIGHT.format(keys=combo.spelled))
    return combo


def read_act(args: dict[str, Any], apps: Sequence[str]) -> Act:
    """The call as the helper would be sent it. Raises the sentence it is refused with."""
    kind, app, ref = text_of(args, "kind"), text_of(args, "app"), text_of(args, "ref")
    if kind not in KINDS:
        raise ToolError(ta.ACT_KIND.format(kind=one_line(kind, NAME_CHARS), kinds=", ".join(KINDS)))
    if not app:
        raise ToolError(ta.ACT_NO_APP)
    if not app_named(apps, app):
        listed = ", ".join(apps) or "—"
        raise ToolError(t.APP_OUTSIDE.format(app=one_line(app, NAME_CHARS), apps=listed))
    if kind == FOCUS_APP:
        return Act(kind, app, {"kind": kind, "app": app})
    frame_id = text_of(args, "frame_id")
    if not FRAME_ID.fullmatch(frame_id):
        raise ToolError(ta.ACT_NO_FRAME.format(kind=kind))
    send: dict[str, Any] = {"kind": kind, "app": app, "frame_id": frame_id}
    if kind in CLICKS:
        pointed = args.get("x") is not None or args.get("y") is not None
        if bool(ref) == pointed:
            raise ToolError(ta.ACT_REF_OR_POINT.format(kind=kind))
        send |= {"ref": ref} if ref else _point(args, kind, frame_id, "x", "y")
        return Act(kind, app, send)
    if kind == DRAG:
        return Act(kind, app, send | _point(args, kind, frame_id, "x", "y", "to_x", "to_y"))
    if kind == SCROLL:
        moved = {"dx": _lines(args, "dx"), "dy": _lines(args, "dy")}
        if not any(moved.values()):
            raise ToolError(ta.ACT_WHOLE.format(what="dx, dy"))
        return Act(kind, app, send | _point(args, kind, frame_id, "x", "y") | moved)
    if kind == KEY:
        combo = _combo(args, apps)
        return Act(kind, app, send | {"keys": combo.spelled}, combo=combo)
    text = _text(args, kind)
    if kind == SET_VALUE:
        if not ref:
            raise ToolError(ta.ACT_NEEDS.format(kind=kind, what="ref"))
        return Act(kind, app, send | {"ref": ref, "text": text}, ref=ref, text=text)
    # The helper types into whatever holds the cursor; a ref with `type` says where the
    # model thinks that is, and is judged here without being sent.
    return Act(kind, app, send | {"text": text}, ref=ref, text=text)


def refusal(args: dict[str, Any], apps: Sequence[str]) -> str:
    """The sentence a call is refused with whatever a person would say, or ""."""
    try:
        read_act(args, apps)
    except ToolError as exc:
        return str(exc)
    return ""


def ask_reason(args: dict[str, Any], apps: Sequence[str], ask: AskWords) -> str | None:
    """Why this call waits for a person even in a conversation that runs on its own. A call
    that is refused anyway gives none: nobody is asked about it."""
    try:
        act = read_act(args, apps)
    except ToolError:
        return None
    app = one_line(act.app, NAME_CHARS)
    if act.kind == FOCUS_APP:
        return ta.ASK_FOCUS.format(app=app)
    if act.combo is not None and not keys.ordinary(act.combo):
        return ta.ASK_KEYS.format(keys=act.combo.spelled, app=app)
    if act.text and (word := ask.find(act.text)):
        return ta.ASK_WORD.format(app=app, word=word)
    return None
