"""The files a page sends a browser of the crew: only the file a waiting call set off is
kept, every other one is stopped as it begins, and a file is measured while it comes. Here
against a browser that is told what to do; `test_browser_download_tool.py` has a real one."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest

from my_agent_crew import texts_browser_files as f
from my_agent_crew.browser import downloads as dl
from my_agent_crew.browser.downloads import FOLDER, Downloads, fresh
from my_agent_crew.tools.registry import ToolError


class Page:
    def __init__(self) -> None:
        self.heard: dict = {}

    def on(self, event: str, handler) -> None:
        self.heard[event] = handler

    def sends(self, path: Path | None = None, whole: bool = False) -> Sent:
        sent = Sent(self, path)
        if whole:
            sent.ends()  # here before anybody heard of it
        self.heard["download"](sent)
        return sent


class Context:
    def __init__(self, *pages: Page) -> None:
        self.pages, self.heard = list(pages), {}

    def on(self, event: str, handler) -> None:
        self.heard[event] = handler

    def opens(self) -> Page:
        page = Page()
        self.pages.append(page)
        self.heard["page"](page)
        return page


class Sent:
    """A file on its way: it ends when it is told to, or when it is stopped. As with a real
    browser, stopping takes away a file still on its way and does nothing to one that came
    whole; removing takes away one that came whole and refuses for one that did not."""

    def __init__(self, page: Page, path: Path | None = None) -> None:
        self.page, self.did = page, []
        self._path, self._failure, self._ended = path, None, asyncio.Event()
        # Shut by a test, either holds the file where it is: being stopped, or being removed.
        self.asked, self.stopping, self.removing = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.stopping.set()
        self.removing.set()

    def ends(self, failure: str | None = None) -> None:
        if not self._ended.is_set():
            self._failure = failure
            self._ended.set()

    async def failure(self) -> str | None:
        await self._ended.wait()
        return self._failure

    async def cancel(self) -> None:
        self.asked.set()
        await self.stopping.wait()
        self.did.append("cancel")
        if not self._ended.is_set() and self._path:
            self._path.unlink(missing_ok=True)
        self.ends("canceled")

    async def delete(self) -> None:
        await self.removing.wait()
        self.did.append("delete")
        if self._failure:
            raise RuntimeError(self._failure)
        if self._path:
            self._path.unlink(missing_ok=True)

    async def path(self) -> Path | None:
        return self._path


async def stopped(sent: Sent) -> bool:
    """Whether the file was stopped and removed, once whoever was to had the time."""
    for _ in range(5):
        await asyncio.sleep(0)
    return sent.did == ["cancel", "delete"]


@contextlib.asynccontextmanager
async def taken(downloads: Downloads, page: Page, path: Path | None = None):
    """A file the page sends while a caller waits for it: the one the caller is given."""
    async with downloads.expecting(lambda sent: True) as began:
        sent = page.sends(path)
        assert began.result() is sent
        yield sent


@pytest.fixture
def quick(monkeypatch):
    """A limit a test can fill, looked at often."""
    monkeypatch.setattr(dl, "LIMIT_BYTES", 1000)
    monkeypatch.setattr(dl, "POLL_SECONDS", 0.01)


def test_the_holding_folder_is_made_private_and_emptied_of_what_a_dead_browser_left(tmp_path):
    profile = tmp_path / "browser" / "coach"

    folder = fresh(profile)

    assert folder == profile / FOLDER and list(folder.iterdir()) == []
    assert [p.stat().st_mode & 0o777 for p in (profile, folder)] == [0o700, 0o700]
    (folder / "half-a-file").write_bytes(b"x" * 10)
    (folder / "sub").mkdir()
    (profile / "Cookies").write_bytes(b"kept")

    assert fresh(profile) == folder and list(folder.iterdir()) == []
    assert (profile / "Cookies").read_bytes() == b"kept"


async def test_a_file_nobody_waits_for_is_stopped_as_it_begins(tmp_path):
    first = Page()
    context = Context(first)
    Downloads(context, tmp_path)

    later = context.opens()

    assert await stopped(first.sends())
    assert await stopped(later.sends())  # a page opened since is watched as well


async def test_a_file_that_came_whole_before_it_could_be_stopped_is_taken_away(tmp_path):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)
    (tmp_path / "coming").write_bytes(b"x" * 10)
    (tmp_path / "whole").write_bytes(b"x" * 10)

    coming = page.sends(tmp_path / "coming")
    whole = page.sends(tmp_path / "whole", whole=True)

    assert await stopped(coming) and await stopped(whole)
    assert await coming.failure() == "canceled" and await whole.failure() is None
    assert downloads.held() == 0


async def test_only_the_first_file_the_caller_takes_for_its_own_is_given(tmp_path):
    mine, other = Page(), Page()
    downloads = Downloads(Context(mine, other), tmp_path)

    async with downloads.expecting(lambda sent: sent.page is mine) as began:
        theirs = other.sends()
        assert await stopped(theirs) and not began.done()
        first = mine.sends()
        assert began.done() and began.result() is first and first.did == []
        second = mine.sends()
        assert await stopped(second) and began.result() is first

    assert first.did == ["cancel", "delete"]  # the browser's copy goes, whatever came of it
    assert theirs.did == second.did == ["cancel", "delete"]


async def test_the_browser_s_copy_goes_when_the_caller_failed_too(tmp_path):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)

    with pytest.raises(ToolError, match="hỏng"):
        async with downloads.expecting(lambda sent: True):
            sent = page.sends()
            raise ToolError("hỏng")

    assert sent.did == ["cancel", "delete"]
    assert await stopped(page.sends())  # and nobody is waiting any more


async def test_a_file_that_begins_after_the_caller_gave_up_is_stopped(tmp_path):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)

    async with downloads.expecting(lambda sent: True) as began:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(began, 0.01)
        late = page.sends()
        assert await stopped(late)

    assert late.did == ["cancel", "delete"]


async def test_a_second_caller_is_told_at_once_and_comes_once_the_first_is_wholly_out(tmp_path):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)
    first = downloads.expecting(lambda sent: True)

    async def second() -> str:
        try:
            async with downloads.expecting(lambda sent: True):
                return "in"
        except ToolError as error:
            return str(error)

    began = await first.__aenter__()
    assert await second() == f.DOWNLOAD_BUSY
    sent = page.sends()
    assert began.result() is sent  # the first is still the one waiting
    sent.removing.clear()
    leaving = asyncio.ensure_future(first.__aexit__(None, None, None))
    await asyncio.sleep(0.01)

    # The first has its file and is taking the browser's copy away: not out yet.
    assert sent.did == ["cancel"] and await second() == f.DOWNLOAD_BUSY
    sent.removing.set()
    await leaving
    assert sent.did == ["cancel", "delete"] and await second() == "in"


@pytest.mark.parametrize("held_at", ["stopping", "removing"])
async def test_a_caller_stopped_again_on_its_way_out_still_has_the_browser_s_copy_removed(
    tmp_path, held_at
):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)
    (tmp_path / "whole").write_bytes(b"x" * 10)
    inside, files = asyncio.Event(), []

    async def caller() -> None:
        async with downloads.expecting(lambda sent: True):
            files.append(page.sends(tmp_path / "whole", whole=True))
            inside.set()
            await asyncio.Event().wait()  # for as long as nobody stops it

    async def next_caller() -> str:
        try:
            async with downloads.expecting(lambda sent: True):
                return "in"
        except ToolError as error:
            return str(error)

    calling = asyncio.ensure_future(caller())
    await inside.wait()
    (sent,) = files
    getattr(sent, held_at).clear()
    calling.cancel()  # stopped once: on its way out it takes the browser's copy away
    await sent.asked.wait()
    calling.cancel()  # and stopped again while it does
    with pytest.raises(asyncio.CancelledError):
        await calling

    meanwhile = (await next_caller(), downloads.held())
    getattr(sent, held_at).set()
    await stopped(sent)

    assert sent.did == ["cancel", "delete"] and downloads.held() == 0
    # While the caller was gone and the copy was not, nobody else came.
    assert meanwhile == (f.DOWNLOAD_BUSY, 10)
    assert await next_caller() == "in"


async def test_a_file_is_measured_while_it_comes_and_given_up_over_the_limit(tmp_path, quick):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)

    async with taken(downloads, page) as sent:
        (tmp_path / "coming").write_bytes(b"x" * 1001)
        with pytest.raises(ToolError) as error:
            await downloads.receive(sent, "e2", 60)
        assert sent.did == []  # still on its way when it was given up

    assert str(error.value) == f.DOWNLOAD_TOO_LARGE.format(ref="e2", limit=1000 / 1024 / 1024)
    assert sent.did == ["cancel", "delete"]


async def test_every_file_the_browser_holds_counts_toward_the_limit(tmp_path, quick):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)
    (tmp_path / "one").write_bytes(b"x" * 600)
    (tmp_path / "two").write_bytes(b"x" * 400)

    async with taken(downloads, page, tmp_path / "one") as whole:
        whole.ends()
        assert downloads.held() == 1000
        # At the limit is not over it.
        assert await downloads.receive(whole, "e2", 60) == tmp_path / "one"
        (tmp_path / "two").write_bytes(b"x" * 401)
        with pytest.raises(ToolError) as error:
            await downloads.receive(whole, "e2", 60)  # a file that came whole is measured too

    assert str(error.value) == f.DOWNLOAD_TOO_LARGE.format(ref="e2", limit=1000 / 1024 / 1024)


async def test_a_file_not_here_in_time_is_given_up(tmp_path, quick):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)

    async with taken(downloads, page) as sent:
        with pytest.raises(ToolError) as error:
            # Bounded here so a call that never gives up fails the test instead of hanging it.
            await asyncio.wait_for(downloads.receive(sent, "e7", 0), 5)
        assert sent.did == []

    assert str(error.value) == f.DOWNLOAD_SLOW.format(ref="e7", seconds=0)
    assert sent.did == ["cancel", "delete"]


async def test_a_file_the_browser_failed_on_says_why_in_one_short_line(tmp_path, quick):
    page = Page()
    downloads = Downloads(Context(page), tmp_path)

    async with taken(downloads, page) as sent:
        sent.ends("net::ERR_FAILED\n   at  somewhere " + "x" * 300)
        with pytest.raises(ToolError) as error:
            await downloads.receive(sent, "e3", 60)

    said = ("net::ERR_FAILED at somewhere " + "x" * 300)[: dl.ERROR_CHARS]
    assert str(error.value) == f.DOWNLOAD_FAILED.format(ref="e3", error=said)


async def test_a_holding_folder_that_went_away_holds_nothing(tmp_path):
    assert Downloads(Context(), tmp_path / "gone").held() == 0
