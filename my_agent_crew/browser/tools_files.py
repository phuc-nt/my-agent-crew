"""What the two browser tools that leave a file in the workspace share: the folder a file
goes in, how much that folder may hold, and how a file that was kept is told.

Either file lands in a folder the tools make up, under a name cleaned down to plain letters
(`saved.py`) and said under the fence, as whatever a page had a say in is. The folder is
judged before anything is clicked or printed and walked to again, through no link, when the
file is written (`folder.py`)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from my_agent_crew import texts_browser_files as f
from my_agent_crew.browser.fence import with_data
from my_agent_crew.browser.folder import held_bytes, keep
from my_agent_crew.browser.kit import Kit
from my_agent_crew.browser.saved import place
from my_agent_crew.tools.registry import ToolError

FOLDER = "downloads"
MB, GB = 1024 * 1024, 1024**3
# What the folder may hold before it takes no new file. It is no setting: pages are many
# and a disk is one, and only a person decides what of the folder goes.
FOLDER_BYTES = GB


def size_said(size: int) -> str:
    return f.SIZE_MB.format(size=size / MB) if size >= MB else f.SIZE_KB.format(size=size / 1024)


async def room(kit: Kit, write_paths: Sequence[str]) -> str:
    """The folder a new file goes in, as the answer names it. Refused when a link leads it
    out of where the agent may write, or when it holds all it may already: asked before
    anything is clicked or printed, since a file with nowhere to go is not asked for."""
    shown = place(kit.workspace, write_paths, FOLDER)[1]
    if await asyncio.to_thread(held_bytes, kit.workspace, shown) >= FOLDER_BYTES:
        raise ToolError(f.FOLDER_FULL.format(folder=shown, limit=FOLDER_BYTES / GB))
    return shown


async def put(kit: Kit, shown: str, name: str, content: bytes | Path) -> tuple[str, int]:
    """The name the file has in the folder `shown` now, and its size."""
    return await asyncio.to_thread(keep, kit.workspace, shown, name, content)


def why(exc: OSError) -> str:
    return exc.strerror or type(exc).__name__


def kept(kit: Kit, said: str, folder: str, *chosen: str) -> str:
    """What a tool that kept a file answers: its own words, and fenced under them the lines
    a page had a say in. Under a cap with no room for those, where to look for the file."""
    missing = f.SAVED_UNNAMED.format(folder=folder)
    return with_data(kit.limit, said, "\n".join(chosen), missing=missing)
