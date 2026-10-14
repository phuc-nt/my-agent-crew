"""The owner's desktop as a person sees it from the web: what one agent may do with it and
what the helper says of the machine, a picture taken to try it, a picture as it was taken
for a person judging an action, and the one button that asks macOS for the helper's two
permissions.

Nothing here acts on the desktop: an agent's own call does that, through the gate. Asking
for the permissions is the only request that may put a system dialog on the owner's screen,
and it is sent from here alone, when a person presses for it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from my_agent_crew.desktop.client import DesktopError
from my_agent_crew.desktop.kit import said
from my_agent_crew.desktop.pictures import verified
from my_agent_crew.desktop.policy import FRAME_ID
from my_agent_crew.server import desktop_runtime as desktop
from my_agent_crew.server.agent_edit_common import existing
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.untrusted_content import SHOWN, untrusted_bytes
from my_agent_crew.tools.registry import ToolError

router = APIRouter(tags=["desktop"])


@router.get("/agents/{agent_id}/desktop")
async def read_desktop(agent_id: str, rt: Rt) -> dict[str, Any]:
    """Asks the helper for its state and nothing else. An agent the crew does not have is a
    404; a machine with no helper is told as one, never as an error."""
    own = existing(rt, agent_id).settings.desktop
    return {
        "mode": own.mode,
        "apps": list(own.apps),
        "machine": await desktop.machine(rt.settings),
    }


@router.post("/agents/{agent_id}/desktop/screenshot")
async def try_screenshot(agent_id: str, rt: Rt) -> dict[str, Any]:
    """One picture for a person, held to what the agent itself would be shown. The picture
    is a file of the agent's workspace, read as any other of its files."""
    profile = existing(rt, agent_id)
    try:
        return await desktop.try_screenshot(profile)
    except ToolError as error:
        # A refusal of the helper reaches a person in one line, its own words beside it.
        cause = error.__cause__
        told = said(cause) if isinstance(cause, DesktopError) else str(error)
        raise HTTPException(409, told) from error


@router.get("/agents/{agent_id}/desktop/pictures/{frame_id}")
def verified_picture(agent_id: str, frame_id: str, rt: Rt) -> Response:
    """The picture of a frame the way the screenshot tool took it, for the card that asks a
    person about an action on that frame. The agent may write in the folder the picture is
    in, so a picture it rewrote, or a link it put in its place, is none (404), as is a frame
    the tool did not take for this agent or no longer keeps."""
    existing(rt, agent_id)
    data = verified(agent_id, frame_id) if FRAME_ID.fullmatch(frame_id) else None
    if data is None:
        raise HTTPException(404, "no such picture")
    return untrusted_bytes(data, SHOWN[".png"], f"{frame_id}.png")


@router.post("/desktop/permissions")
async def ask_permissions(rt: Rt) -> dict[str, bool | None]:
    """What the helper holds once macOS was asked. A permission still false is the owner's
    to grant in System Settings: macOS shows each dialog once."""
    try:
        return await desktop.request_permissions(rt.settings)
    except DesktopError as error:
        raise HTTPException(409, said(error)) from error
