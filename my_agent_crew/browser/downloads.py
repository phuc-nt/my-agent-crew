"""The files a page sends a browser of the crew.

A browser keeps a file only while a call is waiting for one, and only the one that call set
off. Every other file a page starts sending is cancelled as it begins, so no page fills the
disk by itself or leaves anything behind. What is kept is held in a folder inside the agent's
profile, which no tool reads, until the tool that asked has seen it whole and under the size
it may have; when that tool is done the browser's own copy goes, whatever came of it. A small
file may be whole before the browser hears it is to stop, so a file is stopped and then
removed, never only stopped; and since a browser says a file stopped a moment before the half
of it is gone, the folder is emptied when a caller is done. That is work kept to the end: a
caller that is stopped, and stopped again on its way out, does not take it along."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from my_agent_crew import texts_browser_files as f
from my_agent_crew.tools.registry import ToolError

FOLDER = "crew-downloads"
# No file larger than this is kept. It is no setting.
LIMIT_BYTES = 50 * 1024 * 1024
# How often a file on its way is measured: it is stopped while it comes, not once it is here.
POLL_SECONDS = 0.25
ERROR_CHARS = 120


def fresh(profile: Path) -> Path:
    """The folder an agent's browser holds a file in until the tool that asked for it took
    it, emptied of whatever a browser that died left there."""
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder = profile / FOLDER
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(mode=0o700, exist_ok=True)
    return folder


async def _quietly(work: Any) -> None:
    try:
        await work
    except Exception:  # noqa: BLE001 - the page, or the whole browser, went away first
        pass


async def _drop(download: Any, emptied: Path | None = None) -> None:
    """Stop a file and take the browser's copy of it away. Stopping removes one still on its
    way; one that came whole first is only removed by being asked for that. A browser says a
    file stopped before it has taken the half of it away, so the end of a caller's turn
    empties the folder as well: nothing still in it then is anybody's."""
    await _quietly(download.cancel())
    await _quietly(download.delete())
    if emptied is not None:
        _empty(emptied)


def _empty(folder: Path) -> None:
    with contextlib.suppress(OSError):
        for entry in list(os.scandir(folder)):
            with contextlib.suppress(OSError):
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.path)
                else:
                    os.unlink(entry.path)


class Downloads:
    def __init__(self, context: Any, folder: Path) -> None:
        self.folder = folder
        self._wanted: tuple[asyncio.Future[Any], Callable[[Any], bool]] | None = None
        self._dropping: set[asyncio.Future[None]] = set()
        for page in context.pages:
            self._watch(page)
        context.on("page", self._watch)

    def _watch(self, page: Any) -> None:
        page.on("download", self._began)

    def _began(self, download: Any) -> None:
        wanted = self._wanted
        if wanted is not None and not wanted[0].done() and wanted[1](download):
            wanted[0].set_result(download)
            return
        self._dropped(download)

    def _dropped(self, download: Any, emptied: Path | None = None) -> asyncio.Future[None]:
        """The dropping of a file, held here until it is done: whoever waits for it may be
        stopped, and it goes on."""
        task = asyncio.ensure_future(_drop(download, emptied))
        self._dropping.add(task)
        task.add_done_callback(self._dropping.discard)
        return task

    def _free(self, _gone: Any = None) -> None:
        self._wanted = None

    @contextlib.asynccontextmanager
    async def expecting(self, mine: Callable[[Any], bool]) -> AsyncIterator[asyncio.Future[Any]]:
        """For as long as this is held, the first file that begins and that `mine` takes for
        the caller's own is kept, and given through the future. One caller a browser at a
        time: a second is told so at once, before it clicked anything, since two could not
        tell whose file a new window brought. On the way out the browser's copy of the file
        is stopped and removed, the folder emptied, and only then may the next caller come."""
        if self._wanted is not None:
            raise ToolError(f.DOWNLOAD_BUSY)
        began: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._wanted = (began, mine)
        try:
            yield began
        finally:
            if began.done() and not began.cancelled():
                gone = self._dropped(began.result(), emptied=self.folder)
                gone.add_done_callback(self._free)  # whether this caller is still here or not
                await asyncio.shield(gone)
            else:
                self._free()

    def held(self) -> int:
        """The bytes the browser holds for this agent now, files still on their way among
        them."""
        total = 0
        with contextlib.suppress(OSError):
            for entry in os.scandir(self.folder):
                with contextlib.suppress(OSError):
                    total += entry.stat(follow_symlinks=False).st_size
        return total

    async def receive(self, download: Any, ref: str, seconds: float) -> Path:
        """Where the browser holds the file once it is whole. A file that grows past the
        limit, or is not here after `seconds`, is given up while it is still coming."""
        loop = asyncio.get_running_loop()
        ended, deadline = asyncio.ensure_future(download.failure()), loop.time() + seconds
        limit = LIMIT_BYTES / 1024 / 1024
        try:
            while True:
                await asyncio.wait({ended}, timeout=POLL_SECONDS)
                # Measured each time round, the last one too: a file that came whole between
                # two looks is held to the limit like one still on its way.
                if self.held() > LIMIT_BYTES:
                    raise ToolError(f.DOWNLOAD_TOO_LARGE.format(ref=ref, limit=limit))
                if ended.done():
                    break
                if loop.time() >= deadline:
                    raise ToolError(f.DOWNLOAD_SLOW.format(ref=ref, seconds=round(seconds)))
            failure = ended.result()
            if failure:
                said = " ".join(str(failure).split())[:ERROR_CHARS]
                raise ToolError(f.DOWNLOAD_FAILED.format(ref=ref, error=said))
            return Path(await download.path())
        finally:
            ended.cancel()
