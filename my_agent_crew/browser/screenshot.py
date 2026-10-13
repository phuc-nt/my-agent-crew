"""The browser tool that takes a picture of a tab.

The picture is a file in the agent's workspace, in a folder and under a name the tool makes
up: nothing the model or the page says is part of either. When the machine has a route that
reads pictures, what that route says of the picture is given too. A picture of a page carries
the page's words, so what was read out of it stands between fence lines like the page itself."""

from __future__ import annotations

import itertools
import os
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_fence as f
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.fence import ERROR_CHARS, answer, room, with_data
from my_agent_crew.browser.kit import BrowserTool, Kit, one_line, text_of
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.texts import IMAGE_EMPTY, WORKSPACE_ESCAPE, WORKSPACE_WRITE_OUTSIDE
from my_agent_crew.tools.image import data_url, describe
from my_agent_crew.tools.registry import Tool, ToolError, ToolResult

FOLDER = "screenshots"
# A picture over this is taken again as a JPEG, and refused when that is over it too.
MAX_BYTES = 2 * 1024 * 1024
JPEG_QUALITY = 70
# How long the browser is given for one picture; a large page may need two.
SHOT_SECONDS = 15
# How many of its own pictures the tool leaves in the folder.
KEPT = 40
MIME = {"png": "image/png", "jpg": "image/jpeg"}
# The names this tool gives: only files named so are ever removed.
OURS = re.compile(r"\d{8}T\d{6}Z-[a-z0-9_-]+\.(png|jpg)\Z")


def now() -> datetime:
    return datetime.now(UTC)


async def take(page: Any, full: bool) -> tuple[bytes, str]:
    ms = SHOT_SECONDS * 1000
    data = await page.screenshot(type="png", full_page=full, timeout=ms)
    if len(data) <= MAX_BYTES:
        return data, "png"
    data = await page.screenshot(type="jpeg", quality=JPEG_QUALITY, full_page=full, timeout=ms)
    if len(data) <= MAX_BYTES:
        return data, "jpg"
    raise ToolError(t.SHOT_TOO_LARGE.format(limit=MAX_BYTES / 1024 / 1024))


def place(workspace: Path, write_paths: Sequence[str]) -> tuple[Path, str]:
    """The folder pictures go in, and that folder as the answer names it. An agent held to
    some folders keeps its pictures under the first of them: a picture of a page is personal
    data, and the rule that keeps such an agent's files out of the rest of a git repo holds
    for the files of this tool too. The folder is judged where it really is, so one that a
    link leads out of the workspace, or out of those folders, takes no picture."""
    base = Path(os.path.realpath(workspace))
    held = [Path(os.path.realpath(base / path)) for path in write_paths]
    folder = Path(os.path.realpath((held[0] if held else base) / FOLDER))
    if not folder.is_relative_to(base):
        raise ToolError(WORKSPACE_ESCAPE)
    if held and not any(folder.is_relative_to(path) for path in held):
        asked, paths = f"{write_paths[0]}/{FOLDER}", ", ".join(write_paths)
        raise ToolError(WORKSPACE_WRITE_OUTSIDE.format(paths=paths, path=asked))
    return folder, folder.relative_to(base).as_posix()


def save(folder: Path, label: str, data: bytes, kind: str) -> Path:
    """Write the picture under a name not taken yet, and keep the folder from growing: the
    oldest of the tool's own pictures go, and nothing else in the folder is touched."""
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{now():%Y%m%dT%H%M%SZ}-{label}"
    for n in itertools.count(1):
        path = folder / f"{stem}{f'-{n}' if n > 1 else ''}.{kind}"
        try:
            # Made new or not at all: never over a file, nor through a link, already there.
            with open(path, "xb") as file:
                file.write(data)
        except FileExistsError:
            continue
        break
    mine = sorted(
        (found for found in folder.iterdir() if OURS.match(found.name)),
        key=lambda found: (found.lstat().st_mtime_ns, found.name),
    )
    for old in mine[:-KEPT]:
        old.unlink(missing_ok=True)
    return path


def build_screenshot(kit: Kit, write_paths: Sequence[str] = ()) -> Tool:
    async def run(args: dict[str, Any]) -> ToolResult | str:
        full = k.flag(args, "full_page")
        seconds = 2 * SHOT_SECONDS + k.CALL_SECONDS
        async with kit.tab(text_of(args, "tab"), seconds=seconds) as (_session, tab):
            data, kind = await take(tab.page, full)
            label = tab.label
        # The tab is free again: reading a picture takes a model its time.
        folder, shown = place(kit.workspace, write_paths)
        try:
            path = save(folder, label, data, kind)
        except OSError as exc:
            said = exc.strerror or type(exc).__name__
            raise ToolError(t.SHOT_NOT_SAVED.format(error=said)) from exc
        saved = t.SHOT_SAVED.format(label=label, path=f"{shown}/{path.name}")
        if kit.vision is None:
            return "\n".join([saved, t.SHOT_NO_VISION])
        # Sized like a page: what was read out of a picture is the page's words. Under a
        # cap with no room for any of them, no model is paid to read it.
        most = room(kit.limit, saved)
        if not most:
            return "\n".join([saved, f.NO_ROOM.format(limit=kit.limit)])
        try:
            url = data_url(path, MIME[kind])
            text, cost = await describe(kit.vision, url, text_of(args, "question"))
        except ProviderError as exc:
            # What a route answers when it fails may repeat what it was sent.
            why = f.VISION_SAID.format(error=one_line(str(exc), ERROR_CHARS))
            return with_data(kit.limit, "\n".join([saved, t.SHOT_UNREAD]), why)
        output = answer(kit.limit, [saved], (text or IMAGE_EMPTY)[:most])
        return ToolResult(ok=True, output=output, cost_usd=cost, metered=True)

    return BrowserTool(
        name=k.SCREENSHOT,
        description=d.SCREENSHOT_DESCRIPTION,
        parameters=k.schema(
            (),
            tab=("string", d.PARAM_TAB),
            question=("string", d.PARAM_QUESTION),
            full_page=("boolean", d.PARAM_FULL_PAGE),
        ),
        run=run,
        replay_safe=True,
    )
