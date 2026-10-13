"""A picture of the machine's screen, as the tool takes it for an agent and as the owner's
"try a screenshot" takes it from the web.

Both go one way (`capture`), so what the owner sees on trying is what the agent would be
given. An agent given applications is shown the screen only while one of them is in front;
the picture is of the whole display all the same, so what stands beside that application is
in it. The file is named by the frame the helper named, in a folder the tool makes up, and
nothing that is not a whole PNG is ever saved. What a model read off the picture stands
between fence lines: a screen carries words from anywhere.
"""

from __future__ import annotations

import base64
import binascii
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from my_agent_crew import texts_desktop as t
from my_agent_crew import texts_desktop_tools as d
from my_agent_crew.browser.kit import one_line, schema, text_of
from my_agent_crew.browser.screenshot import place
from my_agent_crew.desktop import kit as k
from my_agent_crew.desktop.kit import DesktopTool, Kit
from my_agent_crew.desktop.policy import FRAME_ID
from my_agent_crew.desktop.report import fenced, room
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.texts import IMAGE_EMPTY
from my_agent_crew.texts_workspace import WORKSPACE_PRIVATE
from my_agent_crew.tools.image import MAX_IMAGE_BYTES, describe
from my_agent_crew.tools.private_paths import is_private
from my_agent_crew.tools.registry import Tool, ToolError, ToolResult

FOLDER = "desktop"
# How many of its own pictures the tool leaves in the folder.
KEPT = 40
# How a PNG starts (its signature, then the chunk that gives its size) and how it ends.
PNG, END = b"\x89PNG\r\n\x1a\n", b"IEND\xaeB`\x82"
HEAD = struct.Struct(">8sI4sII")
# The names this tool gives: only files named so are ever removed.
OURS = re.compile(rf"{FRAME_ID.pattern}\.png\Z")


@dataclass(frozen=True)
class Shot:
    frame_id: str
    width: int
    height: int
    # Where the picture is, as an answer names it: a path inside the workspace.
    path: str
    # The picture itself; None when the screen is the one the caller already has.
    data: bytes | None = None


def file_of(folder: Path, frame_id: str) -> Path:
    return folder / f"{frame_id}.png"


def save(folder: Path, frame_id: str, data: bytes) -> Path:
    """Write the picture under its frame's name, and keep the folder from growing: the
    oldest of the tool's own pictures go, and nothing else in the folder is touched."""
    folder.mkdir(parents=True, exist_ok=True)
    path = file_of(folder, frame_id)
    # A frame is named after its pixels, so a file of that name is this picture or something
    # put in its place: it goes, and the picture is made new, never written through a link.
    path.unlink(missing_ok=True)
    with open(path, "xb") as file:
        file.write(data)
    others = sorted(
        (found for found in folder.iterdir() if OURS.match(found.name) and found != path),
        key=lambda found: (found.lstat().st_mtime_ns, found.name),
    )
    for old in others[: max(0, len(others) - (KEPT - 1))]:
        old.unlink(missing_ok=True)
    return path


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
    folder, shown = place(kit.workspace, kit.write_paths, FOLDER)
    if is_private(folder):
        # An agent that works in the crew home: this folder there is the helper's own.
        raise ToolError(WORKSPACE_PRIVATE)
    held = since if since and file_of(folder, since).is_file() else None
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
    path = f"{shown}/{frame_id}.png"
    if answer.get("unchanged") is True:
        if frame_id != held:
            raise ToolError(t.SHOT_BROKEN)
        return Shot(frame_id, width, height, path)
    data = _picture(answer, (width, height))
    try:
        save(folder, frame_id, data)
    except OSError as exc:
        said = exc.strerror or type(exc).__name__
        raise ToolError(t.SHOT_NOT_SAVED.format(error=said)) from exc
    return Shot(frame_id, width, height, path, data)


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
        try:
            url = f"data:image/png;base64,{base64.b64encode(shot.data).decode('ascii')}"
            text, cost = await describe(kit.vision, url, question)
        except ProviderError as exc:
            return "\n".join(
                [saved, t.SHOT_UNREAD.format(error=one_line(str(exc), k.DETAIL_CHARS))]
            )
        # Sized to fit: an answer the registry cut would lose its closing fence.
        output = "\n".join([saved, fenced((text or IMAGE_EMPTY)[: room(kit.limit, saved)])])
        return ToolResult(ok=True, output=output, cost_usd=cost, metered=True)

    return DesktopTool(
        name=k.SCREENSHOT,
        description=d.SCREENSHOT_DESCRIPTION,
        parameters=schema((), question=("string", d.PARAM_QUESTION)),
        run=run,
        replay_safe=True,
    )
