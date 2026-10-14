"""The one desktop tool that does something to the machine.

Whether a person is asked first is read from the call's own arguments and the agent's file
(`asking.py`). Whether a call is refused outright is read from those (`act.py`) and, for a
call that names a ref, from the outline its conversation was last shown (`seen.py`). The
gate asks both questions several times for one call, also after a person answered; nothing
they read changes while a card waits, except that a newer outline makes a ref of the one
before refused. A call that can only be refused is let through the gate unasked and
refuses by itself, so nobody is shown a card whose yes would change nothing.

What an action did is not known here: the helper sends events and the application does what
it does with them. The answer says so, and the agent looks again.
"""

from __future__ import annotations

from typing import Any

from my_agent_crew import texts_desktop_act as ta
from my_agent_crew import texts_desktop_tools as d
from my_agent_crew.browser.kit import one_line, schema
from my_agent_crew.desktop import kit as k
from my_agent_crew.desktop.act import FOCUS_APP, read_act
from my_agent_crew.desktop.asking import ask_reason
from my_agent_crew.desktop.kit import DesktopTool, Kit
from my_agent_crew.desktop.seen import ref_refusal
from my_agent_crew.tools.registry import Tool, ToolError

SET, FOCUSED = "set", "focused"


def build_act(kit: Kit) -> Tool:
    def doomed(args: dict[str, Any]) -> bool:
        """A call the tool refuses whatever a person says: it goes straight to its refusal."""
        try:
            act = read_act(args, kit.apps)
        except ToolError:
            return True
        return bool(ref_refusal(act, kit.shown()))

    def ask(args: dict[str, Any]) -> str | None:
        return None if doomed(args) else ask_reason(args, kit.apps, kit.ask)

    async def run(args: dict[str, Any]) -> str:
        act = read_act(args, kit.apps)
        # Judged by what this conversation was last shown: the helper refuses a ref of an
        # older outline and a secure field too, and this refusal needs no helper to be right.
        shown = kit.shown()
        if refused := ref_refusal(act, shown):
            raise ToolError(refused)
        # A ref means an element only beside the name of the outline it was read in.
        named = {"outline": shown.outline} if act.ref and shown else {}
        answer = await kit.ask_helper("act", **act.send, **named)
        app, effect = one_line(act.app, k.NAME_CHARS), answer.get("effect")
        if act.kind == FOCUS_APP or effect == FOCUSED:
            done = ta.ACT_FOCUSED.format(app=app)
        elif effect == SET:
            done = ta.ACT_SET.format(ref=act.token, app=app)
        else:
            done = ta.ACT_POSTED.format(kind=act.kind, app=app)
        front = answer.get("frontmost")
        if isinstance(front, dict) and not kit.allows(front.get("app"), front.get("bundle_id")):
            # Told without its name: an application outside the list is never named.
            done = "\n".join([done, ta.ACT_FRONT_LEFT])
        return done

    return DesktopTool(
        name=k.ACT,
        description=d.ACT_DESCRIPTION,
        parameters=schema(
            ("kind", "app"),
            kind=("string", d.PARAM_KIND),
            app=("string", d.PARAM_APP),
            frame_id=("string", d.PARAM_FRAME),
            ref=("string", d.PARAM_REF),
            name=("string", d.PARAM_NAME),
            x=("number", d.PARAM_X),
            y=("number", d.PARAM_Y),
            to_x=("number", d.PARAM_TO_X),
            to_y=("number", d.PARAM_TO_Y),
            dx=("integer", d.PARAM_DX),
            dy=("integer", d.PARAM_DY),
            text=("string", d.PARAM_TEXT),
            keys=("string", d.PARAM_KEYS),
        ),
        run=run,
        requires_approval=True,
        ask_when=ask,
        allow_when=doomed,
    )
