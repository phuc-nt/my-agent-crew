"""`browser_download` against a real Chromium: a click on the element the model was shown, and
the one file that click set off, under a cleaned name in a folder of the tool's own. No other
file a page sends is ever kept, and none past the size a file may have."""

from __future__ import annotations

import asyncio
import os
import time

import pytest
import pytest_asyncio
from playwright.async_api import Download

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_files as f
from my_agent_crew.browser import downloads as dl
from my_agent_crew.browser import kit as k
from my_agent_crew.browser import tools_files
from my_agent_crew.browser.navigate import build_navigate
from my_agent_crew.browser.tools_act import build_act
from my_agent_crew.browser.tools_files import FOLDER, build_download, heard
from my_agent_crew.texts import WORKSPACE_ESCAPE
from my_agent_crew.tools.registry import ToolError
from tests.browser_tools import ref_of, talking, world

pytestmark = pytest.mark.asyncio(loop_scope="module")

LOG = (
    "<p id=log></p>"
    "<script>function log(x) { document.getElementById('log').textContent += x + ';' }</script>"
)
FILE, OTHER = "%PDF-1.4 " + "x" * 3000, "tep cua tab khac " * 40
# A name with accents, as a site sends one: the plain one is for a browser that reads no other.
NAMED = (
    'attachment; filename="plain.pdf"; '
    "filename*=UTF-8''ho%C3%A1%20%C4%91%C6%A1n%20th%C3%A1ng%2010.pdf"
)
HOME = (
    "<title>Hoá đơn</title>"
    '<a href="/hd">Tải hoá đơn</a>'
    '<a href="/hd" target="_blank">Mở cửa sổ tải</a>'
    '<a href="/hd">Xoá hoá đơn</a>'
    '<a href="/hd" aria-label="Biên lai">Xoá bản cũ</a>'
    '<a href="/dut">Tệp đứt</a>'
    '<a href="/ten">Tên lạ</a>'
    '<a href="/lon">Tệp lớn</a>'
    '<a href="/cham">Tệp chậm</a>'
    "<button onclick=\"log('sau'); setTimeout(() => location.href = '/hd', 1500)\">"
    "Tải sau</button>"
    "<button onclick=\"window.open('/cua-so')\">Mở trang tải</button>"
    "<button onclick=\"log('bấm')\">Không tải gì</button>" + LOG
)


def sends(body, disposition: str = "attachment", **headers):
    head = {"content-type": "application/octet-stream", "content-disposition": disposition}
    return lambda _site: (200, {**head, **headers}, body)


PAGES = {
    "/": HOME,
    "/hd": sends(FILE, NAMED, **{"content-type": "application/pdf"}),
    "/tep-khac": sends(OTHER, 'attachment; filename="khac.txt"'),
    # Less comes than was promised: the connection ends first.
    "/dut": sends(["x" * 1000, 0.2, "y" * 1000], **{"content-length": "500000"}),
    "/ten": sends("k" * 2000, 'attachment; filename="../../.ssh/authorized_keys"'),
    # Twelve seconds to come whole, a piece at a time.
    "/lon": sends(["a" * 40_000, 0.3] * 40),
    "/cham": sends(["a" * 100, 0.5] * 24),
    "/tu-tai": "<title>Tự tải</title><p>Trang tự tải</p>"
    "<script>setTimeout(() => location.href = '/hd', 200)</script>",
    "/khac": "<title>Khác</title><p>Trang khác</p>",
    # A window that is a page of its own before it sends a file.
    "/cua-so": "<title>Cửa sổ</title><p>Tệp sẽ tải ngay</p>"
    "<script>setTimeout(() => location.href = '/hd', 300)</script>",
    "/cua-so-khac": "<title>Cửa sổ khác</title><p>Tệp khác sẽ tải ngay</p>"
    "<script>setTimeout(() => location.href = '/tep-khac', 300)</script>",
}


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def w(tmp_path_factory):
    async with world(tmp_path_factory.mktemp("down"), PAGES, max_tabs=40) as made:
        yield made


@pytest.fixture(autouse=True)
def emptied(w):
    """A workspace each test finds as the first did."""
    yield
    for left in sorted(w.workspace.rglob("*"), reverse=True):
        left.rmdir() if left.is_dir() and not left.is_symlink() else left.unlink()


async def opened(w, path: str = "/", **how) -> str:
    return await build_navigate(w.kit()).run({"url": w.site.url(path), **how})


async def down(w, ref: str, name: str, kit=None, paths=(), **more) -> str:
    tool = build_download(kit or w.kit(), paths)
    return await tool.run({"ref": ref, "name": name, **more})


async def refused(w, ref: str, name: str, **more) -> str:
    with pytest.raises(ToolError) as error:
        await down(w, ref, name, **more)
    return str(error.value)


def why(w, ref: str, name: str, kit=None, **more) -> str | None:
    """What the gate is told about a call: the reason it stops for a person, or None."""
    return build_download(kit or w.kit()).ask_when({"ref": ref, "name": name, **more})


def saved(w, *under: str) -> dict[str, bytes]:
    """The files the tool left, by name."""
    folder = w.workspace.joinpath(*under, FOLDER)
    return {p.name: p.read_bytes() for p in folder.iterdir()} if folder.is_dir() else {}


def held(w) -> list[str]:
    """What the agent's browser still holds of the files pages sent it."""
    return [p.name for p in w.pool.running("coach").downloads.folder.iterdir()]


def told(ref: str, name: str, size: str, host: str = "127.0.0.1") -> str:
    return f.DOWNLOAD_SAVED.format(ref=ref, host=host, path=f"{FOLDER}/{name}", size=size)


async def until(what, seconds: float = 10.0) -> None:
    """Wait for something that is on its way; a test that asks in vain fails here."""
    end = time.monotonic() + seconds
    while not what():
        assert time.monotonic() < end, "it never came"
        await asyncio.sleep(0.05)


async def logged(tab) -> str:
    return await tab.page.inner_text("#log")


async def test_the_tool_is_an_action_a_person_is_asked_about_as_for_a_click(w):
    tool = build_download(w.kit("nobody"))

    assert (tool.name, tool.requires_approval) == (k.DOWNLOAD, True)
    assert (tool.replay_safe, tool.parallel) == (False, False)
    assert tool.ask_when is not None and tool.allow_when is None and tool.ask_reason is None
    assert tool.parameters["required"] == ["ref", "name"]
    assert set(tool.parameters["properties"]) == {"ref", "name", "save_as", "tab", "timeout_s"}
    assert tool.to_dict()["with_browser"] is True


@talking("down-one")
async def test_a_click_saves_the_one_file_it_set_off_under_a_cleaned_name(w):
    ref = ref_of(await opened(w), "Tải hoá đơn")
    tab = w.tab("down-one")

    out = await down(w, ref, "Tải hoá đơn")

    assert out == told(ref, "hoa-don-thang-10.pdf", "2.9 KB")
    assert saved(w) == {"hoa-don-thang-10.pdf": FILE.encode()}
    assert held(w) == []  # the browser's own copy is gone
    assert tab.page.url == w.site.url("/")
    assert [x.label for x in w.pool.running("coach").tabs.of("down-one")] == [tab.label]


@talking("down-names")
async def test_a_name_that_is_taken_gets_a_number_and_the_model_may_name_the_file(w):
    ref = ref_of(await opened(w), "Tải hoá đơn")

    first = await down(w, ref, "Tải hoá đơn")
    second = await down(w, ref, "Tải hoá đơn")
    third = await down(w, ref, "Tải hoá đơn", save_as="../a/Hoá đơn  Đà Nẵng.PDF")

    assert first == told(ref, "hoa-don-thang-10.pdf", "2.9 KB")
    assert second == told(ref, "hoa-don-thang-10-2.pdf", "2.9 KB")
    assert third == told(ref, "Hoa-don-Da-Nang.PDF", "2.9 KB")
    assert saved(w) == dict.fromkeys(
        ("hoa-don-thang-10.pdf", "hoa-don-thang-10-2.pdf", "Hoa-don-Da-Nang.PDF"), FILE.encode()
    )
    assert sorted(p.name for p in w.workspace.iterdir()) == [FOLDER]


@talking("down-blank")
async def test_a_file_a_window_opened_by_the_click_brings_is_taken(w):
    ref = ref_of(await opened(w), "Mở cửa sổ tải")

    out = await down(w, ref, "Mở cửa sổ tải")

    assert out == told(ref, "hoa-don-thang-10.pdf", "2.9 KB")
    assert saved(w) == {"hoa-don-thang-10.pdf": FILE.encode()} and held(w) == []
    assert len(w.pool.running("coach").tabs.of("down-blank")) == 1  # the window left no tab


@talking("down-window")
async def test_a_file_a_page_the_click_opened_sends_a_while_later_is_taken(w):
    ref = ref_of(await opened(w), "Mở trang tải")

    out = await down(w, ref, "Mở trang tải")

    assert out == told(ref, "hoa-don-thang-10.pdf", "2.9 KB")
    assert saved(w) == {"hoa-don-thang-10.pdf": FILE.encode()} and held(w) == []
    # The window was a page before it sent anything: it is the conversation's next tab.
    tabs = w.pool.running("coach").tabs.of("down-window")
    assert sorted(tab.page.url for tab in tabs) == [w.site.url("/"), w.site.url("/cua-so")]


@talking("down-later")
async def test_a_file_that_begins_a_while_after_the_click_is_taken(w):
    ref = ref_of(await opened(w), "Tải sau")

    out = await down(w, ref, "Tải sau")

    assert out == told(ref, "hoa-don-thang-10.pdf", "2.9 KB")
    assert await logged(w.tab("down-later")) == "sau;"


@talking("down-site-name")
async def test_a_site_names_no_file_out_of_the_folder(w):
    ref = ref_of(await opened(w), "Tên lạ")

    out = await down(w, ref, "Tên lạ")

    (name,) = saved(w)
    assert out == told(ref, name, "2.0 KB") and saved(w) == {name: b"k" * 2000}
    assert name.endswith("authorized_keys") and not name.startswith((".", "-"))
    assert sorted(p.name for p in w.workspace.iterdir()) == [FOLDER]


@talking("down-none")
async def test_a_click_that_brings_no_file_says_the_click_was_made(w, monkeypatch):
    monkeypatch.setattr(tools_files, "BEGIN_SECONDS", 1)
    ref = ref_of(await opened(w), "Không tải gì")
    began = time.monotonic()

    assert await refused(w, ref, "Không tải gì") == f.DOWNLOAD_NONE.format(ref=ref, seconds=1)
    assert time.monotonic() - began < 10  # it waited the second it says, not many times that
    assert await logged(w.tab("down-none")) == "bấm;"
    assert saved(w) == {} and held(w) == []


@talking("down-big")
async def test_a_file_over_the_limit_is_stopped_while_it_comes_and_nothing_is_kept(w, monkeypatch):
    monkeypatch.setattr(dl, "LIMIT_BYTES", 100_000)
    ref = ref_of(await opened(w), "Tệp lớn")

    said = await refused(w, ref, "Tệp lớn")

    assert said == f.DOWNLOAD_TOO_LARGE.format(ref=ref, limit=100_000 / 1024 / 1024)
    assert saved(w) == {} and held(w) == []
    # The browser hung up on the site long before the file had come whole.
    await until(lambda: "/lon" in w.site.cut)


@talking("down-slow")
async def test_a_file_that_is_not_here_in_time_is_given_up_and_nothing_is_kept(w, monkeypatch):
    monkeypatch.setattr(tools_files, "DOWNLOAD_SECONDS", (1, 1, 1))
    ref = ref_of(await opened(w), "Tệp chậm")

    said = await refused(w, ref, "Tệp chậm", timeout_s=300)

    assert said == f.DOWNLOAD_SLOW.format(ref=ref, seconds=1)
    assert saved(w) == {} and held(w) == []
    await until(lambda: "/cham" in w.site.cut)


@talking("down-cut")
async def test_a_file_that_did_not_come_whole_is_not_kept(w):
    ref = ref_of(await opened(w), "Tệp đứt")

    said = await refused(w, ref, "Tệp đứt")

    assert said.startswith(f.DOWNLOAD_FAILED.format(ref=ref, error="")) and said != (
        f.DOWNLOAD_FAILED.format(ref=ref, error="")
    )
    assert saved(w) == {} and held(w) == []


@talking("down-unasked")
async def test_a_file_nobody_asked_for_is_stopped_as_it_begins(w):
    await opened(w)
    tab, begun = w.tab("down-unasked"), []
    tab.page.on("download", lambda sent: begun.append(sent))

    # A page that sends a file by itself, then a plain click on a link to one.
    await opened(w, "/tu-tai")
    await until(lambda: len(begun) == 1)
    again = await opened(w)
    await build_act(w.kit()).run(
        {"kind": "click", "ref": ref_of(again, "Tải hoá đơn"), "name": "Tải hoá đơn"}
    )
    await until(lambda: len(begun) == 2)

    # Stopped on its way or removed once whole: either way none of it is left anywhere.
    await until(lambda: held(w) == [])
    assert saved(w) == {} and "GET /hd" in w.site.seen


@talking("down-late-stop")
async def test_a_file_that_came_whole_before_it_could_be_stopped_is_removed(w, monkeypatch):
    stop, came = Download.cancel, []

    async def late(sent) -> None:
        came.append(await sent.failure())  # the browser is told to stop once the file is whole
        await stop(sent)

    monkeypatch.setattr(Download, "cancel", late)
    await opened(w)

    await w.tab("down-late-stop").page.evaluate("() => { location.href = '/hd' }")
    await until(lambda: came == [None])  # nothing stopped it: it is whole in the browser's folder

    await until(lambda: held(w) == [], seconds=3)
    assert saved(w) == {}


@talking("down-other-tab")
async def test_a_file_another_tab_sends_meanwhile_is_not_the_caller_s(w):
    ref = ref_of(await opened(w, tab="mot"), "Tải sau")
    await opened(w, "/khac", tab="hai")
    one, two, theirs = w.tab("down-other-tab", "mot"), w.tab("down-other-tab", "hai"), []
    two.page.on("download", lambda sent: theirs.append(sent.suggested_filename))

    waiting = asyncio.ensure_future(down(w, ref, "Tải sau", tab="mot"))
    # The click was made: the caller now waits for its file, which begins a while later.
    while not waiting.done() and await logged(one) != "sau;":
        await asyncio.sleep(0.02)
    await two.page.evaluate("() => { location.href = '/tep-khac' }")
    out = await waiting

    assert out == told(ref, "hoa-don-thang-10.pdf", "2.9 KB")
    assert saved(w) == {"hoa-don-thang-10.pdf": FILE.encode()}
    await until(lambda: theirs == ["khac.txt"])  # it began while the caller waited
    await until(lambda: held(w) == [])


@talking("down-other-window")
async def test_a_file_a_window_another_tab_opened_meanwhile_sends_is_not_the_caller_s(w):
    ref = ref_of(await opened(w, tab="mot"), "Tải sau")
    await opened(w, "/khac", tab="hai")
    one, two = w.tab("down-other-window", "mot"), w.tab("down-other-window", "hai")
    asked = len(w.site.seen)

    waiting = asyncio.ensure_future(down(w, ref, "Tải sau", tab="mot"))
    while not waiting.done() and await logged(one) != "sau;":
        await asyncio.sleep(0.02)
    await two.page.evaluate("() => { window.open('/cua-so-khac') }")
    out = await waiting

    assert out == told(ref, "hoa-don-thang-10.pdf", "2.9 KB")
    assert saved(w) == {"hoa-don-thang-10.pdf": FILE.encode()}
    # The other window's file began first, while the caller was waiting for its own.
    files = [line for line in w.site.seen[asked:] if line in ("GET /tep-khac", "GET /hd")]
    assert files == ["GET /tep-khac", "GET /hd"]
    await until(lambda: held(w) == [])


async def test_a_page_is_listened_to_only_for_as_long_as_the_call_waits():
    class Source:
        def __init__(self) -> None:
            self.listening: dict = {}

        def on(self, event: str, handler) -> None:
            self.listening[event] = handler

        def remove_listener(self, event: str, handler) -> None:
            assert self.listening.pop(event) is handler

    source = Source()

    with heard(source, "popup") as told_of:
        source.listening["popup"]("one")
        source.listening["popup"]("two")
        assert told_of == ["one", "two"]
    assert source.listening == {}

    with pytest.raises(ToolError), heard(source, "popup"):
        raise ToolError("hỏng")
    assert source.listening == {}


@talking("down-busy")
async def test_a_download_while_another_call_waits_for_its_file_clicks_nothing(w):
    ref = ref_of(await opened(w), "Không tải gì")
    tab, session = w.tab("down-busy"), w.pool.running("coach")

    async with session.downloads.expecting(lambda sent: False):
        said = await refused(w, ref, "Không tải gì")

    assert said == f.DOWNLOAD_BUSY and await logged(tab) == ""


@talking("down-shown")
async def test_only_the_element_the_model_was_shown_is_clicked(w):
    ref = ref_of(await opened(w), "Tải hoá đơn")
    tab, asked = w.tab("down-shown"), len(w.site.seen)

    assert await refused(w, ref, "Tải biên lai") == (
        t.NAME_MISMATCH.format(ref=ref, name="Tải biên lai")
    )
    assert await refused(w, "e999", "Tải hoá đơn") == t.REF_UNKNOWN.format(ref="e999")
    assert await refused(w, "", "Tải hoá đơn") == t.ACT_NEEDS.format(kind="click", what="ref")
    await tab.page.goto(w.site.url("/khac"))
    assert await refused(w, ref, "Tải hoá đơn") == t.PAGE_MOVED

    assert "GET /hd" not in w.site.seen[asked:]  # nothing was clicked: no file was asked for
    assert saved(w) == {}


@talking("down-gate")
async def test_a_person_is_asked_for_the_hosts_and_the_words_a_click_is_asked_for(w):
    bound = w.kit(hosts=("localhost",))
    first = await opened(w)
    tab, session = w.tab("down-gate"), w.pool.running("coach")
    plain, word = ref_of(first, "Tải hoá đơn"), ref_of(first, "Xoá hoá đơn")
    was, asked = (tab.used, tab.shown, session.tabs.last("down-gate")), len(w.site.seen)

    assert why(w, plain, "Tải hoá đơn") is None
    assert why(w, word, " Xoá   hoá đơn ") == f.ASK_DOWNLOAD_WORD.format(
        name="Xoá hoá đơn", host="127.0.0.1", word="xoá"
    )
    # What the page drew under the element counts when the name given holds no word.
    assert why(w, ref_of(first, "Biên lai"), "Biên lai") == f.ASK_DOWNLOAD_WORD.format(
        name="Biên lai", host="127.0.0.1", word="xoá"
    )
    # A name the model made up counts as the name a person is asked about.
    assert why(w, plain, "x" * 90 + " mua") == f.ASK_DOWNLOAD_WORD.format(
        name="x" * 80, host="127.0.0.1", word="mua"
    )
    assert why(w, plain, "Tải hoá đơn", kit=bound) == f.ASK_DOWNLOAD_OUTSIDE.format(
        name="Tải hoá đơn", host="127.0.0.1"
    )
    assert why(w, "e999", "Xoá hoá đơn", kit=bound) is None  # nothing will be clicked
    # Asking is only reading: the gate asks several times for one call.
    now = (tab.used, tab.shown, session.tabs.last("down-gate"))
    assert now[0] == was[0] and now[1] is was[1] and now[2] is was[2]
    assert "GET /hd" not in w.site.seen[asked:] and saved(w) == {}

    home = await build_navigate(w.kit()).run(
        {"url": w.site.url("/", host="localhost"), "tab": "nha"}
    )
    ref = ref_of(home, "Tải hoá đơn")
    assert why(w, ref, "Tải hoá đơn", kit=bound) is None  # a host of its own
    assert why(w, ref_of(home, "Xoá hoá đơn"), "Xoá hoá đơn", kit=bound) == (
        f.ASK_DOWNLOAD_WORD.format(name="Xoá hoá đơn", host="localhost", word="xoá")
    )
    assert await down(w, ref, "Tải hoá đơn", kit=bound) == told(
        ref, "hoa-don-thang-10.pdf", "2.9 KB", host="localhost"
    )


async def test_the_gate_starts_no_browser(w):
    kit = w.kit("nobody", hosts=("localhost",))

    assert why(w, "e2", "Xoá hoá đơn", kit=kit) is None
    assert w.pool.running("nobody") is None


@talking("down-held")
async def test_an_agent_held_to_some_folders_keeps_its_files_under_the_first(w):
    ref = ref_of(await opened(w), "Tải hoá đơn")

    out = await down(w, ref, "Tải hoá đơn", paths=("data", "notes"))

    assert out == f.DOWNLOAD_SAVED.format(
        ref=ref, host="127.0.0.1", path=f"data/{FOLDER}/hoa-don-thang-10.pdf", size="2.9 KB"
    )
    assert saved(w, "data") == {"hoa-don-thang-10.pdf": FILE.encode()}
    assert sorted(p.name for p in w.workspace.iterdir()) == ["data"]


@talking("down-escape")
async def test_a_folder_that_leads_out_of_the_workspace_is_refused_before_any_click(w, tmp_path):
    ref = ref_of(await opened(w), "Tải hoá đơn")
    os.symlink(tmp_path, w.workspace / FOLDER)
    asked = len(w.site.seen)

    assert await refused(w, ref, "Tải hoá đơn") == WORKSPACE_ESCAPE

    assert "GET /hd" not in w.site.seen[asked:] and list(tmp_path.iterdir()) == []


@talking("down-unsaved")
async def test_a_file_that_came_and_could_not_be_put_in_the_workspace_says_so(w):
    ref = ref_of(await opened(w), "Tải hoá đơn")
    (w.workspace / FOLDER).write_bytes(b"a file where the folder would be")

    said = await refused(w, ref, "Tải hoá đơn")

    assert said == f.DOWNLOAD_NOT_SAVED.format(ref=ref, error="File exists")
    assert (w.workspace / FOLDER).read_bytes() == b"a file where the folder would be"
    assert held(w) == []


@talking("down-address")
async def test_an_address_that_answers_with_a_file_is_no_page_and_keeps_no_file(w):
    await opened(w)

    with pytest.raises(ToolError) as error:
        await opened(w, "/hd")

    assert str(error.value) == f.NAV_IS_FILE
    await until(lambda: held(w) == [])
    assert saved(w) == {} and w.tab("down-address").page.url == "about:blank"
