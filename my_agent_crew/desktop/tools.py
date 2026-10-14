"""The desktop tools one agent is given, and the two of them that only tell: what the
machine's screen is in a state for, and what one application is made of.

An agent whose file says `computer: on` gets all four whether or not a helper runs on the
machine; its `tools:` list neither brings one nor takes one away. An application outside the
agent's list is never named in an answer and never read: with a list, an answer tells of the
agent's own applications only, and says of any other no more than that one is in front.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from my_agent_crew import texts_desktop as t
from my_agent_crew import texts_desktop_tools as d
from my_agent_crew.browser.kit import one_line, schema, text_of
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.config_desktop import DesktopSettings
from my_agent_crew.desktop import kit as k
from my_agent_crew.desktop.client import BAD_ANSWER, DesktopClient, DesktopError
from my_agent_crew.desktop.kit import DesktopTool, Kit
from my_agent_crew.desktop.policy import app_named
from my_agent_crew.desktop.report import (
    APP_CHARS,
    TITLE_CHARS,
    answer,
    app_line,
    fenced,
    no_room,
    outline,
    room,
    words,
)
from my_agent_crew.desktop.screenshot import build_screenshot
from my_agent_crew.desktop.seen import OUTLINE, TAG, Shown
from my_agent_crew.desktop.tools_act import build_act
from my_agent_crew.tools.registry import Tool, ToolError

# What the helper calls its version is named outside the fence, so only in this shape.
VERSION = re.compile(r"[0-9][0-9A-Za-z.+-]{0,19}")
# What stops every look and every action, and what stops some: told in the helper's order.
STOPS = ("locked", "display_asleep")
PERMISSIONS = {
    "screen_recording": "permission_missing:screen",
    "accessibility": "permission_missing:accessibility",
}


def rows_of(answer: dict) -> list[dict]:
    listed = answer.get("apps")
    return [row for row in listed if isinstance(row, dict)] if isinstance(listed, list) else []


def named(kit: Kit, row: dict) -> bool:
    """Whether an answer may name this application: with a list, only the agent's own."""
    return not kit.apps or kit.allows(row.get("app"), row.get("bundle_id"))


def own_pids(kit: Kit, rows: list[dict]) -> set[int]:
    """The processes of the agent's own applications, as the helper lists them now."""
    return {
        row["pid"]
        for row in rows
        if type(row.get("pid")) is int and kit.allows(row.get("app"), row.get("bundle_id"))
    }


async def _running(kit: Kit) -> list[dict] | None:
    """The applications that are open; None when the helper would not say."""
    try:
        return rows_of(await kit.client.request("apps"))
    except DesktopError:
        return None  # what `state` said still stands


def build_state(kit: Kit) -> Tool:
    async def run(_args: dict[str, Any]) -> str:
        state = await kit.ask_helper("state")
        version = state.get("version")
        version = version if isinstance(version, str) and VERSION.fullmatch(version) else "?"
        said = [t.STATE_HELPER.format(version=version)]
        stopped = [t.HELPER_ERRORS[code] for code in STOPS if state.get(code) is True]
        stopped += [t.HELPER_ERRORS[c] for key, c in PERMISSIONS.items() if state.get(key) is False]
        if not stopped and not state.get("displays"):
            stopped.append(t.STATE_NO_DISPLAY)
        said += stopped or [t.STATE_CLEAR]
        if state.get("secure_input") is True:
            said.append(t.STATE_SECURE_INPUT)
        said.append(t.STATE_APPS_MINE.format(apps=kit.listed()) if kit.apps else t.STATE_APPS_ALL)
        seen: list[str] = []
        front = state.get("frontmost")
        if not isinstance(front, dict):
            said.append(t.STATE_FRONT_NONE)
        elif named(kit, front):
            seen.append(t.STATE_FRONT.format(app=app_line(front)))
        else:
            said.append(t.STATE_FRONT_OUTSIDE)
        open_now = None if any(state.get(code) is True for code in STOPS) else await _running(kit)
        if open_now is not None:
            names = [app_line(row) for row in open_now if named(kit, row)]
            if names:
                seen.append(t.STATE_RUNNING.format(apps=", ".join(names)))
            else:
                said.append(t.STATE_NONE_RUNNING)
        return answer(kit.limit, said, "\n".join(seen)) if seen else "\n".join(said)

    return DesktopTool(
        name=k.STATE,
        description=d.STATE_DESCRIPTION,
        parameters=schema(()),
        run=run,
        replay_safe=True,
    )


def build_observe(kit: Kit) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        wanted = text_of(args, "app")
        if not kit.apps:
            raise ToolError(t.OBSERVE_NO_APPS)
        if wanted and not app_named(kit.apps, wanted):
            shown = one_line(wanted, k.NAME_CHARS)
            raise ToolError(t.APP_OUTSIDE.format(app=shown, apps=kit.listed()))
        open_now = rows_of(await kit.ask_helper("apps"))
        mine = own_pids(kit, open_now)
        front_outside = t.OBSERVE_FRONT_OUTSIDE.format(apps=kit.listed())
        in_front = (row.get("pid") for row in open_now if row.get("frontmost") is True)
        if not wanted and not any(pid in mine for pid in in_front):
            raise ToolError(front_outside)
        tree = await kit.ask_helper("ax", app=wanted or None)
        # The refs of the outline before are dead at the helper from here on, whoever
        # read it.
        kit.showed(None)
        found = tree.get("pid")
        if type(found) is not int or found not in mine:
            # The helper found another application than the list means: nothing of it is told.
            raise ToolError(t.OBSERVE_OTHER if wanted else front_outside)
        name = tree.get("outline")
        if not isinstance(name, str) or not OUTLINE.fullmatch(name):
            # Without its name no ref of this outline could be acted on.
            raise k.refused(kit.limit, DesktopError(BAD_ANSWER, ""))
        head = [t.OBSERVE_APP.format(app=words(tree.get("app"), APP_CHARS))]
        if title := words(tree.get("window"), TITLE_CHARS):
            head.append(t.OBSERVE_WINDOW.format(title=title))
        most = room(kit.limit, t.OBSERVE_HEAD, *head)
        if not most:
            # Nothing of the outline is told, so none of its refs can be acted on.
            return no_room(kit.limit)
        drawn = outline(tree.get("nodes"), most, name[:TAG])
        kit.showed(Shown(name, drawn.named, drawn.secure))
        said = [t.OBSERVE_HEAD.format(shown=drawn.shown)]
        said.append(fenced("\n".join([*head, drawn.text or t.OBSERVE_EMPTY])))
        if drawn.shown < drawn.total:
            said.append(t.OBSERVE_CUT.format(shown=drawn.shown, total=drawn.total))
        if tree.get("truncated") is True:
            said.append(t.OBSERVE_TRUNCATED)
        return "\n".join(said)

    return DesktopTool(
        name=k.OBSERVE,
        description=d.OBSERVE_DESCRIPTION,
        parameters=schema((), app=("string", d.PARAM_OBSERVE_APP)),
        run=run,
        replay_safe=True,
    )


def build_desktop_tools(
    client: DesktopClient,
    agent_id: str,
    settings: DesktopSettings,
    workspace: Path,
    limit: int,
    *,
    vision: Any = None,
    ask_patterns: Sequence[str] = (),
    write_paths: Sequence[str] = (),
) -> list[Tool]:
    """`settings` are the agent's own; `limit` is what its registry cuts an answer at;
    `vision` the chain its pictures are read by, when the machine has one; `ask_patterns` the
    agent's words that stop a typed text for a person; `write_paths` the folders its files
    are held to. None for an agent whose file leaves the desktop off."""
    if not settings.on:
        return []
    ask, held = AskWords(tuple(ask_patterns)), tuple(write_paths)
    kit = Kit(client, agent_id, settings, workspace, limit, vision, ask, held)
    return [build_state(kit), build_screenshot(kit), build_observe(kit), build_act(kit)]
