"""The owner's desktop as the server holds it: where the helper is looked for, what is closed
around its socket, the tools an agent's own file asks for, and what the owner's screens are
told of the machine.

Nothing here starts, installs or signals the helper: it is the owner's to install and to
permit, and the server only ever asks it over its socket. Whoever reaches that socket sees
the screen and types on the keyboard, so the folder it is in is closed to every file tool and
to every sandboxed command whether or not a helper ever runs (`tools/private_paths.py`,
`tools/shell_sandbox.py`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_desktop as t
from my_agent_crew.config_desktop import desktop_root, socket_path
from my_agent_crew.desktop.client import DesktopClient, DesktopError
from my_agent_crew.desktop.kit import Kit
from my_agent_crew.desktop.screenshot import capture
from my_agent_crew.desktop.tools import build_desktop_tools
from my_agent_crew.tools.private_paths import keep_private
from my_agent_crew.tools.registry import Tool, ToolError

if TYPE_CHECKING:
    from my_agent_crew.agents import AgentProfile
    from my_agent_crew.config import Settings

# How long the owner's screens wait for the helper: a page is not held up by one that hangs.
STATUS_SECONDS = 1.0
# What the helper says of the machine that the owner's screens show, each true, false or
# unknown (null): a helper that left one out is not guessed for.
SWITCHES = ("locked", "display_asleep", "screen_recording", "accessibility")
MACHINE_KEYS = ("version", "protocol", *SWITCHES)
VERSION_CHARS = 40


def desktop_private(settings: Settings) -> tuple[Path, ...]:
    """What no file tool and no sandboxed command goes into: the folder the helper keeps its
    socket in and, where the machine's file puts the socket elsewhere, that socket too. The
    folder such a socket is in is not closed with it: it may be one many things share."""
    root, path = desktop_root(settings.home), socket_path(settings.home, settings.desktop)
    # Judged where the path leads: one that climbs out of the folder with `..` is not in it.
    inside = Path(os.path.realpath(path)).is_relative_to(os.path.realpath(root))
    return (root,) if inside else (root, path)


def close_desktop(settings: Settings) -> None:
    for kept in desktop_private(settings):
        keep_private(kept)


def client_of(settings: Settings) -> DesktopClient:
    return DesktopClient(socket_path(settings.home, settings.desktop))


def desktop_tools_of(profile: AgentProfile, limit: int, vision: Any = None) -> list[Tool]:
    """The desktop tools the agent's own file asks for. They are built with or without a
    helper on the machine: each call looks for it, and says so when there is none."""
    return build_desktop_tools(
        client_of(profile.settings),
        profile.id,
        profile.settings.desktop,
        profile.workspace,
        limit,
        vision=vision,
        # One list of words stops a risky step for a person, in a page and on the desktop.
        ask_patterns=profile.settings.browser.ask_patterns,
        write_paths=profile.settings.write_paths,
    )


async def machine(settings: Settings) -> dict[str, Any]:
    """What the helper says of the machine, for the owner's screens. Never an error: with no
    helper, one that does not answer within a second or one whose answer cannot be read,
    `present` is false and the rest is unknown."""
    try:
        state = await client_of(settings).request("state", seconds=STATUS_SECONDS)
    except DesktopError:
        return {"present": False, **dict.fromkeys(MACHINE_KEYS)}
    version, protocol = state.get("version"), state.get("protocol")
    return {
        "present": True,
        "version": version[:VERSION_CHARS] if isinstance(version, str) else None,
        "protocol": protocol if type(protocol) is int else None,
        **{key: state[key] if isinstance(state.get(key), bool) else None for key in SWITCHES},
    }


async def try_screenshot(profile: AgentProfile) -> dict[str, Any]:
    """One picture of the screen for a person, taken the way the agent's own tool takes it and
    held to the same applications, so what the owner sees is what the agent would be given.
    It is nobody's frame: no agent's memory of what it was shown is touched, and no model
    reads the picture. A `ToolError` says, in one sentence, why there is none."""
    own = profile.settings
    if not own.desktop.on:
        raise ToolError(t.TRY_OFF)
    kit = Kit(
        client_of(own),
        profile.id,
        own.desktop,
        profile.workspace,
        own.tool_output_chars,
        write_paths=tuple(own.write_paths),
    )
    shot = await capture(kit)
    return {
        "frame_id": shot.frame_id,
        "path": shot.path,
        "width": shot.width,
        "height": shot.height,
    }


async def request_permissions(settings: Settings) -> dict[str, bool | None]:
    """Ask the helper to ask macOS for its two permissions: the one request that may put a
    system dialog on the owner's screen, sent only when the owner presses for it. What the
    helper holds afterwards, or a `DesktopError`."""
    answer = await client_of(settings).request("request_permissions")
    return {
        key: answer[key] if isinstance(answer.get(key), bool) else None
        for key in ("screen_recording", "accessibility")
    }
