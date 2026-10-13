"""The two browser tools that leave a file in the workspace: the file a page sends when
something on it is clicked, and the page itself printed as a PDF.

Either file lands in a folder the tools make up, under a name cleaned down to plain letters
(`saved.py`). A download is a click, so it is judged as `browser_act` judges one: the element
has to be the one the model was shown still, and a person is asked first for the same hosts
and the same words. Only the file that click set off is kept (`downloads.py`): one the tab
itself sends, or a window that tab opened meanwhile does."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_files as f
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser import act as a
from my_agent_crew.browser import downloads as dl
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.act_page import NAME_CHARS, current, guard, perform
from my_agent_crew.browser.kit import BrowserTool, Kit, one_line, text_of, timed_out
from my_agent_crew.browser.policy import host_allowed, host_of
from my_agent_crew.browser.saved import file_name, keep, place
from my_agent_crew.browser.tools_act import seen
from my_agent_crew.tools.registry import Tool, ToolError

FOLDER = "downloads"
CLICK = "click"
# How long the element is given to take the click, how long a file is given to begin after
# it, and the least, usual and most seconds it is given to arrive whole.
CLICK_SECONDS, BEGIN_SECONDS = 8, 15
DOWNLOAD_SECONDS = (5, 60, 300)
# Printing has no limit of its own in the browser: the call's is the only one.
PDF_SECONDS = 30
MB = 1024 * 1024


def size_said(size: int) -> str:
    return f.SIZE_MB.format(size=size / MB) if size >= MB else f.SIZE_KB.format(size=size / 1024)


async def put(folder: Path, name: str, content: bytes | Path) -> tuple[Path, int]:
    """The file as it now stands in the workspace, and its size."""
    path = await asyncio.to_thread(keep, folder, name, content)
    return path, path.stat().st_size


def why(exc: OSError) -> str:
    return exc.strerror or type(exc).__name__


@contextlib.contextmanager
def heard(source: Any, event: str) -> Iterator[list[Any]]:
    """What `source` tells of `event` while this is held, in the order it came."""
    told: list[Any] = []

    def note(what: Any) -> None:
        told.append(what)

    source.on(event, note)
    try:
        yield told
    finally:
        source.remove_listener(event, note)


@contextlib.asynccontextmanager
async def from_tab(session: Any, page: Any) -> AsyncIterator[asyncio.Future[Any]]:
    """The first file this tab sends while this is held, or a window it opened meanwhile
    does. A window another tab opened is that tab's: its file is nobody's here."""
    with heard(page, "popup") as opened:

        def mine(sent: Any) -> bool:
            return sent.page is page or sent.page in opened

        async with session.downloads.expecting(mine) as began:
            yield began


def build_download(kit: Kit, write_paths: Sequence[str] = ()) -> Tool:
    hosts = kit.settings.hosts

    def ask(args: dict[str, Any]) -> str | None:
        """Why this call stops for a person, None when it need not. It only reads."""
        ref, name = text_of(args, "ref"), text_of(args, "name")
        shown, url, host = seen(kit, text_of(args, "tab"))
        node = shown.nodes.get(ref) if shown else None
        if node is None:
            return None  # nothing will be clicked: the call refuses by itself
        said = one_line(name, NAME_CHARS)
        if hosts and not host_allowed(host_of(url), hosts):
            return f.ASK_DOWNLOAD_OUTSIDE.format(name=said, host=host)
        word = a.word_for(kit.ask, CLICK, name, "", node)
        return f.ASK_DOWNLOAD_WORD.format(name=said, host=host, word=word) if word else None

    async def run(args: dict[str, Any]) -> str:
        asked = a.read({**args, "kind": CLICK}, kit.workspace)
        ref, wait = asked.ref, k.number(args, "timeout_s", *DOWNLOAD_SECONDS)
        # Before anything is clicked: a file with nowhere to go is not asked for.
        folder, shown = place(kit.workspace, write_paths, FOLDER)
        seconds = CLICK_SECONDS + BEGIN_SECONDS + wait + k.CALL_SECONDS
        async with kit.tab(text_of(args, "tab"), seconds=seconds, last=True) as (session, tab):
            target, node = await current(kit, tab, asked)
            page, host = tab.page, host_of(tab.shown.url) or "—"
            async with from_tab(session, page) as began:
                try:
                    await guard(kit, page, target, asked, node.name, CLICK_SECONDS * 1000)
                    await perform(page, target, asked, CLICK_SECONDS * 1000)
                except Exception as exc:
                    if not timed_out(exc):
                        raise
                    said = t.ACT_TIMEOUT.format(ref=ref, seconds=CLICK_SECONDS)
                    raise ToolError(said) from exc
                try:
                    download = await asyncio.wait_for(began, BEGIN_SECONDS)
                except TimeoutError as exc:
                    said = f.DOWNLOAD_NONE.format(ref=ref, seconds=BEGIN_SECONDS)
                    raise ToolError(said) from exc
                held = await session.downloads.receive(download, ref, wait)
                called = text_of(args, "save_as") or download.suggested_filename
                name = file_name(called, "download")
                try:
                    path, size = await put(folder, name, held)
                except OSError as exc:
                    raise ToolError(f.DOWNLOAD_NOT_SAVED.format(ref=ref, error=why(exc))) from exc
        where = f"{shown}/{path.name}"
        return f.DOWNLOAD_SAVED.format(ref=ref, host=host, path=where, size=size_said(size))

    return BrowserTool(
        name=k.DOWNLOAD,
        description=f.DOWNLOAD_DESCRIPTION,
        parameters=k.schema(
            ("ref", "name"),
            ref=("string", d.PARAM_REF),
            name=("string", d.PARAM_NAME),
            save_as=("string", f.PARAM_SAVE_AS),
            tab=("string", d.PARAM_ACT_TAB),
            timeout_s=("integer", f.PARAM_DOWNLOAD_TIMEOUT),
        ),
        run=run,
        requires_approval=True,
        ask_when=ask,
    )


def build_pdf(kit: Kit, write_paths: Sequence[str] = ()) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        folder, shown = place(kit.workspace, write_paths, FOLDER)
        seconds = PDF_SECONDS + k.CALL_SECONDS
        async with kit.tab(text_of(args, "tab"), seconds=seconds) as (_session, tab):
            title = await tab.page.title()
            data = await tab.page.pdf(format="A4", print_background=True)
            label = tab.label
        if len(data) > dl.LIMIT_BYTES:
            raise ToolError(f.PDF_TOO_LARGE.format(limit=dl.LIMIT_BYTES / MB))
        name = file_name(text_of(args, "save_as") or title, "page", "pdf")
        try:
            path, size = await put(folder, name, data)
        except OSError as exc:
            raise ToolError(f.PDF_NOT_SAVED.format(error=why(exc))) from exc
        where = f"{shown}/{path.name}"
        return f.PDF_SAVED.format(label=label, path=where, size=size_said(size))

    return BrowserTool(
        name=k.PDF,
        description=f.PDF_DESCRIPTION,
        parameters=k.schema(
            (),
            tab=("string", d.PARAM_TAB),
            save_as=("string", f.PARAM_PDF_SAVE_AS),
        ),
        run=run,
        replay_safe=True,
    )
