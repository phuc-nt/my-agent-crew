"""`browser_navigate`: the address is read once and checked, a hop the proxy refuses ends the
call with a blank tab, and a page is told between fence lines."""

from __future__ import annotations

import time

import pytest
import pytest_asyncio
from playwright.async_api import Error

from my_agent_crew import texts_browser as t
from my_agent_crew.agent.tool_gate import ASK, RUN, verdict
from my_agent_crew.agent.turn_context import reading_as
from my_agent_crew.browser import navigate
from my_agent_crew.browser.navigate import build_navigate
from my_agent_crew.browser.policy import host_of
from my_agent_crew.tools.registry import ToolError
from tests.browser_servers import Site, browsers, sites
from tests.browser_tools import World, parts, talking, world

pytestmark = pytest.mark.asyncio(loop_scope="module")

PAGES = {
    "/": "<title>Cửa hàng</title><h1>Đơn hàng</h1><a href='/khac'>Xem đơn</a><button>Tìm</button>",
    "/khac": "<title>Khác</title><p>Trang khác</p>",
    "/cam": lambda site: (403, {}, "<title>Cấm</title><p>Không được vào</p>"),
    "/gia": lambda site: (403, {"x-crew-proxy": "1"}, "<p>giả</p>"),
    "/cham": lambda site: (time.sleep(2.5), (200, {}, "<p>muộn</p>"))[1],
    "/tai": lambda site: (200, {"content-disposition": "attachment; filename=a.bin"}, "x"),
}


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def w(tmp_path_factory):
    async with world(tmp_path_factory.mktemp("nav"), PAGES) as made:
        dead = Site()
        dead.close()
        made.ports.add(dead.port)
        private, gone = made.intranet.url("/"), dead.url("/")
        made.site.pages.update(
            {
                "/vong": lambda site: (302, {"location": private}, ""),
                "/vong-tls": lambda site: (
                    302,
                    {"location": private.replace("http:", "https:")},
                    "",
                ),
                "/vong-chet": lambda site: (302, {"location": gone}, ""),
                "/anh": f"<title>Ảnh</title><img src='{made.intranet.url('/x.png')}'><p>Có ảnh</p>",
                # Its picture is asked for at once; the rest of it comes too late.
                "/anh-cham": lambda site: (
                    200,
                    {},
                    [
                        f"<title>Chậm</title><img src='{made.intranet.url('/x.png')}'>"
                        + "<!-- đệm -->" * 400,
                        2.5,
                        "<p>muộn</p>",
                    ],
                ),
            }
        )
        made.dead = dead
        yield made


@talking("nav-open")
async def test_a_page_is_told_between_fence_lines_and_kept_as_what_was_shown(w):
    go = build_navigate(w.kit())

    answer = await go.run({"url": w.site.url("/")})
    outside, inside = parts(answer)
    tab = w.tab("nav-open")

    assert outside.splitlines()[0] == "Tab t1 · HTTP 200"
    assert "Cửa hàng" not in outside and w.site.url("/") not in outside
    assert inside.splitlines()[:2] == [f"Địa chỉ: {w.site.url('/')}", "Tiêu đề: Cửa hàng"]
    assert 'heading "Đơn hàng"' in inside and 'link "Xem đơn"' in inside
    assert tab.shown.url == w.site.url("/")
    assert {(n.role, n.name) for n in tab.shown.nodes.values()} >= {
        ("link", "Xem đơn"),
        ("button", "Tìm"),
    }


@talking("nav-tabs")
async def test_a_call_goes_on_in_the_tab_used_last_unless_it_names_another(w):
    go = build_navigate(w.kit())

    first = await go.run({"url": w.site.url("/")})
    again = await go.run({"url": w.site.url("/khac")})
    named = await go.run({"url": w.site.url("/"), "tab": "Gio-Hang"})
    back = await go.run({"url": w.site.url("/khac"), "tab": "t1"})

    assert [x.splitlines()[0].split(" · ")[0] for x in (first, again, named, back)] == [
        "Tab t1",
        "Tab t1",
        "Tab gio-hang",
        "Tab t1",
    ]
    assert sorted(tab.label for tab in w.pool.running("coach").tabs.of("nav-tabs")) == [
        "gio-hang",
        "t1",
    ]
    with pytest.raises(ToolError) as bad:
        await go.run({"url": w.site.url("/"), "tab": "Giỏ hàng"})
    assert str(bad.value) == t.BAD_LABEL.format(label="Giỏ hàng")


async def test_an_address_that_is_refused_starts_no_browser(w):
    go = build_navigate(w.kit("never"))

    refused = {}
    for url in (
        w.intranet.url("/"),
        "http://localhost:1/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "about:blank",
        f"http://nguoi@127.0.0.1:{w.site.port}/",
        "",
    ):
        with pytest.raises(ToolError) as error:
            await go.run({"url": url})
        refused[url] = str(error.value)
    with pytest.raises(ToolError) as unread:
        await go.run({"url": ["http://127.0.0.1/"]})

    assert refused[w.intranet.url("/")] == t.URL_PRIVATE.format(host="127.0.0.1")
    assert refused["http://localhost:1/"] == t.URL_PRIVATE.format(host="localhost")
    assert set(list(refused.values())[2:]) == {t.URL_SCHEME} == {str(unread.value)}
    assert w.pool.running("never") is None and w.intranet.seen == []


@talking("nav-hop")
async def test_a_page_that_leads_to_a_private_address_is_refused_and_leaves_a_blank_tab(w):
    go = build_navigate(w.kit())
    await go.run({"url": w.site.url("/")})

    told = {}
    for path in ("/vong", "/vong-tls"):
        with pytest.raises(ToolError) as error:
            await go.run({"url": w.site.url(path)})
        tab = w.tab("nav-hop")
        told[path] = (str(error.value), tab.page.url, tab.shown)

    refused = t.NAV_REFUSED.format(hosts="127.0.0.1")
    assert told == {
        "/vong": (refused, "about:blank", None),
        "/vong-tls": (refused, "about:blank", None),
    }
    assert w.intranet.seen == []
    # The tab is still the conversation's and goes on to the next page.
    assert (await go.run({"url": w.site.url("/khac")})).startswith("Tab t1 · HTTP 200")


@talking("nav-own")
async def test_a_refusal_of_the_site_itself_is_a_page_like_any_other(w):
    go = build_navigate(w.kit())

    outside, inside = parts(await go.run({"url": w.site.url("/cam")}))

    assert outside.splitlines()[0] == "Tab t1 · HTTP 403"
    assert "Tiêu đề: Cấm" in inside and "Không được vào" in inside
    assert w.tab("nav-own").shown is not None


@talking("nav-fake")
async def test_a_site_that_writes_the_proxys_mark_only_refuses_itself(w):
    go = build_navigate(w.kit())

    with pytest.raises(ToolError) as error:
        await go.run({"url": w.site.url("/gia")})

    assert str(error.value) == t.NAV_REFUSED.format(hosts="127.0.0.1")
    assert w.tab("nav-fake").page.url == "about:blank"


@talking("nav-dead")
async def test_a_server_that_does_not_answer_is_named_and_nothing_is_refused(w):
    go = build_navigate(w.kit())
    session = await w.pool.session("coach")
    mark = session.proxy.refused_total

    said = []
    for path in ("/", "/vong-chet"):
        with pytest.raises(ToolError) as error:
            await go.run({"url": w.dead.url("/") if path == "/" else w.site.url(path)})
        said.append(str(error.value))

    assert said == [t.NAV_UNREACHABLE.format(host="127.0.0.1")] * 2
    assert session.proxy.refused_since(mark) == []
    assert w.tab("nav-dead").page.url == "about:blank"


@talking("nav-slow")
async def test_a_page_too_slow_to_load_is_given_up_and_the_tab_stays_usable(w, monkeypatch):
    monkeypatch.setattr(navigate, "LOAD_SECONDS", (1, 1, 1))
    go = build_navigate(w.kit())

    with pytest.raises(ToolError) as error:
        await go.run({"url": w.site.url("/cham?bi-mat=1")})

    assert str(error.value) == t.NAV_FAILED.format(error="Page.goto: Timeout 1000ms exceeded.")
    assert w.tab("nav-slow").shown is None
    assert (await go.run({"url": w.site.url("/")})).startswith("Tab t1 · HTTP 200")


@talking("nav-slow-reach")
async def test_a_slow_page_is_not_blamed_on_what_it_reached_for_meanwhile(w, monkeypatch):
    """A refusal ends a call only when it is what kept the page from loading."""
    monkeypatch.setattr(navigate, "LOAD_SECONDS", (1, 1, 1))
    go = build_navigate(w.kit())
    session = await w.pool.session("coach")
    mark = session.proxy.refused_total

    with pytest.raises(ToolError) as error:
        await go.run({"url": w.site.url("/anh-cham")})

    assert session.proxy.refused_since(mark) == ["127.0.0.1"]
    assert str(error.value) == t.NAV_FAILED.format(error="Page.goto: Timeout 1000ms exceeded.")
    assert w.intranet.seen == []


@talking("nav-dead-tls")
async def test_an_error_of_the_browser_is_told_without_the_address_it_names(w):
    """The address in it is one the model wrote or a page chose: neither is said again
    outside a fence."""
    go = build_navigate(w.kit())

    with pytest.raises(ToolError) as error:
        await go.run({"url": w.dead.url("/don?khoa=bi-mat").replace("http:", "https:")})

    assert str(error.value) == t.NAV_FAILED.format(
        error="Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED"
    )


class Busy:
    """A page still putting up an error page of its own: it lets itself be blanked only at
    the third try."""

    def __init__(self, failures: list[Exception]):
        self.failures, self.asked = failures, []

    async def goto(self, url: str, **how):
        self.asked.append(url)
        if self.failures:
            raise self.failures.pop(0)


class Held:
    def __init__(self, page: Busy):
        self.page, self.shown = page, None


async def test_a_tab_is_blanked_again_when_the_browser_pushed_the_blank_page_aside(monkeypatch):
    monkeypatch.setattr(navigate, "BLANK_PAUSE", 0)
    pushed = Error('Navigation to "about:blank" is interrupted by another navigation')
    twice, never, ours = Busy([pushed, pushed]), Busy([pushed] * 9), Busy([RuntimeError("x")])

    await navigate._blank(Held(twice))
    await navigate._blank(Held(never))
    with pytest.raises(RuntimeError):
        await navigate._blank(Held(ours))

    assert twice.asked == ["about:blank"] * 3
    assert never.asked == ["about:blank"] * navigate.BLANKS and ours.asked == ["about:blank"]


async def test_a_fault_of_this_program_is_not_told_as_a_page_that_failed():
    broken = Held(Busy([RuntimeError("của chương trình")]))

    with pytest.raises(RuntimeError):
        await navigate._go(None, broken, "http://shop.test/", 5, 0)

    assert broken.page.asked == ["http://shop.test/"]


@talking("nav-file")
async def test_an_address_that_would_download_a_file_downloads_nothing(w):
    go = build_navigate(w.kit())

    with pytest.raises(ToolError) as error:
        await go.run({"url": w.site.url("/tai?ten=bi-mat")})

    assert str(error.value).startswith(t.NAV_FAILED.format(error="Page.goto: "))
    assert "bi-mat" not in str(error.value) and str(w.site.port) not in str(error.value)
    assert not list((w.pool.root / "coach").rglob("a.bin"))


@talking("nav-reach")
async def test_what_a_page_reached_for_and_was_refused_is_told_inside_the_fence(w):
    go = build_navigate(w.kit())

    outside, inside = parts(await go.run({"url": w.site.url("/anh")}))

    assert t.PAGE_REFUSED.format(hosts="127.0.0.1") in inside.splitlines()
    assert "127.0.0.1" not in outside and "Có ảnh" in inside
    assert w.intranet.seen == []


async def test_an_agent_with_hosts_opens_them_unasked_and_asks_for_any_other(w):
    free, held = (
        build_navigate(w.kit()),
        build_navigate(w.kit(hosts=("shop.example", "*.cdn.example"))),
    )
    urls = {
        "in": "https://shop.example/don",
        "shout": " HTTPS://SHOP.EXAMPLE/don ",
        "under": "http://a.b.cdn.example:8080/",
        "out": "https://evil.example/shop.example",
        "alike": "https://notshop.example/",
        # A test's own server is the one private address not refused outright: asked for.
        "here": w.site.url("/"),
        # A name is refused only once it is resolved, so it is asked for as any other is.
        "inwards": "http://router.test/",
    }

    asks = {key: held.ask_when({"url": url}) for key, url in urls.items()}
    runs = {key: held.allow_when({"url": url}) for key, url in urls.items()}

    assert asks == {
        "in": None,
        "shout": None,
        "under": None,
        "out": t.ASK_NAV_OUTSIDE.format(host="evil.example"),
        "alike": t.ASK_NAV_OUTSIDE.format(host="notshop.example"),
        "here": t.ASK_NAV_OUTSIDE.format(host="127.0.0.1"),
        "inwards": t.ASK_NAV_OUTSIDE.format(host="router.test"),
    }
    assert [key for key, routine in runs.items() if routine] == ["in", "shout", "under"]
    # Without a list, a navigation is asked for like any other change and never waved through.
    assert all(free.ask_when({"url": url}) is None for url in urls.values())
    assert not any(free.allow_when({"url": url}) for url in urls.values())
    assert held.requires_approval and free.requires_approval and not free.replay_safe


async def test_nobody_is_asked_about_an_address_that_is_refused_whatever_they_say(w, deps_factory):
    """A yes would change nothing. The call goes straight to its refusal instead: for an
    agent with hosts of its own and for one with none, watched or left to itself."""
    free, held = (
        build_navigate(w.kit("never")),
        build_navigate(w.kit("never", hosts=("shop.example", "localhost"))),
    )
    private = [
        "http://10.0.0.5/",
        "http://127.0.0.1:9/",
        "http://localhost:9/api/agents",
        "http://shop.localhost/",
        "http://[::1]:8765/",
        "http://[::ffff:127.0.0.1]/",
        "http://169.254.169.254/latest/meta-data/",
    ]
    unread = [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "about:blank",
        "https://shop.example\\@evil.example/",
        "https://shop.example@evil.example/",
        "shop.example",
        "",
        ["https://shop.example/"],
    ]
    deps = deps_factory(extra_tools=[held])
    watched, alone = deps.store.create(), deps.store.create(autonomous=True)

    said = {}
    for tool in (free, held):
        for url in [*private, *unread]:
            assert tool.ask_when({"url": url}) is None, url
            assert tool.allow_when({"url": url}) is True, url
            with pytest.raises(ToolError) as error:
                await tool.run({"url": url})
            said[str(url)] = str(error.value)

    assert [said[url] for url in private] == [
        t.URL_PRIVATE.format(host=host_of(url)) for url in private
    ]
    assert said["http://localhost:9/api/agents"] == t.URL_PRIVATE.format(host="localhost")
    assert {said[str(url)] for url in unread} == {t.URL_SCHEME}
    # The gate itself: neither conversation stops for one, and both still stop for a page
    # outside the list that might be opened.
    for conv in (watched, alone):
        assert verdict(deps, conv, held.name, {"url": "http://127.0.0.1:9/"}) == RUN
        assert verdict(deps, conv, held.name, {"url": "javascript:alert(1)"}) == RUN
        assert verdict(deps, conv, held.name, {"url": "https://evil.example/"}) == ASK
    # A test's own server, reached under a name of the agent's, is opened as any of its hosts.
    assert held.allow_when({"url": w.site.url("/", host="localhost")}) is True
    assert not free.allow_when({"url": w.site.url("/", host="localhost")})
    assert w.pool.running("never") is None and w.intranet.seen == []


async def test_the_browser_is_given_the_address_as_it_was_checked(tmp_path):
    """A name in another script is spelled one way by this program and another by the
    browser: the page must be asked for under the name the rule was judged on."""
    asked: list[str] = []

    def resolver(host: str) -> list[str]:
        asked.append(host)
        return ["127.0.0.1"]

    with sites({"/": "<title>Phố</title><p>Đến nơi</p>"}) as [site]:
        async with browsers(tmp_path / "b", site, resolver=resolver) as pool:
            go = build_navigate(World(pool, site, site, {site.port}, tmp_path).kit())
            with reading_as("nav-idn"):
                answer = await go.run({"url": f"http://Straße.test:{site.port}/"})

        assert f"Địa chỉ: http://strasse.test:{site.port}/" in answer
        assert site.heads[-1]["host"] == f"strasse.test:{site.port}"
        assert {host for host in asked if host.endswith(".test")} == {"strasse.test"}
