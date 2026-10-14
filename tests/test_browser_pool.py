"""The browsers of the crew: one an agent, started at its first call, stopped when idle, each
behind a proxy of its own."""

from __future__ import annotations

import asyncio
import stat

import pytest

from my_agent_crew.browser import launch as launch_module
from my_agent_crew.browser import pool as pool_module
from my_agent_crew.browser.proxy import FilteringProxy
from my_agent_crew.browser.session import Session
from tests.browser_servers import Clock, browsers, local_names, sites

SHOP = {
    "/": "<title>Cửa hàng</title><h1>Cửa hàng</h1>",
    "/cookie": lambda site: (
        200,
        {"set-cookie": "cart=3; Max-Age=3600; Path=/"},
        "<title>Đã ghi</title>",
    ),
}


async def test_nothing_is_started_until_an_agent_asks_and_then_it_has_a_profile_of_its_own(
    tmp_path,
):
    async with browsers(tmp_path / "browser") as pool:
        assert pool.running("coach") is None and not (tmp_path / "browser").exists()

        session = await pool.session("coach")

        assert pool.running("coach") is session
        assert pool.running("ledger") is None
        profile = tmp_path / "browser" / "coach"
        assert profile.is_dir() and stat.S_IMODE(profile.stat().st_mode) == 0o700
        assert session.context.browser.version.split(".")[0].isdigit()
        assert len(session.context.pages) == 1 and session.tabs.all() == []


async def test_two_calls_at_once_wait_for_one_browser(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        first, second = await asyncio.gather(pool.session("coach"), pool.session("coach"))

        assert first is second
        assert await pool.session("coach") is first


async def test_what_one_agent_is_logged_in_to_is_not_anothers_and_stays_over_a_restart(tmp_path):
    with sites(SHOP) as (shop,):
        async with browsers(tmp_path / "browser", shop) as pool:
            mine, yours = await pool.session("purchases"), await pool.session("coach")
            assert mine is not yours and mine.proxy.port != yours.proxy.port
            tab = await mine.tabs.open("c1")
            await tab.page.goto(shop.url("/cookie"))

            assert [c["name"] for c in await mine.context.cookies()] == ["cart"]
            assert await yours.context.cookies() == []

            assert await pool.stop("purchases") is True
            assert pool.running("purchases") is None and pool.running("coach") is yours
            again = await pool.session("purchases")
            assert again is not mine
            assert [c["value"] for c in await again.context.cookies()] == ["3"]


async def test_a_browser_reaches_a_site_only_through_its_proxy(tmp_path):
    with sites(SHOP, {"/": "<title>Bộ định tuyến</title>"}) as (shop, router):
        async with browsers(tmp_path / "browser", shop) as pool:
            session = await pool.session("coach")
            tab = await session.tabs.open("c1")

            reached = await tab.page.goto(shop.url("/"))
            title = await tab.page.title()
            refused = await tab.page.goto(router.url("/"))

            assert reached.status == 200 and title == "Cửa hàng"
            assert refused.status == 403 and router.seen == []
            assert session.proxy.refused_since(0) == ["127.0.0.1"]
            assert await tab.page.evaluate(
                "url => fetch(url).then(r => r.status, () => 'failed')", router.url("/")
            ) in (403, "failed")
            assert router.seen == []


async def test_loopback_goes_through_the_proxy_whatever_the_driver_was_told(tmp_path, monkeypatch):
    # The driver puts loopback behind the proxy by itself unless this is set: the rule must
    # not hang on a variable of the environment.
    monkeypatch.setenv("PLAYWRIGHT_DISABLE_FORCED_CHROMIUM_PROXIED_LOOPBACK", "1")
    with sites({"/": "<title>Bộ định tuyến</title>"}) as (router,):
        async with browsers(tmp_path / "browser") as pool:
            tab = await (await pool.session("coach")).tabs.open("c1")

            by_address = await tab.page.goto(router.url("/"))
            by_name = await tab.page.goto(router.url("/", host="localhost"))

            assert (by_address.status, by_name.status) == (403, 403) and router.seen == []


async def test_a_browser_nobody_used_for_a_while_is_stopped_and_the_next_call_starts_it_again(
    tmp_path,
):
    clock = Clock()
    async with browsers(tmp_path / "browser", clock=clock, idle_minutes=10) as pool:
        first = await pool.session("coach")
        clock.now = 599
        assert await pool.reap() == [] and pool.running("coach") is first

        clock.now = 600

        assert await pool.reap() == ["coach"] and pool.running("coach") is None
        assert first.context.pages == []
        assert await pool.session("coach") is not first


async def test_a_browser_a_call_is_using_is_not_stopped_and_its_idle_time_starts_after_it(
    tmp_path,
):
    clock = Clock()
    async with browsers(tmp_path / "browser", clock=clock, idle_minutes=1) as pool:
        async with pool.hold(await pool.session("coach")) as session:
            clock.now = 500
            assert await pool.reap() == [] and pool.running("coach") is session
        assert session.busy == 0

        clock.now = 559
        assert await pool.reap() == []
        clock.now = 560
        assert await pool.reap() == ["coach"]


async def test_only_the_idle_browser_is_stopped_and_the_others_lose_their_cold_tabs(tmp_path):
    clock = Clock()
    async with browsers(tmp_path / "browser", clock=clock, idle_minutes=30) as pool:
        idle, used = await pool.session("coach"), await pool.session("ledger")
        cold, warm = await used.tabs.open("c1"), await used.tabs.open("c2")
        clock.now = 1800
        used.tabs.touch(warm)
        clock.now = 3599
        used.used = 3000

        assert await pool.reap() == ["coach"] and idle.context.pages == []
        assert pool.running("ledger") is used
        assert used.tabs.all() == [warm] and cold.page.is_closed()


async def test_a_start_that_failed_leaves_no_place_taken(tmp_path):
    (tmp_path / "browser").write_text("a file where the profiles should be")
    async with browsers(tmp_path / "browser") as pool:
        with pytest.raises(OSError):
            await pool.session("coach")
        assert pool.running("coach") is None

        (tmp_path / "browser").unlink()

        assert pool.running("coach") is None
        assert (await pool.session("coach")).context.pages


@pytest.mark.parametrize("agent_id", ["", ".", "..", "../coach", "a/b"])
async def test_a_name_that_is_no_agent_id_starts_nothing(tmp_path, agent_id):
    async with browsers(tmp_path / "browser") as pool:
        with pytest.raises(ValueError):
            await pool.session(agent_id)

        assert (
            not (tmp_path / "browser").exists() and not tmp_path.parent.joinpath("coach").exists()
        )


async def test_a_browser_that_went_away_by_itself_is_forgotten_and_started_again(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        first = await pool.session("coach")
        port = first.proxy.port

        await first.context.close()
        await asyncio.sleep(0.1)

        assert pool.running("coach") is None
        with pytest.raises(OSError):
            await asyncio.open_connection("127.0.0.1", port)
        assert await pool.session("coach") is not first


async def test_a_call_that_arrives_while_its_browser_is_stopping_waits_until_it_is_gone(
    tmp_path, monkeypatch
):
    order: list[str] = []

    class Watched(FilteringProxy):
        async def start(self) -> None:
            order.append("starting")
            await super().start()

    async with browsers(tmp_path / "browser") as pool:
        first = await pool.session("coach")
        monkeypatch.setattr(pool_module, "FilteringProxy", Watched)
        gone, close = asyncio.Event(), first.close

        async def slowly() -> None:
            await gone.wait()
            await close()
            order.append("closed")

        first.close = slowly
        stopping = asyncio.ensure_future(pool.stop("coach"))
        asking = asyncio.ensure_future(pool.session("coach"))
        await asyncio.sleep(0.2)
        waited = (list(order), asking.done(), pool.running("coach"))
        gone.set()
        fresh = await asking

        # Two browsers on one profile would fight over it: the new one waited.
        assert waited == ([], False, None)

        assert order == ["closed", "starting"] and fresh is not first
        assert await stopping is True and pool.running("coach") is fresh
        assert (await fresh.tabs.open("c1")).label == "t1"


async def test_a_stop_that_comes_before_a_start_took_its_first_step_stops_that_browser(tmp_path):
    """The place is taken when a browser is asked for, and the start runs a turn later. A stop
    in between waits for that start; the start must not wait for the stop in its turn."""
    async with browsers(tmp_path / "browser") as pool:
        asking = asyncio.ensure_future(pool.session("coach"))
        await asyncio.sleep(0)
        assert pool.running("coach") is None and not asking.done()

        async with asyncio.timeout(30):
            assert await pool.stop("coach") is True
            session = await asking

        assert pool.running("coach") is None and session.context.pages == []
        with pytest.raises(OSError):
            await asyncio.open_connection("127.0.0.1", session.proxy.port)
        async with asyncio.timeout(30):
            again = await pool.session("coach")
        assert again is not session and pool.running("coach") is again
        assert (await again.tabs.open("c1")).label == "t1"


async def test_everything_stops_while_a_browser_is_still_starting(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        up = await pool.session("ledger")
        asking = asyncio.ensure_future(pool.session("coach"))
        await asyncio.sleep(0)

        async with asyncio.timeout(30):
            await pool.stop_all()
            session = await asking

        assert pool.running("coach") is None and pool.running("ledger") is None
        assert session.context.pages == [] and up.context.pages == []


async def test_a_second_stop_waits_for_the_first_and_says_it_stopped_nothing(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        session = await pool.session("coach")
        gone, close, order = asyncio.Event(), session.close, []

        async def slowly() -> None:
            await gone.wait()
            await close()
            order.append("closed")

        session.close = slowly
        first = asyncio.ensure_future(pool.stop("coach"))
        second = asyncio.ensure_future(pool.stop("coach"))
        other = asyncio.ensure_future(pool.stop("ledger"))
        await asyncio.sleep(0.2)
        # Whoever is told it is stopped may take the profile folder away: not before it is.
        waited = (first.done(), second.done(), other.done(), list(order))
        gone.set()

        assert await second is False and order == ["closed"]
        assert waited == (False, False, True, [])
        assert await first is True and await other is False
        assert await pool.stop("coach") is False


async def test_stopping_an_agent_that_has_no_browser_does_nothing(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        assert await pool.stop("coach") is False
        assert pool.peek("coach", "c1") is None


async def test_everything_stops_together_and_a_later_call_starts_afresh(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        one, two = await pool.session("coach"), await pool.session("ledger")
        ports = [one.proxy.port, two.proxy.port]

        await pool.stop_all()

        assert pool.running("coach") is None and pool.running("ledger") is None
        assert one.context.pages == [] and two.context.pages == []
        for port in ports:
            with pytest.raises(OSError):
                await asyncio.open_connection("127.0.0.1", port)
        assert (await pool.session("coach")).context.pages


async def test_a_pool_that_was_shut_starts_no_browser(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        up = await pool.session("coach")
        pool.shut = True

        # A browser that is up stays the agent's until everything stops.
        assert await pool.session("coach") is up
        with pytest.raises(RuntimeError, match="the server is stopping"):
            await pool.session("ledger")
        assert pool.running("ledger") is None
        assert not (tmp_path / "browser" / "ledger").exists()

        await pool.stop_all()

        with pytest.raises(RuntimeError, match="the server is stopping"):
            await pool.session("coach")
        assert pool.running("coach") is None and up.context.pages == []


async def test_a_pool_starts_browsers_until_it_is_shut(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        assert pool.shut is False
        await pool.stop_all()
        # Stopping everything is not the end: only the server going down is.
        assert pool.shut is False


async def test_the_gate_reads_a_tab_without_starting_anything(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        assert pool.peek("coach", "c1") is None and pool.running("coach") is None
        session = await pool.session("coach")
        tab = await session.tabs.open("c1", "gio")

        assert pool.peek("coach", "c1") is tab and pool.peek("coach", "c1", "gio") is tab
        assert pool.peek("coach", "c2") is None and pool.peek("coach", "c1", "khac") is None
        assert pool.peek("ledger", "c1") is None and pool.running("ledger") is None


async def test_a_browser_runs_no_errand_of_its_own(tmp_path):
    """Chromium opens a connection to a search engine at every page, describes the forms of a
    page to its autofill service, and calls its sign-in and push services at start. None of
    that is the crew's: the first two are off, the others are sent to names that resolve
    nowhere."""
    asked: list[str] = []

    def resolver(host: str) -> list[str]:
        asked.append(host)
        return ["127.0.0.1"]

    form = (
        "<title>Trang</title><form action=/gui><input name=email type=email autocomplete=email>"
        "<input name=password type=password><input name=card autocomplete=cc-number>"
        "<input name=address autocomplete=street-address><button>Gửi</button></form>"
    )
    with sites({"/": form}) as (site,):
        async with browsers(tmp_path / "browser", site, resolver=resolver) as pool:
            tab = await (await pool.session("coach")).tabs.open("c1")
            await tab.page.goto(site.url("/"))
            await asyncio.sleep(2.5)

    assert {host for host in asked if not host.endswith(".invalid")} == {"127.0.0.1"}


async def test_a_browser_that_never_answers_a_close_still_gives_up_its_proxy(monkeypatch):
    """Its driver went away while it was up: the way out it was given is not left answering."""
    monkeypatch.setattr(launch_module, "CLOSE_SECONDS", 0.05)

    class Deaf:
        async def close(self) -> None:
            await asyncio.Event().wait()

    proxy = FilteringProxy(local_names, None)
    await proxy.start()
    port = proxy.port
    session = Session("coach", Deaf(), proxy, None, 0.0)

    async with asyncio.timeout(5):
        await session.close()

    with pytest.raises(OSError):
        await asyncio.open_connection("127.0.0.1", port)
