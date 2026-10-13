"""The tabs of one agent's browser: each belongs to the conversation that opened it."""

from __future__ import annotations

import asyncio

import pytest

from my_agent_crew import texts_browser as t
from my_agent_crew.tools.registry import ToolError
from tests.browser_servers import Clock, browsers, sites

PAGES = {
    "/": (
        "<title>Trang</title>"
        '<a href="/khac" target="_blank">Mở cửa sổ</a>'
        "<button id=a onclick=\"alert('Xin chào')\">Chào</button>"
        "<button id=c onclick=\"this.textContent = String(confirm('Xoá hết?'))\">Hỏi</button>"
        "<button id=p onclick=\"this.textContent = String(prompt('Mã?', 'x'))\">Nhập</button>"
        '<button id=x onclick="window.close()">Đóng</button>'
    ),
    "/khac": "<title>Khác</title><button onclick=\"window.open('/')\">Mở nữa</button>",
    "/giu": (
        "<title>Giữ</title><input id=i>"
        "<script>addEventListener('beforeunload', e => { e.preventDefault(); "
        "e.returnValue = 'x'; })</script>"
    ),
}


async def settled(check, seconds: float = 3.0) -> None:
    for _ in range(int(seconds / 0.02)):
        if check():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("never happened")


async def test_a_conversation_sees_its_own_tabs_and_the_one_it_used_last_first(tmp_path):
    clock = Clock()
    async with browsers(tmp_path / "b", clock=clock) as pool:
        tabs = (await pool.session("coach")).tabs
        clock.now = 1
        first = await tabs.open("c1")
        clock.now = 2
        second = await tabs.open("c1")
        other = await tabs.open("c2")

        assert (first.label, second.label, other.label) == ("t1", "t2", "t1")
        assert len({first.id, second.id, other.id}) == 3
        assert tabs.of("c1") == [second, first] and tabs.of("c2") == [other]
        assert tabs.find("c1") is second and tabs.find("c1", "t1") is first
        assert tabs.find("c2", "t2") is None and tabs.find("c3") is None

        clock.now = 3
        tabs.touch(first)

        assert tabs.find("c1") is first and tabs.get("c1") is first
        assert tabs.get("c1", " T2 ") is second


async def test_the_tab_of_the_last_call_is_that_one_or_none_and_never_another(tmp_path):
    clock = Clock()
    async with browsers(tmp_path / "b", clock=clock) as pool:
        tabs = (await pool.session("coach")).tabs
        clock.now = 1
        first, other = await tabs.open("c1"), await tabs.open("c2")

        assert tabs.last("c1") is None  # a tab no call was on yet is nobody's last
        with pytest.raises(ToolError) as untouched:
            tabs.get("c1", last=True)
        assert str(untouched.value) == t.TAB_GONE.format(labels="t1")

        tabs.touch(other)
        tabs.touch(first)
        clock.now = 2
        second = await tabs.open("c1")  # as a window the page opened would be

        assert tabs.last("c1") is first and tabs.last("c2") is other
        assert tabs.find("c1") is second and tabs.get("c1") is second  # where a read goes
        assert tabs.get("c1", last=True) is first
        assert tabs.get("c1", "t2", last=True) is second  # a label given is the label meant
        with pytest.raises(ToolError) as unknown:
            tabs.get("c1", "don", last=True)
        assert str(unknown.value) == t.UNKNOWN_TAB.format(label="don", labels="t2, t1")

        await tabs.close(first)

        assert tabs.last("c1") is None and tabs.find("c1") is second
        with pytest.raises(ToolError) as gone:
            tabs.get("c1", last=True)
        assert str(gone.value) == t.TAB_GONE.format(labels="t2")

        await tabs.close(second)

        with pytest.raises(ToolError) as none:
            tabs.get("c1", last=True)
        assert str(none.value) == t.NO_TAB
        assert tabs.get("c2", last=True) is other


async def test_asking_for_a_tab_that_is_not_there_says_which_there_are(tmp_path):
    async with browsers(tmp_path / "b") as pool:
        tabs = (await pool.session("coach")).tabs
        with pytest.raises(ToolError) as none:
            tabs.get("c1")
        await tabs.open("c1", "gio-hang")
        await tabs.open("c1")
        with pytest.raises(ToolError) as unknown:
            tabs.get("c1", "don")
        with pytest.raises(ToolError) as others:
            tabs.get("c2", "gio-hang")

        assert str(none.value) == t.NO_TAB == str(others.value)
        assert str(unknown.value) == t.UNKNOWN_TAB.format(label="don", labels="t1, gio-hang")


async def test_a_tab_is_named_as_asked_and_a_name_in_use_is_not_given_twice(tmp_path):
    async with browsers(tmp_path / "b") as pool:
        tabs = (await pool.session("coach")).tabs
        named = await tabs.open("c1", " Gio-Hang_2 ")
        taken = await tabs.open("c1", "t1")
        auto = await tabs.open("c1")
        again = await tabs.open("c1", "gio-hang_2")

        assert (named.label, taken.label, auto.label, again.label) == (
            "gio-hang_2",
            "t1",
            "t2",
            "t3",
        )


@pytest.mark.parametrize("label", ["giỏ hàng", "a b", "-a", "a" * 25, "a/b", "../x"])
async def test_a_label_that_is_no_label_opens_nothing(tmp_path, label):
    async with browsers(tmp_path / "b") as pool:
        tabs = (await pool.session("coach")).tabs
        with pytest.raises(ToolError) as refused:
            await tabs.open("c1", label)

        assert str(refused.value) == t.BAD_LABEL.format(label=label) and tabs.all() == []


async def test_a_conversation_holding_every_tab_is_told_to_close_one(tmp_path):
    async with browsers(tmp_path / "b", max_tabs=2) as pool:
        session = await pool.session("coach")
        await session.tabs.open("c1")
        await session.tabs.open("c1")
        with pytest.raises(ToolError) as refused:
            await session.tabs.open("c1")

        assert str(refused.value) == t.TOO_MANY_TABS.format(count=2)
        assert len(session.tabs.all()) == 2 and len(session.context.pages) == 3


async def test_at_the_limit_the_tab_another_conversation_used_longest_ago_gives_way(tmp_path):
    clock = Clock()
    async with browsers(tmp_path / "b", clock=clock, max_tabs=3) as pool:
        tabs = (await pool.session("coach")).tabs
        old = await tabs.open("c1")
        clock.now = 1
        newer = await tabs.open("c1")
        clock.now = 2
        mine = await tabs.open("c2")
        clock.now = 3
        tabs.touch(old)

        opened = await tabs.open("c2")

        assert newer.page.is_closed() and not old.page.is_closed()
        assert tabs.all() == [old, mine, opened]


async def test_a_tab_in_the_middle_of_an_action_does_not_give_way(tmp_path):
    clock = Clock()
    async with browsers(tmp_path / "b", clock=clock, max_tabs=1) as pool:
        tabs = (await pool.session("coach")).tabs
        busy = await tabs.open("c1")
        clock.now = 5000
        async with busy.lock:
            with pytest.raises(ToolError):
                await tabs.open("c2")
            assert await tabs.close_cold() == 0
        assert tabs.all() == [busy] and not busy.page.is_closed()


async def test_two_conversations_opening_at_once_do_not_both_take_the_last_place(tmp_path):
    async with browsers(tmp_path / "b", max_tabs=2) as pool:
        tabs = (await pool.session("coach")).tabs
        await tabs.open("c1")
        got = await asyncio.gather(tabs.open("c1"), tabs.open("c1"), return_exceptions=True)

        assert sorted(type(one).__name__ for one in got) == ["Tab", "ToolError"]
        assert len(tabs.all()) == 2


async def test_a_tab_nobody_used_for_half_an_hour_is_closed(tmp_path):
    clock = Clock()
    async with browsers(tmp_path / "b", clock=clock) as pool:
        tabs = (await pool.session("coach")).tabs
        cold = await tabs.open("c1")
        clock.now = 1
        warm = await tabs.open("c2")
        clock.now = 1799
        assert await tabs.close_cold() == 0

        clock.now = 1800

        assert await tabs.close_cold() == 1
        assert tabs.all() == [warm] and cold.page.is_closed() and tabs.find("c1") is None


async def test_closing_a_tab_closes_its_page_and_a_page_that_closes_itself_is_no_tab(tmp_path):
    with sites(PAGES) as (site,):
        async with browsers(tmp_path / "b", site) as pool:
            tabs = (await pool.session("coach")).tabs
            one, two = await tabs.open("c1"), await tabs.open("c1")
            await tabs.close(one)
            await tabs.close(one)

            assert one.page.is_closed() and tabs.all() == [two]

            await two.page.goto(site.url("/khac"))
            await two.page.click("button")
            await settled(lambda: len(tabs.all()) == 2)
            opened = tabs.all()[1]
            await opened.page.click("#x")  # a window a script opened may close itself
            await settled(lambda: tabs.all() == [two])
            assert opened.page.is_closed()


async def test_a_window_a_page_opens_is_the_next_tab_of_the_same_conversation(tmp_path):
    with sites(PAGES) as (site,):
        async with browsers(tmp_path / "b", site, max_tabs=3) as pool:
            tabs = (await pool.session("coach")).tabs
            other, tab = await tabs.open("c2"), await tabs.open("c1")
            await tab.page.goto(site.url("/"))

            await tab.page.click("a")
            await settled(lambda: len(tabs.of("c1")) == 2)

            popup = next(x for x in tabs.of("c1") if x is not tab)
            await popup.page.wait_for_load_state()
            assert (popup.label, popup.owner, popup.shown) == ("t2", "c1", None)
            assert popup.page.url == site.url("/khac") and tabs.of("c2") == [other]

            async with popup.page.context.expect_page() as third:  # over the limit
                await popup.page.click("button")
            extra = await third.value
            await settled(extra.is_closed)
            assert len(tabs.all()) == 3 and not popup.page.is_closed()


async def test_a_dialog_is_sent_away_and_kept_to_be_told(tmp_path):
    with sites(PAGES) as (site,):
        async with browsers(tmp_path / "b", site) as pool:
            tab = await (await pool.session("coach")).tabs.open("c1")
            await tab.page.goto(site.url("/"))

            await tab.page.click("#a")
            await tab.page.click("#c")
            await tab.page.click("#p")

            assert tab.dialogs == ["alert: Xin chào", "confirm: Xoá hết?", "prompt: Mã?"]
            assert await tab.page.inner_text("#c") == "false"  # nobody said yes
            assert await tab.page.inner_text("#p") == "null"

            for _ in range(4):
                await tab.page.click("#a")
            assert len(tab.dialogs) == 5 and tab.dialogs[0] == "prompt: Mã?"

            await tab.page.evaluate(
                "document.querySelector('#a').onclick = () => alert('x'.repeat(999))"
            )
            await tab.page.click("#a")
            assert len(tab.dialogs[-1]) == 300


async def test_a_page_that_asks_whether_to_leave_is_left(tmp_path):
    with sites(PAGES) as (site,):
        async with browsers(tmp_path / "b", site) as pool:
            tab = await (await pool.session("coach")).tabs.open("c1")
            await tab.page.goto(site.url("/giu"))
            await tab.page.fill("#i", "đang gõ dở")  # a page asks only once it was touched

            await tab.page.goto(site.url("/khac"))

            assert await tab.page.title() == "Khác"
            assert tab.dialogs in ([], ["beforeunload: "])
