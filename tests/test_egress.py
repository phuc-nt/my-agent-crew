"""The hosts the process calls, counted per host and per day: a host name is all that is
kept, counts gather in memory and are written in batches, old days leave, and a count that
cannot be kept never fails the call it counted."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx
import pytest

from my_agent_crew import egress
from my_agent_crew.browser.proxy import FilteringProxy
from my_agent_crew.egress import BATCH_CALLS, BATCH_SECONDS, COUNTER, INVALID, EgressCounter
from my_agent_crew.llm.anthropic import AnthropicProvider
from my_agent_crew.llm.openrouter import OpenRouterProvider
from my_agent_crew.mcp.hub import CONNECTED, McpHub
from my_agent_crew.mcp.tokens import TokenStore
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.store.egress import KEEP_DAYS
from tests.browser_servers import ask, only, sites
from tests.mcp_fakes import FakeMcp, public, server
from tests.test_browser_proxy import auth, get

DAY = "2026-03-10"
SECRET = "khoa-bi-mat"


def rows(store: Store) -> list[tuple]:
    found = store._conn.execute("SELECT * FROM egress_hosts ORDER BY day, host").fetchall()
    return [tuple(row) for row in found]


@pytest.fixture
def kept():
    """The process's counter writing to a store of this test's, on a day the test names;
    it is left as it was found, with nothing pending."""
    store = Store(":memory:")
    COUNTER.flush()
    COUNTER.bind(store.egress.add, lambda: DAY)
    yield store
    COUNTER.flush()
    COUNTER.unbind(store.egress.add)


def answering(handler=lambda request: httpx.Response(200, text="ok")) -> httpx.AsyncClient:
    return egress.counted_client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("raw", "host"),
    [
        ("API.Example.COM", "api.example.com"),
        ("example.com.", "example.com"),
        ("xn--bcher-kva.example", "xn--bcher-kva.example"),
        ("10.0.0.7", "10.0.0.7"),
        ("example.com/path?q=1", INVALID),
        ("user:pw@example.com", INVALID),
        ("2001:db8::1", INVALID),
        ("tên.vn", INVALID),
        ("a" * 254, INVALID),
        ("", INVALID),
        (None, INVALID),
        (b"example.com", INVALID),
    ],
)
def test_only_a_host_name_passes_and_anything_else_is_invalid(raw, host):
    assert egress.clean_host(raw) == host


async def test_a_request_counts_its_host_and_keeps_no_path_query_header_or_body(kept):
    async with answering() as client:
        url = f"https://API.Example.com/v1/{SECRET}?token={SECRET}"
        await client.post(url, headers={"x-key": SECRET}, content=SECRET)
        await client.get("https://api.example.com/other")
    COUNTER.flush()

    assert rows(kept) == [(DAY, "api.example.com", 2)]
    columns = [c[1] for c in kept._conn.execute("PRAGMA table_info(egress_hosts)")]
    assert columns == ["day", "host", "calls"]
    assert SECRET not in "\n".join(kept._conn.iterdump())


async def test_each_hop_of_a_redirect_counts_the_host_it_goes_to(kept):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "short.test":
            return httpx.Response(302, headers={"location": "https://long.test/there"})
        return httpx.Response(200)

    async with answering(handler) as client:
        await client.get("https://short.test/x", follow_redirects=True)
    COUNTER.flush()

    assert rows(kept) == [(DAY, "long.test", 1), (DAY, "short.test", 1)]


def test_the_store_cleans_a_host_whoever_hands_it_over():
    store = Store(":memory:")
    store.egress.add({(DAY, f"evil.test/{SECRET}?a=1"): 2, (DAY, "Fine.Test."): 1}, DAY)
    store.egress.add({(DAY, f"other.test#{SECRET}"): 1}, DAY)

    assert rows(store) == [(DAY, "fine.test", 1), (DAY, INVALID, 3)]
    with pytest.raises(ValueError):
        store.egress.add({(f"{DAY}/{SECRET}", "a.test"): 1}, DAY)
    assert rows(store) == [(DAY, "fine.test", 1), (DAY, INVALID, 3)]


def test_counts_gather_in_memory_until_a_batch_is_full():
    written: list[dict] = []
    counter = EgressCounter(clock=lambda: 0.0)
    counter.bind(lambda counts, today: written.append(counts), lambda: DAY)

    for _ in range(BATCH_CALLS - 1):
        counter.count("a.test")
    assert written == []
    counter.count("b.test")
    assert written == [{(DAY, "a.test"): BATCH_CALLS - 1, (DAY, "b.test"): 1}]
    counter.count("a.test")
    assert len(written) == 1
    counter.flush()
    assert written[1] == {(DAY, "a.test"): 1}
    counter.flush()  # nothing gathered: nothing is written
    assert len(written) == 2


def test_a_count_that_has_waited_long_enough_is_written_with_the_next_call():
    now, written = [0.0], []
    counter = EgressCounter(clock=lambda: now[0])
    counter.bind(lambda counts, today: written.append(counts), lambda: DAY)

    counter.count("a.test")
    now[0] = BATCH_SECONDS - 1
    counter.count("a.test")
    assert written == []
    now[0] = BATCH_SECONDS
    counter.count("a.test")
    assert written == [{(DAY, "a.test"): 3}]


def test_a_count_falls_on_the_day_it_was_made_not_the_day_it_is_written():
    today, written = [DAY], []
    counter = EgressCounter(clock=lambda: 0.0)
    counter.bind(lambda counts, now: written.append((counts, now)), lambda: today[0])

    counter.count("a.test")
    today[0] = "2026-03-11"
    counter.count("a.test")
    counter.flush()

    assert written == [({(DAY, "a.test"): 1, ("2026-03-11", "a.test"): 1}, "2026-03-11")]


def test_with_no_store_bound_the_tally_is_dropped_and_stays_small():
    counter = EgressCounter(clock=lambda: 0.0)
    for _ in range(BATCH_CALLS * 3 + 1):
        counter.count("a.test")
    assert counter._pending == {(egress._utc_today(), "a.test"): 1}


def test_rows_older_than_the_retention_leave_when_counts_are_written():
    store = Store(":memory:")
    today = date.fromisoformat(DAY)
    edge = (today - timedelta(days=KEEP_DAYS)).isoformat()
    gone = (today - timedelta(days=KEEP_DAYS + 1)).isoformat()
    store.egress.add({(gone, "old.test"): 4, (edge, "edge.test"): 2}, edge)
    assert len(rows(store)) == 2

    store.egress.add({(DAY, "new.test"): 1}, DAY)

    assert rows(store) == [(edge, "edge.test", 2), (DAY, "new.test", 1)]


async def test_a_count_that_cannot_be_written_does_not_fail_the_request(kept, caplog):
    kept.close()
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.egress"):
        async with answering() as client:
            for _ in range(BATCH_CALLS + 1):
                assert (await client.get("https://a.test/")).status_code == 200
        COUNTER.flush()
    assert "counts were not written" in caplog.text


async def test_a_clock_that_fails_does_not_fail_the_request(kept):
    def broken() -> str:
        raise RuntimeError("no clock")

    COUNTER.bind(kept.egress.add, broken)
    async with answering() as client:
        assert (await client.get("https://a.test/")).status_code == 200
    COUNTER.bind(kept.egress.add, lambda: DAY)
    assert rows(kept) == []


async def test_a_client_handed_in_is_used_as_it_is_and_one_made_here_counts():
    async with httpx.AsyncClient() as mine:
        assert OpenRouterProvider("k", client=mine)._client is mine
        assert AnthropicProvider("k", client=mine)._client is mine
    for provider in (OpenRouterProvider("k"), AnthropicProvider("k")):
        assert egress.count_request in provider._client.event_hooks["request"]
        await provider._client.aclose()


async def test_a_hook_the_caller_brings_is_kept_beside_the_count(kept):
    seen: list[str] = []

    async def own(request: httpx.Request) -> None:
        seen.append(request.url.host)

    transport = httpx.MockTransport(lambda request: httpx.Response(200))
    async with egress.counted_client(transport=transport, event_hooks={"request": [own]}) as c:
        await c.get("https://a.test/")
    COUNTER.flush()

    assert seen == ["a.test"] and rows(kept) == [(DAY, "a.test", 1)]


async def test_an_mcp_server_called_over_http_is_counted_by_its_host(kept):
    fake = FakeMcp()
    async with answering(fake.handle) as client:
        hub = McpHub((server(),), client, TokenStore(None, {}), public, {})
        await hub.connect()
        assert hub.links["notion"].status == CONNECTED
    COUNTER.flush()

    [(day, host, calls)] = rows(kept)
    assert (day, host) == (DAY, "mcp.example.test") and calls == len(fake.fetched)


async def test_the_browser_proxy_counts_the_host_of_a_connection_it_opens_and_no_refused_one(kept):
    names = {"shop.test": ["127.0.0.1"], "inside.test": ["127.0.0.1"]}
    with sites({"/trang": "chào"}) as [shop]:
        proxy = FilteringProxy(resolver=lambda host: names[host], allow=only(shop))
        await proxy.start()
        try:
            page = f"http://shop.test:{shop.port}/trang?khoa={SECRET}"
            assert (await ask(proxy.port, get(proxy, page))).startswith(b"HTTP/1.1 200 ")
            target = f"SHOP.test:{shop.port}".encode()
            tunnel = b"CONNECT " + target + b" HTTP/1.1\r\n" + auth(proxy) + b"\r\n"
            opened = await ask(proxy.port, tunnel, more=b"GET / HTTP/1.1\r\n\r\n", wait=0.05)
            assert opened.startswith(b"HTTP/1.1 200 ")
            refused = await ask(proxy.port, get(proxy, "http://inside.test:9/"))
            assert refused.startswith(b"HTTP/1.1 403 ")
        finally:
            await proxy.stop()
    COUNTER.flush()

    assert rows(kept) == [(DAY, "shop.test", 2)]


async def test_what_is_still_in_memory_is_written_when_the_server_stops(deps_factory):
    runtime = Runtime.single(deps_factory())
    app = create_app(runtime, schedule=False)
    today = runtime.settings.today().isoformat()
    async with app.router.lifespan_context(app):
        COUNTER.count("a.test")
        assert rows(runtime.store) == []
    assert rows(runtime.store) == [(today, "a.test", 1)]
    COUNTER.count("b.test")  # the server is gone: its store is left alone
    COUNTER.flush()
    assert rows(runtime.store) == [(today, "a.test", 1)]
