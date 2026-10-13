"""`browser_pdf` against a real Chromium: the page of a tab printed as a file in the agent's
workspace, under a cleaned name that ends in `.pdf` whatever it was called. It only looks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_files as f
from my_agent_crew.browser import downloads as dl
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.navigate import build_navigate
from my_agent_crew.browser.tools_files import FOLDER, build_pdf, size_said
from my_agent_crew.texts import WORKSPACE_ESCAPE, WORKSPACE_WRITE_OUTSIDE
from my_agent_crew.tools.registry import ToolError
from tests.browser_tools import talking, world

pytestmark = pytest.mark.asyncio(loop_scope="module")

PAGES = {
    "/": "<title>Hoá đơn tháng 10</title><h1>Hoá đơn</h1><p>Tổng cộng: 120.000 đ</p>",
    "/khac": "<title>Trang khác</title><h1>Khác</h1>" + "<p>dòng</p>" * 400,
    "/khong-ten": "<p>Trang không có tiêu đề</p>",
    "/ten-la": "<title>../../etc/passwd</title><p>Tên lạ</p>",
}


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def w(tmp_path_factory):
    async with world(tmp_path_factory.mktemp("pdf"), PAGES, max_tabs=40) as made:
        yield made


@pytest.fixture(autouse=True)
def emptied(w):
    """A workspace each test finds as the first did."""
    yield
    for left in sorted(w.workspace.rglob("*"), reverse=True):
        left.rmdir() if left.is_dir() and not left.is_symlink() else left.unlink()


async def opened(w, path: str = "/", **how) -> str:
    return await build_navigate(w.kit()).run({"url": w.site.url(path), **how})


async def printed(w, paths=(), **args) -> str:
    return await build_pdf(w.kit(), paths).run(args)


async def refused(w, paths=(), **args) -> str:
    with pytest.raises(ToolError) as error:
        await printed(w, paths, **args)
    return str(error.value)


def files(w, *under: str) -> dict[str, bytes]:
    folder = w.workspace.joinpath(*under, FOLDER)
    return {p.name: p.read_bytes() for p in folder.iterdir()} if folder.is_dir() else {}


def told(label: str, name: str, data: bytes, under: str = "") -> str:
    where = f"{under}{FOLDER}/{name}"
    return f.PDF_SAVED.format(label=label, path=where, size=size_said(len(data)))


async def test_the_tool_only_looks_so_nobody_is_asked_and_a_script_may_call_it(w):
    tool = build_pdf(w.kit("nobody"))

    assert (tool.name, tool.requires_approval) == (k.PDF, False)
    assert (tool.replay_safe, tool.parallel) == (True, False)
    assert tool.ask_when is None and tool.allow_when is None and tool.ask_reason is None
    assert tool.parameters["required"] == []
    assert set(tool.parameters["properties"]) == {"tab", "save_as"}
    assert tool.to_dict()["with_browser"] is True
    assert k.PDF in k.READ_TOOLS


@talking("pdf-none")
async def test_a_conversation_with_no_tab_has_nothing_to_print(w):
    assert await refused(w) == t.NO_TAB
    assert files(w) == {} and w.pool.running("coach").tabs.of("pdf-none") == []


@talking("pdf-one")
async def test_a_page_is_printed_under_its_title_in_plain_letters(w):
    await opened(w)
    tab = w.tab("pdf-one")
    was = (tab.page.url, tab.shown)

    out = await printed(w)

    ((name, data),) = files(w).items()
    assert name == "Hoa-don-thang-10.pdf" and data.startswith(b"%PDF-")
    assert out == told(tab.label, name, data)
    assert len(data) > 1000 and (tab.page.url, tab.shown) == was  # the page is as it was
    assert sorted(p.name for p in w.workspace.iterdir()) == [FOLDER]


@talking("pdf-names")
async def test_a_name_ends_in_pdf_whatever_it_was_called_and_never_takes_another_s_place(w):
    await opened(w)
    label = w.tab("pdf-names").label

    first = await printed(w)
    second = await printed(w)
    third = await printed(w, save_as="../a/Báo cáo  Đà Nẵng.exe")
    fourth = await printed(w, save_as="bao-cao.PDF")

    names = ["Hoa-don-thang-10.pdf", "Hoa-don-thang-10-2.pdf", "Bao-cao-Da-Nang.exe.pdf"]
    names.append("bao-cao.pdf")
    kept = files(w)
    assert sorted(kept) == sorted(names) and all(x.startswith(b"%PDF-") for x in kept.values())
    assert [first, second, third, fourth] == [told(label, n, kept[n]) for n in names]


@talking("pdf-titles")
async def test_a_page_names_no_file_out_of_the_folder_and_one_without_a_title_has_a_name(w):
    await opened(w, "/ten-la", tab="la")
    await opened(w, "/khong-ten", tab="khong")

    await printed(w, tab="la")
    await printed(w, tab="khong")

    assert sorted(files(w)) == ["page.pdf", "passwd.pdf"]
    assert sorted(p.name for p in w.workspace.iterdir()) == [FOLDER]


@talking("pdf-tabs")
async def test_the_tab_named_is_the_one_printed(w):
    await opened(w, tab="mot")
    await opened(w, "/khac", tab="hai")

    last = await printed(w)
    named = await printed(w, tab="mot")

    kept = files(w)
    assert last == told("hai", "Trang-khac.pdf", kept["Trang-khac.pdf"])
    assert named == told("mot", "Hoa-don-thang-10.pdf", kept["Hoa-don-thang-10.pdf"])
    assert len(kept["Trang-khac.pdf"]) > len(kept["Hoa-don-thang-10.pdf"])  # a longer page
    assert await refused(w, tab="ba") == t.UNKNOWN_TAB.format(label="ba", labels="mot, hai")


@talking("pdf-large")
async def test_a_print_over_the_size_a_file_may_have_is_not_kept(w, monkeypatch):
    monkeypatch.setattr(dl, "LIMIT_BYTES", 1000)
    await opened(w)

    assert await refused(w) == f.PDF_TOO_LARGE.format(limit=1000 / 1024 / 1024)
    assert files(w) == {} and list(w.workspace.iterdir()) == []


@talking("pdf-held")
async def test_an_agent_held_to_some_folders_keeps_its_prints_under_the_first(w):
    await opened(w)
    label = w.tab("pdf-held").label

    out = await printed(w, ("data", "notes"))

    kept = files(w, "data")
    assert out == told(label, "Hoa-don-thang-10.pdf", kept["Hoa-don-thang-10.pdf"], "data/")
    assert sorted(p.name for p in w.workspace.iterdir()) == ["data"]


@talking("pdf-escape")
async def test_a_print_is_written_inside_the_workspace_or_not_at_all(w, tmp_path: Path):
    await opened(w)
    os.symlink(tmp_path, w.workspace / FOLDER)

    assert await refused(w) == WORKSPACE_ESCAPE
    assert list(tmp_path.iterdir()) == []

    (w.workspace / FOLDER).unlink()
    (w.workspace / "data").mkdir()
    (w.workspace / "src").mkdir()
    os.symlink(w.workspace / "src", w.workspace / "data" / FOLDER)
    assert await refused(w, ("data",)) == WORKSPACE_WRITE_OUTSIDE.format(
        paths="data", path=f"data/{FOLDER}"
    )
    assert list((w.workspace / "src").iterdir()) == []


@talking("pdf-unsaved")
async def test_a_print_that_could_not_be_put_in_the_workspace_says_so(w):
    await opened(w)
    (w.workspace / FOLDER).write_bytes(b"a file where the folder would be")

    assert await refused(w) == f.PDF_NOT_SAVED.format(error="File exists")
    assert (w.workspace / FOLDER).read_bytes() == b"a file where the folder would be"
