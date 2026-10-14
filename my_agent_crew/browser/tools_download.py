"""The browser tool that keeps the file a page sends when something on it is clicked.

A download is a click, so it is judged as `browser_act` judges one: the element has to be the
one the model was shown still, and a person is asked first for the same hosts and the same
words. The file kept is the first one the tab sends once the element passed and was clicked,
or a window that tab opened meanwhile does (`downloads.py`). A page may have sent that file
from anywhere, so the answer says the host it came from beside the host of the page."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_files as f
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser import act as a
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.act_page import current, guard, perform
from my_agent_crew.browser.kit import BrowserTool, Kit, text_of, timed_out
from my_agent_crew.browser.policy import host_allowed, host_of
from my_agent_crew.browser.saved import file_name, inert
from my_agent_crew.browser.tools_act import quoted, seen
from my_agent_crew.browser.tools_files import kept, put, room, size_said, why
from my_agent_crew.tools.registry import Tool, ToolError

CLICK, FALLBACK = "click", "download"
# How long the element is given to take the click, how long a file is given to begin after
# it, and the least, usual and most seconds it is given to arrive whole.
CLICK_SECONDS, BEGIN_SECONDS = 8, 15
DOWNLOAD_SECONDS = (5, 60, 300)


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


@contextlib.contextmanager
def in_time(ref: str) -> Iterator[None]:
    """A step of the click that ran out of its time says so as `browser_act` does."""
    try:
        yield
    except Exception as exc:
        if not timed_out(exc):
            raise
        raise ToolError(t.ACT_TIMEOUT.format(ref=ref, seconds=CLICK_SECONDS)) from exc


def build_download(kit: Kit, write_paths: Sequence[str] = ()) -> Tool:
    hosts = kit.settings.hosts

    def ask(args: dict[str, Any]) -> str | None:
        """Why this call stops for a person, None when it need not. It only reads."""
        ref, name = text_of(args, "ref"), text_of(args, "name")
        shown, url, host = seen(kit, text_of(args, "tab"))
        node = shown.nodes.get(ref) if shown else None
        if node is None:
            return None  # nothing will be clicked: the call refuses by itself
        said = quoted(name)
        if hosts and not host_allowed(host_of(url), hosts):
            return f.ASK_DOWNLOAD_OUTSIDE.format(name=said, host=host)
        word = a.word_for(kit.ask, CLICK, name, "", node)
        return f.ASK_DOWNLOAD_WORD.format(name=said, host=host, word=word) if word else None

    async def run(args: dict[str, Any]) -> str:
        asked = a.read({**args, "kind": CLICK}, kit.workspace)
        ref, wait = asked.ref, k.number(args, "timeout_s", *DOWNLOAD_SECONDS)
        save_as = text_of(args, "save_as")
        shown = await room(kit, write_paths)
        seconds = CLICK_SECONDS + BEGIN_SECONDS + wait + k.CALL_SECONDS
        async with kit.tab(text_of(args, "tab"), seconds=seconds, last=True) as (session, tab):
            target, node = await current(kit, tab, asked)
            page, host = tab.page, host_of(tab.shown.url) or "—"
            with in_time(ref):
                await guard(kit, page, target, asked, node.name, CLICK_SECONDS * 1000)
            # Listened for only now: a file the tab sent before the element passed is not it.
            async with from_tab(session, page) as began:
                with in_time(ref):
                    await perform(page, target, asked, CLICK_SECONDS * 1000)
                try:
                    download = await asyncio.wait_for(began, BEGIN_SECONDS)
                except TimeoutError as exc:
                    said = f.DOWNLOAD_NONE.format(ref=ref, seconds=BEGIN_SECONDS)
                    raise ToolError(said) from exc
                held = await session.downloads.receive(download, ref, wait)
                called = file_name(save_as or download.suggested_filename, FALLBACK)
                safe, sent = inert(called), host_of(download.url) or "—"
                try:
                    name, size = await put(kit, shown, safe, held)
                except OSError as exc:
                    raise ToolError(f.DOWNLOAD_NOT_SAVED.format(ref=ref, error=why(exc))) from exc
        said = f.DOWNLOAD_SAVED.format(ref=ref, folder=shown, size=size_said(size))
        if safe != called:
            said = "\n".join([said, f.SAVED_INERT])
        where = f.SAVED_AS.format(path=f"{shown}/{name}")
        hosts_said = (f.SAVED_FROM.format(host=host), f.SENT_FROM.format(host=sent))
        return kept(kit, said, shown, where, *hosts_said)

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
