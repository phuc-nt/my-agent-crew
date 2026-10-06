"""When the crew talks to its MCP servers without being asked: once as it starts, without
letting a slow one hold it up, and again later for the ones that did not answer
(`server/mcp_lifecycle.py`, the lifespan in `server/app.py`)."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from my_agent_crew.llm.fake import completion
from my_agent_crew.mcp.config import McpServer
from my_agent_crew.server import create_app, mcp_lifecycle
from my_agent_crew.server.mcp_lifecycle import connect_at_start, retry_loop
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.runs import DONE
from tests.mcp_fakes import MCP_URL, FakeMcp, make_hub, server
from tests.queue_helpers import GatedProvider, settle_loop, until
from tests.test_mcp_turns import SEARCH, cut_while_the_server_answers, with_notion

WIKI_URL = "https://wiki.example.test/mcp"
NOTION_TOOLS = ["mcp__notion__search", "mcp__notion__create_page"]
WIKI_TOOLS = ["mcp__wiki__search", "mcp__wiki__create_page"]


class Wiki:
    """A second server at its own address. It is the same fake underneath, and it can be
    slow to answer or refuse the connection while the first one answers as usual."""

    def __init__(self, fake: FakeMcp) -> None:
        self.fake, self.slow, self.down, self.asked = fake, False, False, 0

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) != WIKI_URL:
            return await self.fake.handle(request)
        self.asked += 1
        if self.down:
            raise httpx.ConnectError("connection refused")
        if self.slow:
            await asyncio.sleep(30)
        there = httpx.Request("POST", MCP_URL, headers=request.headers, content=request.content)
        return await self.fake.handle(there)


class Door:
    """In front of the first server: each opening of a session waits here until the test
    answers it, let in or turned away. So a test decides what a try that is under way gets
    to see, and sees whether a second one came while it stood there."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.came: list[asyncio.Future[bool]] = []  # one per opening, in the order they came
        self.standing = 0
        self.most = 0  # the most openings that stood here at one time

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    async def handle(self, request: httpx.Request) -> httpx.Response:
        opening = (
            request.method == "POST"
            and str(request.url) == MCP_URL
            and json.loads(request.content).get("method") == "initialize"
        )
        if not opening:
            return await self.inner(request)
        let_in = asyncio.get_running_loop().create_future()
        self.came.append(let_in)
        self.standing += 1
        self.most = max(self.most, self.standing)
        try:
            if await let_in:
                return await self.inner(request)
            return httpx.Response(503, text="one session at a time")
        finally:
            self.standing -= 1


def crew(deps_factory, fake: FakeMcp, *servers: McpServer, script=()) -> Runtime:
    """A runtime whose one agent names every server, with nothing asked of them yet."""
    servers = servers or (server(),)
    rt = Runtime.single(deps_factory(providers={"scripted": GatedProvider(script)}))
    rt.default.profile = replace(rt.default.agent, mcp=tuple(each.name for each in servers))
    rt.mcp = make_hub(fake, *servers)
    return rt


def with_wiki(deps_factory, fake: FakeMcp) -> tuple[Runtime, Wiki]:
    rt, wiki = crew(deps_factory, fake, server(), server("wiki", url=WIKI_URL)), Wiki(fake)
    rt.mcp.client = wiki.client()
    return rt, wiki


def held(rt: Runtime) -> list[str]:
    return [name for name in rt.default.tools.names() if name.startswith("mcp__")]


def status(rt: Runtime, name: str = "notion") -> str:
    return rt.mcp.links[name].status


def retrying() -> list[asyncio.Task]:
    return [task for task in asyncio.all_tasks() if task.get_coro().__name__ == "retry_loop"]


def warned(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == mcp_lifecycle.__name__]


@pytest.fixture
def rounds(monkeypatch):
    """Runs the retry loop until it begins its wait number `count` and stops it there, so
    it has tried the servers `count - 1` times. Each wait before that is cut to a
    millisecond, and one that is woken still returns as one that was woken. Returns how
    long each wait meant to be; `at` maps the number of a wait to something done as it
    begins, and waited for when it is something to wait for."""

    async def run(rt: Runtime, count: int, at=None) -> list[float]:
        noted: list[float] = []

        async def noting(awaitable, timeout):
            noted.append(timeout)
            if len(noted) == count:
                awaitable.close()
                await asyncio.Event().wait()
            if at and len(noted) in at:
                done = at[len(noted)]()
                if inspect.isawaitable(done):
                    await done
            return await asyncio.wait_for(awaitable, 0.001)

        with monkeypatch.context() as patched:
            patched.setattr(mcp_lifecycle, "asyncio", SimpleNamespace(wait_for=noting))
            task = asyncio.create_task(retry_loop(rt))
            await until(lambda: len(noted) == count or task.done())
            assert not task.done(), task
            task.cancel()
            await settle_loop()
        return noted

    return run


async def test_starting_connects_the_servers_and_hands_their_tools_to_the_agents(deps_factory):
    rt = crew(deps_factory, FakeMcp())
    assert status(rt) == "idle" and held(rt) == []

    await connect_at_start(rt)

    assert status(rt) == "connected" and held(rt) == NOTION_TOOLS


async def test_a_crew_with_no_servers_asks_nothing_of_anyone(deps_factory, caplog):
    rt = Runtime.single(deps_factory())

    with caplog.at_level(logging.WARNING, logger=mcp_lifecycle.__name__):
        await connect_at_start(rt, limit=0)

    assert rt.mcp.links == {} and warned(caplog) == []


async def test_starting_does_not_wait_for_a_server_that_is_slow(deps_factory, caplog):
    fake = FakeMcp()
    rt, wiki = with_wiki(deps_factory, fake)
    wiki.slow = True

    with caplog.at_level(logging.WARNING, logger=mcp_lifecycle.__name__):
        await asyncio.wait_for(connect_at_start(rt, limit=0.05), 2)

    # The one that answered is in use, and the other is left as one still to be tried.
    assert (status(rt), status(rt, "wiki")) == ("connected", "idle")
    assert held(rt) == NOTION_TOOLS and rt.mcp.waiting() == ["wiki"]
    assert warned(caplog) == ["MCP servers not connected after 0.05s, trying later: wiki"]


async def test_a_server_that_is_down_at_the_start_is_one_to_try_again(deps_factory, caplog):
    rt, wiki = with_wiki(deps_factory, FakeMcp())
    wiki.down = True

    with caplog.at_level(logging.WARNING, logger=mcp_lifecycle.__name__):
        await connect_at_start(rt)

    assert (status(rt), status(rt, "wiki")) == ("connected", "failed")
    assert "connection refused" in rt.mcp.links["wiki"].error
    assert rt.mcp.waiting() == ["wiki"] and held(rt) == NOTION_TOOLS
    assert warned(caplog) == []  # it answered in time, with a no: the row says so


async def test_a_server_that_stays_down_is_tried_at_longer_and_longer_waits(deps_factory, rounds):
    fake = FakeMcp()
    rt, wiki = with_wiki(deps_factory, fake)
    wiki.down = True
    await connect_at_start(rt)
    asked, fetched = wiki.asked, len(fake.fetched)

    noted = await rounds(rt, 8)

    assert noted == [30, 60, 120, 240, 480, 600, 600, 600]
    assert wiki.asked - asked == 7  # once after each wait that ran out
    assert status(rt) == "connected" and status(rt, "wiki") == "failed"
    assert len(fake.fetched) == fetched  # the one that is up was not asked again


async def test_a_server_that_comes_back_is_connected_and_the_wait_starts_over(deps_factory, rounds):
    fake = FakeMcp()
    rt, wiki = with_wiki(deps_factory, fake)
    wiki.down = True
    await connect_at_start(rt)

    def back() -> None:
        wiki.down = False

    noted = await rounds(rt, 5, at={3: back})

    assert noted == [30, 60, 120, 30, 30]
    assert status(rt, "wiki") == "connected" and held(rt) == NOTION_TOOLS + WIKI_TOOLS
    asked = wiki.asked
    await rounds(rt, 8)
    assert wiki.asked == asked  # a server that is up is left alone


async def test_a_server_the_owner_connected_by_hand_starts_the_wait_over(deps_factory, rounds):
    """The waits grew while it was down. Connected from the screen in the middle of one,
    it leaves nothing to try, and the next server to go down is not kept waiting as long
    as the last one had been."""
    rt, wiki = with_wiki(deps_factory, FakeMcp())
    wiki.down = True
    await connect_at_start(rt)

    async def by_hand() -> None:
        wiki.down = False
        await rt.mcp.connect(["wiki"])

    noted = await rounds(rt, 5, at={3: by_hand})

    assert noted == [30, 60, 120, 30, 30] and status(rt, "wiki") == "connected"


async def test_a_key_that_changes_gets_the_server_tried_at_once(deps_factory, rounds):
    """Saving a key sets `wake` (`runtime_connections.commit`): the owner who just pasted
    the right one should not wait ten minutes to see it work."""
    rt, wiki = with_wiki(deps_factory, FakeMcp())
    wiki.down = True
    await connect_at_start(rt)
    asked = wiki.asked

    noted = await rounds(rt, 6, at={3: rt.mcp.wake.set})

    # The third wait was cut short; the next ones start over from the first.
    assert noted == [30, 60, 120, 30, 60, 120]
    assert wiki.asked - asked == 5 and not rt.mcp.wake.is_set()


async def test_being_woken_with_every_server_up_asks_nothing(deps_factory, rounds):
    fake = FakeMcp()
    rt = crew(deps_factory, fake)
    await connect_at_start(rt)
    fetched = len(fake.fetched)

    noted = await rounds(rt, 5, at={2: rt.mcp.wake.set})

    assert noted == [30, 30, 30, 30, 30] and not rt.mcp.wake.is_set()
    assert len(fake.fetched) == fetched


async def test_a_server_that_wants_a_sign_in_is_not_tried_again(deps_factory, rounds):
    """Only the owner can give it one; asking again would only be told no again."""
    fake = FakeMcp(oauth=True)
    rt = crew(deps_factory, fake)
    await connect_at_start(rt)
    assert status(rt) == "signed_out" and rt.mcp.waiting() == []
    fetched = len(fake.fetched)

    noted = await rounds(rt, 5, at={2: rt.mcp.wake.set})

    assert noted == [30, 30, 30, 30, 30] and len(fake.fetched) == fetched


async def test_a_server_the_start_did_not_wait_for_is_tried_by_the_round(deps_factory, rounds):
    """Cut off, its try let go of the server: nothing is left that keeps the next one out."""
    rt, wiki = with_wiki(deps_factory, FakeMcp())
    wiki.slow = True
    await connect_at_start(rt, limit=0.05)
    assert status(rt, "wiki") == "idle"
    wiki.slow = False

    await rounds(rt, 2)

    assert status(rt, "wiki") == "connected" and held(rt) == NOTION_TOOLS + WIKI_TOOLS


async def test_a_server_someone_is_connecting_is_not_tried_by_the_round_as_well(
    deps_factory, rounds
):
    """The owner pressed connect on a server that is slow to open a session, and the wait
    ran out while it did. Tried again under that try, the server is told of two sessions for
    one press, and the row is left as whichever of the two ended last."""
    fake = FakeMcp()
    rt = crew(deps_factory, fake)
    door = Door(fake.handle)
    rt.mcp.client = door.client()
    by_hand = asyncio.create_task(rt.mcp.connect(["notion"]))
    await until(lambda: len(door.came) == 1)
    assert status(rt) == "idle"  # down as far as its row says, and not for the round to try

    noted = await rounds(rt, 3)

    assert noted == [30, 30, 30] and len(door.came) == 1
    door.came[0].set_result(True)
    await by_hand
    rt.mcp.attach(rt.agents)
    assert status(rt) == "connected" and held(rt) == NOTION_TOOLS
    assert fake.methods().count("initialize") == 1


async def test_a_server_is_spoken_for_from_the_moment_a_connect_is_asked_for(deps_factory):
    """The round may look at who is waiting in the very turn of the loop a press came in,
    before that press has got as far as trying the server."""
    fake = FakeMcp()
    rt = crew(deps_factory, fake)
    assert rt.mcp.waiting() == ["notion"]

    by_hand = asyncio.create_task(rt.mcp.connect(["notion"]))
    await asyncio.sleep(0)  # asked for, and nothing sent yet

    assert fake.fetched == [] and rt.mcp.waiting() == []
    await by_hand
    assert status(rt) == "connected" and rt.mcp.waiting() == []


async def test_the_round_tries_the_other_servers_while_one_is_being_connected(deps_factory, rounds):
    fake = FakeMcp()
    rt, wiki = with_wiki(deps_factory, fake)
    wiki.down = True
    await connect_at_start(rt)
    door = Door(wiki.handle)
    rt.mcp.client = door.client()
    by_hand = asyncio.create_task(rt.mcp.connect(["notion"]))
    await until(lambda: len(door.came) == 1)
    wiki.down = False

    await rounds(rt, 2)

    assert status(rt, "wiki") == "connected" and len(door.came) == 1
    door.came[0].set_result(True)
    await by_hand
    rt.mcp.attach(rt.agents)
    assert held(rt) == NOTION_TOOLS + WIKI_TOOLS


@pytest.mark.parametrize(
    ("first", "second", "stands", "holds"),
    [(True, False, "failed", []), (False, True, "connected", NOTION_TOOLS)],
    ids=["then-refused", "then-let-in"],
)
async def test_a_server_asked_for_again_is_tried_after_the_try_under_way(
    deps_factory, first, second, stands, holds
):
    """Two tries at once leave the session and tools of the one that worked under the word
    of the one that did not. The one asked for later waits its turn and then tries afresh,
    not taking the answer the first one got: it may have been asked for because a key or a
    sign-in changed after the first one began. The server stands as the later one left it."""
    fake = FakeMcp()
    rt = crew(deps_factory, fake)
    door = Door(fake.handle)
    rt.mcp.client = door.client()
    link = rt.mcp.links["notion"]
    earlier = asyncio.create_task(rt.mcp.connect(["notion"]))
    await until(lambda: len(door.came) == 1)
    later = asyncio.create_task(rt.mcp.connect(["notion"]))
    await settle_loop()
    assert len(door.came) == 1 and not later.done()

    door.came[0].set_result(first)
    await earlier
    await until(lambda: len(door.came) == 2)
    door.came[1].set_result(second)
    await later

    rt.mcp.attach(rt.agents)
    assert door.most == 1
    assert (link.status, link.session is not None, held(rt)) == (stands, bool(holds), holds)
    assert bool(link.error) == (stands == "failed")
    assert rt.mcp.waiting() == ([] if holds else ["notion"])


async def test_the_served_app_connects_its_servers_before_it_takes_up_a_cut_turn(
    served, deps_factory
):
    """The turn was cut in a call to a tool that only reads, so it is made again, and for
    that the tool has to be there when the turn is looked at."""
    first, fake = await with_notion(served, [completion(tool_calls=[SEARCH])], read_only=["search"])
    conv = first.conv
    await cut_while_the_server_answers(first, fake)

    again = server(read_only=["search"])
    second = crew(deps_factory, fake, again, script=[completion("Có một trang.")])
    assert status(second) == "idle" and held(second) == []
    app = create_app(second, schedule=True)
    async with app.router.lifespan_context(app):
        await until(lambda: not second.hub.busy.busy(conv.id) and fake.calls != [])
        run = second.store.runs.latest_for_conversation(conv.id)
        await until(lambda: not second.hub.busy.busy(conv.id))

    assert run is not None and run.resumed is True
    assert fake.calls == [("search", {"query": "kế hoạch"})]
    stored = [(m.message.role, m.message.content) for m in second.store.history(conv.id)]
    assert stored[-2:] == [("tool", "ran search"), ("assistant", "Có một trang.")]
    assert second.store.runs.latest_for_conversation(conv.id).status == DONE


async def test_the_served_app_keeps_trying_its_servers_only_while_it_serves(deps_factory):
    rt = crew(deps_factory, FakeMcp())
    app = create_app(rt, schedule=True)

    async with app.router.lifespan_context(app):
        assert status(rt) == "connected" and held(rt) == NOTION_TOOLS
        assert len(retrying()) == 1
    await settle_loop()

    assert retrying() == []


async def test_an_app_with_no_servers_starts_nothing_to_try_them(deps_factory):
    app = create_app(Runtime.single(deps_factory()), schedule=True)

    async with app.router.lifespan_context(app):
        assert retrying() == []


async def test_an_app_that_schedules_nothing_does_not_reach_for_its_servers(deps_factory):
    """What tests and embedders build: nothing is fetched until someone asks."""
    fake = FakeMcp()
    rt = crew(deps_factory, fake)
    app = create_app(rt, schedule=False)

    async with app.router.lifespan_context(app):
        await settle_loop()
        assert retrying() == []

    assert fake.fetched == [] and status(rt) == "idle"
