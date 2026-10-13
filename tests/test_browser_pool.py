"""The browsers of the crew: one an agent, started at its first call, stopped when idle, each
behind a proxy of its own."""

from __future__ import annotations

import asyncio
import stat

import pytest

from my_agent_crew.browser import pool as pool_module
from my_agent_crew.browser.proxy import FilteringProxy
from tests.browser_servers import Clock, browsers, sites

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
        async with pool.hold("coach") as session:
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


async def test_the_gate_reads_a_tab_without_starting_anything(tmp_path):
    async with browsers(tmp_path / "browser") as pool:
        assert pool.peek("coach", "c1") is None and pool.running("coach") is None
        session = await pool.session("coach")
        tab = await session.tabs.open("c1", "gio")

        assert pool.peek("coach", "c1") is tab and pool.peek("coach", "c1", "gio") is tab
        assert pool.peek("coach", "c2") is None and pool.peek("coach", "c1", "khac") is None
        assert pool.peek("ledger", "c1") is None and pool.running("ledger") is None
