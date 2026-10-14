"""A picture of the machine's screen, as the tool takes it for an agent and as the owner's
"try a screenshot" takes it from the web.

Both go one way (`capture`), so what the owner sees on trying is what the agent would be
given. An agent given applications is shown the screen only while one of them is in front;
the picture is of the whole display all the same, so what stands beside that application is
in it. The file is named by the frame the helper named, in a folder the tool makes up, and
nothing that is not a whole PNG is ever saved (`pictures.py` keeps it). What a model read off
the picture stands between fence lines: a screen carries words from anywhere.
"""

from __future__ import annotations

import base64
import binascii
import struct
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts_desktop as t
from my_agent_crew import texts_desktop_tools as d
from my_agent_crew.browser.kit import one_line, schema, text_of
from my_agent_crew.desktop import kit as k
from my_agent_crew.desktop.kit import DesktopTool, Kit
from my_agent_crew.desktop.pictures import has, judged, save
from my_agent_crew.desktop.policy import FRAME_ID, frame_size
from my_agent_crew.desktop.report import answer, no_room, room, with_data
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.texts import IMAGE_EMPTY
from my_agent_crew.tools.image import MAX_IMAGE_BYTES, describe
from my_agent_crew.tools.registry import Tool, ToolError, ToolResult

# How a PNG starts (its signature, then the chunk that gives its size) and how it ends.
PNG, END = b"\x89PNG\r\n\x1a\n", b"IEND\xaeB`\x82"
HEAD = struct.Struct(">8sI4sII")


@dataclass(frozen=True)
class Shot:
    frame_id: str
    width: int
    height: int
    # Where the picture is, as an answer names it: a path inside the workspace.
    path: str
    # The picture itself; None when the screen is the one the caller already has.
    data: bytes | None = None


async def in_front(kit: Kit, outside: str) -> None:
    """An agent given applications sees the screen only while one of them is in front."""
    state = await kit.ask_helper("state")
    for code in ("locked", "display_asleep"):
        if state.get(code) is True:
            raise ToolError(t.HELPER_ERRORS[code])
    front = state.get("frontmost")
    front = front if isinstance(front, dict) else {}
    if not kit.allows(front.get("app"), front.get("bundle_id")):
        raise ToolError(outside)


def _size(answer: dict, key: str) -> int:
    value = answer.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ToolError(t.SHOT_BROKEN)
    return value


def _picture(answer: dict, size: tuple[int, int]) -> bytes:
    """The PNG the helper sent, or the refusal: a picture that does not start as one, does
    not end as one, or is not of the size the answer gives is not saved. Coordinates are
    counted in that size, so a picture of another would send every click astray."""
    sent = answer.get("png_base64")
    try:
        data = base64.b64decode(sent, validate=True) if isinstance(sent, str) else b""
    except (binascii.Error, ValueError) as exc:
        raise ToolError(t.SHOT_BROKEN) from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise ToolError(t.SHOT_TOO_LARGE.format(limit=MAX_IMAGE_BYTES / 1024 / 1024))
    if len(data) < HEAD.size or not data.endswith(END):
        raise ToolError(t.SHOT_BROKEN)
    signature, _, kind, *drawn = HEAD.unpack_from(data)
    if signature != PNG or kind != b"IHDR" or tuple(drawn) != size:
        raise ToolError(t.SHOT_BROKEN)
    return data


async def capture(kit: Kit, since: str = "") -> Shot:
    """One picture of the screen, saved. `since` is a frame the caller already has: while the
    screen is still that frame and its file is still there, no picture is sent again."""
    shown = judged(kit)
    held = since if since and has(kit.workspace, shown, since) else None
    if kit.apps:
        await in_front(kit, t.SHOT_OUTSIDE)
    answer = await kit.ask_helper("screenshot", since=held)
    if kit.apps:
        # The picture was taken a moment after the look: one taken of another application
        # that came to the front in between is dropped unsaved and undescribed.
        await in_front(kit, t.SHOT_MOVED)
    frame_id = answer.get("frame_id")
    if not isinstance(frame_id, str) or not FRAME_ID.fullmatch(frame_id):
        raise ToolError(t.SHOT_BROKEN)
    width, height = _size(answer, "width"), _size(answer, "height")
    if frame_size(frame_id) != (width, height):
        # A point is judged by the size its frame id names: it is the picture's or no use.
        raise ToolError(t.SHOT_BROKEN)
    if answer.get("unchanged") is True:
        if frame_id != held:
            raise ToolError(t.SHOT_BROKEN)
        return Shot(frame_id, width, height, f"{shown}/{frame_id}.png")
    data = _picture(answer, (width, height))
    # The helper took its time: the folder is judged again where it is now.
    shown = judged(kit)
    try:
        save(kit.workspace, shown, frame_id, data)
    except OSError as exc:
        said = exc.strerror or type(exc).__name__
        raise ToolError(t.SHOT_NOT_SAVED.format(error=said)) from exc
    return Shot(frame_id, width, height, f"{shown}/{frame_id}.png", data)


def build_screenshot(kit: Kit) -> Tool:
    async def run(args: dict[str, Any]) -> ToolResult | str:
        question = text_of(args, "question")
        # A question is about the picture, so the picture is taken and read even when the
        # screen has not changed.
        shot = await capture(kit, "" if question else kit.frames.get(kit.owner(), ""))
        kit.gave(shot.frame_id)
        told = {"path": shot.path, "frame_id": shot.frame_id}
        told |= {"width": shot.width, "height": shot.height}
        if shot.data is None:
            return t.SHOT_UNCHANGED.format(**told)
        saved = t.SHOT_SAVED.format(**told)
        if kit.vision is None:
            return "\n".join([saved, t.SHOT_NO_VISION])
        # Sized to fit: an answer the registry cut would lose its closing fence. Under a cap
        # with no room for any of what a model would read, no model is paid to read it.
        if not room(kit.limit, saved):
            return "\n".join([saved, no_room(kit.limit)])
        try:
            url = f"data:image/png;base64,{base64.b64encode(shot.data).decode('ascii')}"
            text, cost = await describe(kit.vision, url, question)
        except ProviderError as exc:
            # What a route answers when it fails may repeat what it was sent.
            why = t.VISION_SAID.format(error=one_line(str(exc), k.DETAIL_CHARS))
            return with_data(kit.limit, "\n".join([saved, t.SHOT_UNREAD]), why)
        output = answer(kit.limit, [saved], text or IMAGE_EMPTY)
        return ToolResult(ok=True, output=output, cost_usd=cost, metered=True)

    return DesktopTool(
        name=k.SCREENSHOT,
        description=d.SCREENSHOT_DESCRIPTION,
        parameters=schema((), question=("string", d.PARAM_QUESTION)),
        run=run,
        replay_safe=True,
    )
