"""The mark an outline puts on what came to a page since the model was last shown it, against
a real Chromium: a page that grew where it stood, one that drew itself again, one that was
loaded again, one that became another, and the views a long page is cut down to."""

from __future__ import annotations

import re

import pytest
import pytest_asyncio

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.navigate import build_navigate
from my_agent_crew.browser.snapshot_view import NEW
from my_agent_crew.browser.tools_act import build_act
from my_agent_crew.browser.tools_read import build_snapshot
from my_agent_crew.tools.registry import ToolRegistry
from tests.browser_tools import parts, ref_of, talking, world

pytestmark = pytest.mark.asyncio(loop_scope="module")

# A row put first in the list, the count in the link, and a message under everything.
CART = (
    "<title>Giỏ</title><h1>Giỏ hàng</h1><a href='/khac' id=dem>Giỏ hàng (1)</a>"
    "<ul id=ds><li>Áo <button>Xoá</button></li><li>Quần <button>Xoá</button></li></ul>"
    '<input aria-label="Ghi chú" id=note value="cũ">'
    '<button onclick="them()">Thêm áo khoác</button>'
    "<script>function them() {"
    " document.getElementById('ds').insertAdjacentHTML("
    "'afterbegin', '<li>Áo khoác <button>Xoá</button></li>');"
    " document.getElementById('dem').textContent = 'Giỏ hàng (2)';"
    " document.body.insertAdjacentHTML('beforeend', '<p role=alert>Đã thêm áo khoác</p>') }"
    "</script>"
)
# Everything under the box is made anew at each click, with one button and a line more.
REDRAW = (
    "<title>Vẽ</title><div id=goc></div><script>let n = 0; function ve() { n += 1;"
    " document.getElementById('goc').innerHTML = '<h2>Đơn</h2>'"
    " + '<button onclick=\"ve()\">Vẽ lại</button>' + '<button>Xoá</button>'.repeat(2)"
    " + (n > 1 ? '<p role=status>Lần ' + n + '</p><button>Xoá</button>' : '') } ve()</script>"
)
RELOAD = (
    "<title>Nạp</title><h1>Đơn</h1>"
    "<script>if (sessionStorage.xong) document.write('<p>Đã lưu đơn</p>')</script>"
    '<button onclick="sessionStorage.xong = 1; location.reload()">Lưu</button>'
)
# The address stays and nothing that said anything does.
STEPS = (
    "<title>Bước</title><h1>Bước một</h1><p>Chọn món</p>"
    "<button onclick=\"document.body.innerHTML = '<h1>Bước hai</h1><p>Chọn cách giao</p>"
    "<button>Xong</button>'\">Tiếp</button>"
)
SECTIONS = 40
LONG = (
    "<title>Dài</title>"
    + "".join(
        f"<h2>Mục {n}</h2><p>{'Đoạn văn dài của mục này. ' * 20}</p><button>Nút {n}</button>"
        for n in range(SECTIONS)
    )
    + "<script>function them() { document.body.insertAdjacentHTML("
    "'afterbegin', '<button>Nút mới</button><p role=alert>Vừa thêm</p>') }</script>"
)
PAGES = {
    "/gio": CART,
    "/ve": REDRAW,
    "/nap": RELOAD,
    "/buoc": STEPS,
    "/dai": LONG,
    # A heading the cart has too: an address is what makes this another page.
    "/khac": "<title>Khác</title><h1>Giỏ hàng</h1><p>Trang khác</p>",
}
REF = re.compile(r"\[ref=\w+\]")


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def w(tmp_path_factory):
    async with world(tmp_path_factory.mktemp("new"), PAGES, max_tabs=40) as made:
        yield made


async def opened(w, path: str) -> str:
    return await build_navigate(w.kit()).run({"url": w.site.url(path)})


async def clicked(w, answer: str, name: str) -> str:
    asked = {"kind": "click", "ref": ref_of(answer, name), "name": name}
    return await build_act(w.kit()).run(asked)


def said(answer: str) -> list[str]:
    """What an answer says before the line that announces its fence."""
    return parts(answer)[0].splitlines()[:-1]


def marked(answer: str) -> list[str]:
    """The lines of the page that carry the mark, without the refs the browser gave."""
    lines = parts(answer)[1].splitlines()
    return [REF.sub("[ref]", line.strip()) for line in lines if NEW in line]


def alike(answer: str, name: str) -> list[tuple[str, bool]]:
    """The buttons of one name in the order drawn: the ref of each and whether it is marked."""
    found = re.findall(rf'button "{name}" \[ref=(\w+)\]( \[new\])?', parts(answer)[1])
    return [(ref, bool(mark)) for ref, mark in found]


def new(count: int) -> str:
    return d.PAGE_NEW.format(count=count)


@talking("new-grown")
async def test_what_an_action_brought_to_a_page_is_marked_and_counted_outside_the_fence(w):
    first = await opened(w, "/gio")
    were = [ref for ref, _mark in alike(first, "Xoá")]
    answer = await clicked(w, first, "Thêm áo khoác")
    again = await build_snapshot(w.kit()).run({})

    assert said(first) == ["Tab t1 · HTTP 200"] and NEW not in first
    done = t.ACT_DONE.format(kind="click", ref=ref_of(first, "Thêm áo khoác"))
    assert said(answer) == [done, "Tab t1", new(4)]
    assert marked(answer) == [
        '- link "Giỏ hàng (2)" [ref] [cursor=pointer] [new]:',
        "- listitem [ref] [new]:",
        '- button "Xoá" [ref] [new]',
        "- alert [ref] [new]: Đã thêm áo khoác",
    ]
    # Of three buttons alike the one marked is the one that came, though it is drawn first.
    now = alike(answer, "Xoá")
    assert now[1:] == [(were[0], False), (were[1], False)]
    assert now[0][1] and now[0][0] not in were
    # A marked line names its element as any other does, and a look after it finds no more.
    assert ref_of(answer, "Giỏ hàng (2)") in w.tab("new-grown").shown.nodes
    assert said(again) == ["Tab t1"] and NEW not in again


@talking("new-redrawn")
async def test_a_page_that_drew_itself_again_marks_only_what_it_has_more_of(w):
    first = await opened(w, "/ve")
    answer = await clicked(w, first, "Vẽ lại")

    were, now = alike(first, "Xoá"), alike(answer, "Xoá")
    # Every button is another element than the one shown: none kept the ref it had.
    assert len(were) == 2 and not {ref for ref, _ in were} & {ref for ref, _ in now}
    assert ref_of(first, "Vẽ lại") != ref_of(answer, "Vẽ lại")
    assert marked(answer) == ["- status [ref] [new]: Lần 2", '- button "Xoá" [ref] [new]']
    assert [mark for _ref, mark in now] == [False, False, True]
    assert said(answer)[1:] == ["Tab t1", new(2)]


@talking("new-reloaded")
async def test_a_page_loaded_again_at_its_address_marks_what_it_shows_more(w):
    first = await opened(w, "/nap")
    answer = await clicked(w, first, "Lưu")

    assert "Đã lưu đơn" not in first and ref_of(first, "Lưu") != ref_of(answer, "Lưu")
    assert marked(answer) == ["- paragraph [ref] [new]: Đã lưu đơn"]
    assert said(answer)[1:] == ["Tab t1", new(1)]


@talking("new-elsewhere")
async def test_going_to_a_page_marks_nothing_and_neither_does_an_action_that_leads_elsewhere(w):
    first = await opened(w, "/gio")
    grown = await clicked(w, first, "Thêm áo khoác")
    # The same address asked for again: the page as it was at first, and all of it is told.
    back = await opened(w, "/gio")
    away = await clicked(w, back, "Giỏ hàng (1)")

    assert marked(grown) and said(back) == ["Tab t1 · HTTP 200"]
    assert 'link "Giỏ hàng (1)"' in back and NEW not in back
    assert "Địa chỉ: " + w.site.url("/khac") in parts(away)[1].splitlines()
    assert 'heading "Giỏ hàng"' in away and "Trang khác" in away
    assert said(away)[1:] == ["Tab t1"] and NEW not in away


@talking("new-other")
async def test_a_page_that_became_another_at_its_address_is_marked_nowhere(w):
    first = await opened(w, "/buoc")
    answer = await clicked(w, first, "Tiếp")

    inside = parts(answer)[1]
    assert "Địa chỉ: " + w.site.url("/buoc") in inside.splitlines()
    assert all(text in inside for text in ('heading "Bước hai"', "Chọn cách giao", 'button "Xong"'))
    assert "Bước một" not in inside and said(answer)[1:] == ["Tab t1"] and NEW not in answer


@talking("new-views")
async def test_what_came_while_nobody_acted_is_marked_in_the_list_and_in_a_search(w):
    await opened(w, "/gio")
    tab, snapshot = w.tab("new-views"), build_snapshot(w.kit())

    await tab.page.evaluate("them()")
    listed = await snapshot.run({"interactive": True})
    await tab.page.evaluate("them()")
    found = await snapshot.run({"query": "áo  KHOÁC"})

    # The list holds what can be acted on: the row and the message that came are not in it.
    assert marked(listed) == [
        '- link "Giỏ hàng (2)" [ref] [cursor=pointer] [new]:',
        '- button "Xoá" [ref] [new]',
    ]
    assert said(listed) == ["Tab t1", new(2)]
    # A search gives the lines that hold the words: of the two rows and the two messages
    # the ones marked are those of the second time, and the button that came is not given.
    assert marked(found) == ["- listitem [ref] [new]:", "- alert [ref] [new]: Đã thêm áo khoác"]
    assert said(found) == ["Tab t1", new(2)]
    lines = [line.strip() for line in parts(found)[1].splitlines()]
    assert lines.count("- text: Áo khoác") == 2 and 'button "Xoá"' not in parts(found)[1]
    assert len([line for line in lines if line.startswith("- alert ")]) == 2


@talking("new-long")
async def test_a_long_page_says_how_it_was_cut_and_what_came_and_stays_under_the_cap(w):
    await opened(w, "/dai")
    tab, whole = w.tab("new-long"), SECTIONS * 2  # a heading and a button each
    roomy, tight = (build_snapshot(w.kit(limit=limit)) for limit in (6_000, 3_000))

    await tab.page.evaluate("them()")
    listed = await roomy.run({})
    await tab.page.evaluate("them()")
    cut = await tight.run({})
    await tab.page.evaluate("them()")
    through = await ToolRegistry([tight], limit=3_000).execute(k.SNAPSHOT, {})

    # The message that came is no part of a list of what can be acted on; the button is.
    total = whole + 1
    assert said(listed) == ["Tab t1", t.PAGE_LISTED.format(shown=total, total=total), new(1)]
    assert marked(listed) == ['- button "Nút mới" [ref] [new]'] and "Vừa thêm" not in listed
    assert [mark for _ref, mark in alike(listed, "Nút mới")] == [True]
    # Cut further, the page says both: how much of it is given and what of that came.
    shown = int(re.search(rf"Đã cắt còn (\d+)/{total + 1} dòng", parts(cut)[0]).group(1))
    assert said(cut) == ["Tab t1", t.PAGE_CUT.format(shown=shown, total=total + 1), new(1)]
    assert 0 < shown < total and len(cut) <= 3_000
    assert [mark for _ref, mark in alike(cut, "Nút mới")] == [True, False]
    # The registry, which cuts what is over its cap, finds nothing to cut.
    assert through.ok and len(through.output) <= 3_000
    assert said(through.output)[-1] == new(1)
    assert [mark for _ref, mark in alike(through.output, "Nút mới")] == [True, False, False]
