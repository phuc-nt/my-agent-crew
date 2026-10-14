"""A `computer_act` call, read from its arguments alone: what the helper would be sent, or
the sentence the call is refused with. Whether it stops for a person is in `asking.py`.

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
from my_agent_crew.desktop import keys
from my_agent_crew.desktop.policy import (
    CONTROL,
    FRAME_ID,
    app_named,
    code_point,
    frame_size,
    spotlight_allowed,
    typed_refusal,
)
from my_agent_crew.desktop.seen import NAME_CHARS, TOKEN
from my_agent_crew.tools.registry import ToolError

CLICKS = ("click", "double_click", "right_click")
DRAG, SCROLL, TYPE, KEY = "drag", "scroll", "type", "key"
SET_VALUE, FOCUS_APP = "set_value", "focus_app"
KINDS = (*CLICKS, DRAG, SCROLL, TYPE, KEY, SET_VALUE, FOCUS_APP)
# The most characters the helper types in one go, and the most lines it scrolls.
MAX_TYPED, MAX_SCROLL = 2000, 50
# The most characters a field is set to. The helper names no limit of its own, but a request
# is one line of at most 64 KiB, and a character can take four bytes of it: one beyond the
# first plane. The control characters a request writes as escapes of six are refused.
MAX_SET = 8000


@dataclass(frozen=True)
class Act:
    kind: str
    app: str
    # What the helper is sent beside the command, and nothing a kind does not read.
    send: dict[str, Any] = field(default_factory=dict)
    # The element the call names: the helper's own ref for it, and the tag of the outline
    # the model read it in. For a click, and a field set when the call says it, the name the
    # model read beside it.
    ref: str = ""
    tag: str = ""
    name: str = ""
    text: str | None = None  # what is typed or set
    combo: keys.Combo | None = None

    @property
    def token(self) -> str:
        """The ref as the outline showed it, and as a sentence names it back."""
        return f"{self.ref}-{self.tag}"


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
        # A whole number is compared as it is: one too large for a float is just off.
        if not number or (isinstance(value, float) and not math.isfinite(value)) or value < 0:
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
    try:
        text.encode()
    except UnicodeEncodeError as exc:  # half of a pair, which no request can carry
        raise ToolError(ta.ACT_TEXT_BROKEN.format(kind=kind)) from exc
    if control := CONTROL.search(text):
        raise ToolError(ta.ACT_TEXT_CONTROL.format(kind=kind, code=code_point(control.group())))
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


def _ref(written: str) -> tuple[str, str]:
    """A ref as an outline shows it, taken apart: the helper's own ref, and the tag."""
    found = TOKEN.fullmatch(written)
    if found is None:
        raise ToolError(ta.ACT_REF_SHAPE.format(ref=one_line(written, NAME_CHARS)))
    return found.group(1), found.group(2)


def read_act(args: dict[str, Any], apps: Sequence[str]) -> Act:
    """The call as the helper would be sent it. Raises the sentence it is refused with."""
    kind, app, written = text_of(args, "kind"), text_of(args, "app"), text_of(args, "ref")
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
        if bool(written) == pointed:
            raise ToolError(ta.ACT_REF_OR_POINT.format(kind=kind))
        if not written:
            return Act(kind, app, send | _point(args, kind, frame_id, "x", "y"))
        ref, tag = _ref(written)
        return Act(kind, app, send | {"ref": ref}, ref=ref, tag=tag, name=text_of(args, "name"))
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
        if not written:
            raise ToolError(ta.ACT_NEEDS.format(kind=kind, what="ref"))
        ref, tag = _ref(written)
        sent = send | {"ref": ref, "text": text}
        return Act(kind, app, sent, ref=ref, tag=tag, name=text_of(args, "name"), text=text)
    if written:
        # The helper types into whatever holds the cursor, wherever the model thinks that
        # is: a text sent with a ref it does not go to would be judged by the wrong field.
        raise ToolError(ta.ACT_TYPE_REF)
    return Act(kind, app, send | {"text": text}, text=text)


def refusal(args: dict[str, Any], apps: Sequence[str]) -> str:
    """The sentence a call is refused with whatever a person would say, or ""."""
    try:
        read_act(args, apps)
    except ToolError as exc:
        return str(exc)
    return ""
