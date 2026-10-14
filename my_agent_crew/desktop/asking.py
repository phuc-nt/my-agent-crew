"""Why a `computer_act` call waits for a person even in a conversation that runs on its own.

Read from the call's own arguments and the agent's file alone, like everything in `act.py`,
and from the outline the conversation was last shown, for the name of an element a ref
means. What an action does is known only where the call says it in words: a text that is
typed, a combination of keys, the name of the element a click names or a field is set in.
So a click on a point, a drag, and a key that presses whatever happens to be chosen wait for
a person: nothing in them says what is pressed. A double click waits too, whatever it names:
on a file or a program it opens it, and nothing in the call says what it opens.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.browser.kit import one_line
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.desktop import keys
from my_agent_crew.desktop.act import FOCUS_APP, SCROLL, TYPE, Act, read_act
from my_agent_crew.desktop.policy import shown_controls
from my_agent_crew.desktop.seen import NAME_CHARS, Shown
from my_agent_crew.tools.registry import ToolError

DOUBLE_CLICK = "double_click"


def shown_name(name: str) -> str:
    """A name the screen gave, as a sentence of this program quotes it: on one line, short,
    without the marks the sentence quotes it in, and with each control character written out,
    since none of them draws."""
    return one_line(shown_controls(name.replace("«", "").replace("»", "")), NAME_CHARS)


def _at(value: float) -> str:
    """A coordinate as a card shows it: to the hundredth, and whole when it is whole."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _element(act: Act, shown: Shown | None) -> str:
    """The name of the element a ref means: the outline's own where the conversation was
    shown it, else the one the call read beside it (held to the outline before it is sent)."""
    if shown is not None and act.ref in shown.named:
        return shown.named[act.ref]
    return act.name


def _text_reason(act: Act, app: str, field: str, ask: AskWords) -> str | None:
    """Why a text typed, or set in the field `field` names, waits: the agent's words in the
    text or in the field's name, or a line break typed."""
    text, name = act.text or "", shown_name(field) if act.ref else ""
    if word := ask.find(text):
        if name:
            return ta.ASK_SET_WORD.format(name=name, app=app, word=word)
        return ta.ASK_WORD.format(app=app, word=word)
    if act.ref and (word := ask.find(field)):
        return ta.ASK_SET_FIELD.format(name=name, app=app, word=word)
    # A line break typed is Enter pressed. A field that is set takes it as text.
    broken = act.kind == TYPE and ("\n" in text or "\r" in text)
    return ta.ASK_NEWLINE.format(app=app) if broken else None


def _double_reason(act: Act, app: str, element: str) -> str:
    if not act.ref:
        x, y = _at(act.send["x"]), _at(act.send["y"])
        return ta.ASK_DOUBLE_POINT.format(x=x, y=y, app=app)
    if name := shown_name(element):
        return ta.ASK_DOUBLE_NAMED.format(name=name, app=app)
    return ta.ASK_DOUBLE_REF.format(ref=act.token, app=app)


def ask_reason(
    args: dict[str, Any], apps: Sequence[str], ask: AskWords, shown: Shown | None = None
) -> str | None:
    """The reason a person reads on the approval card, or None for a call that goes like any
    other. A call that is refused anyway gives none: nobody is asked about it. `shown` is the
    outline the conversation was last shown, where the name of a ref's element is read."""
    try:
        act = read_act(args, apps)
    except ToolError:
        return None
    app = one_line(act.app, NAME_CHARS)
    if act.kind == FOCUS_APP:
        return ta.ASK_FOCUS.format(app=app)
    if act.combo is not None:
        if keys.presses(act.combo):
            return ta.ASK_CONFIRM.format(keys=act.combo.spelled, app=app)
        if keys.ordinary(act.combo):
            return None
        return ta.ASK_KEYS.format(keys=act.combo.spelled, app=app)
    element = _element(act, shown)
    if act.text is not None:
        return _text_reason(act, app, element, ask)
    if act.kind == SCROLL:
        return None
    if act.kind == DOUBLE_CLICK:
        return _double_reason(act, app, element)
    if not act.ref:
        x, y = _at(act.send["x"]), _at(act.send["y"])
        return ta.ASK_POINT.format(kind=act.kind, x=x, y=y, app=app)
    if word := ask.find(element):
        return ta.ASK_NAMED.format(kind=act.kind, name=shown_name(element), app=app, word=word)
    return None
