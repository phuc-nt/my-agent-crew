"""Why a `computer_act` call waits for a person even in a conversation that runs on its own.

Read from the call's own arguments and the agent's file alone, like everything in `act.py`.
What an action does is known only where the call says it in words: a text that is typed, a
combination of keys, the name of the element a click names. So a click on a point, a drag,
and a key that presses whatever happens to be chosen wait for a person: nothing in them says
what is pressed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.browser.kit import one_line
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.desktop import keys
from my_agent_crew.desktop.act import FOCUS_APP, SCROLL, TYPE, read_act
from my_agent_crew.desktop.seen import NAME_CHARS
from my_agent_crew.tools.registry import ToolError


def shown_name(name: str) -> str:
    """A name the screen gave, as a sentence of this program quotes it: on one line, short,
    and without the marks the sentence quotes it in."""
    return one_line(name.replace("«", "").replace("»", ""), NAME_CHARS)


def _at(value: float) -> str:
    """A coordinate as a card shows it: to the hundredth, and whole when it is whole."""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def ask_reason(args: dict[str, Any], apps: Sequence[str], ask: AskWords) -> str | None:
    """The reason a person reads on the approval card, or None for a call that goes like any
    other. A call that is refused anyway gives none: nobody is asked about it."""
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
    if act.text is not None:
        if word := ask.find(act.text):
            return ta.ASK_WORD.format(app=app, word=word)
        # A line break typed is Enter pressed. A field that is set takes it as text.
        broken = act.kind == TYPE and ("\n" in act.text or "\r" in act.text)
        return ta.ASK_NEWLINE.format(app=app) if broken else None
    if act.kind == SCROLL:
        return None
    if not act.ref:
        x, y = _at(act.send["x"]), _at(act.send["y"])
        return ta.ASK_POINT.format(kind=act.kind, x=x, y=y, app=app)
    if word := ask.find(act.name):
        name = shown_name(act.name)
        return ta.ASK_NAMED.format(kind=act.kind, name=name, app=app, word=word)
    return None
