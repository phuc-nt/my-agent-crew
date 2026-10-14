"""Where the pictures of the screen are kept: a folder of the workspace the tool makes up,
each picture under the name of its frame, and only the newest of them.

The folder is judged before the helper is asked and again once it has answered, since a
picture may take the helper a while and the folder may be another by then; it is then
written to through no link (`browser/folder.py`), so nothing is written, and nothing is
removed, anywhere a link put there meanwhile leads."""

from __future__ import annotations

import contextlib
import os
import re
import stat
from pathlib import Path

from my_agent_crew.browser.folder import NEW, listed, reached, remove
from my_agent_crew.browser.saved import place
from my_agent_crew.desktop.kit import Kit
from my_agent_crew.desktop.policy import FRAME_ID
from my_agent_crew.texts_workspace import WORKSPACE_PRIVATE
from my_agent_crew.tools.private_paths import is_private
from my_agent_crew.tools.registry import ToolError

FOLDER = "desktop"
# How many of its own pictures the tool leaves in the folder.
KEPT = 40
# The names this tool gives: only files named so are ever removed.
OURS = re.compile(rf"{FRAME_ID.pattern}\.png\Z")


def judged(kit: Kit) -> str:
    """The folder the pictures go in, as the answer names it: judged where it really is."""
    folder, shown = place(kit.workspace, kit.write_paths, FOLDER)
    if is_private(folder):
        # An agent that works in the crew home: this folder there is the helper's own.
        raise ToolError(WORKSPACE_PRIVATE)
    return shown


def has(workspace: Path, shown: str, frame_id: str) -> bool:
    """Whether the picture of that frame is still in the folder: a file, not a link or a
    folder put in its place."""
    try:
        with reached(workspace, shown, make=False) as folder:
            found = os.stat(f"{frame_id}.png", dir_fd=folder, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(found.st_mode)


def save(workspace: Path, shown: str, frame_id: str, data: bytes) -> None:
    """Write the picture under its frame's name, and keep the folder from growing: the
    oldest of the tool's own pictures go, and nothing else in the folder is touched: a folder
    or a link under such a name is no picture, and is neither counted nor removed. The
    folder is opened once and through no link, and all of it is done under it."""
    name = f"{frame_id}.png"
    with reached(workspace, shown) as folder:
        # A frame is named after its pixels, so a file of that name is this picture or
        # something put in its place: it goes, and the picture is made new, never written
        # through a link.
        remove(folder, name)
        fd = os.open(name, NEW, 0o644, dir_fd=folder)
        try:
            with open(fd, "wb") as file:
                file.write(data)
        except BaseException:
            with contextlib.suppress(OSError):  # the failure that is told is the first one
                remove(folder, name)
            raise
        files = ((old, x) for old, x in listed(folder) if stat.S_ISREG(x.st_mode))
        mine = sorted((x.st_mtime_ns, old) for old, x in files if OURS.match(old) and old != name)
        for _at, old in mine[: max(0, len(mine) - (KEPT - 1))]:
            remove(folder, old)
