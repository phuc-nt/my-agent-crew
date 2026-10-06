"""One session with an MCP server over streamable HTTP: what is sent, how an answer is
read whichever of the two ways the server gives it, and what a server that misbehaves
costs the turn that called it (`mcp/wire.py`, `mcp/session.py`)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp import wire
from my_agent_crew.mcp.session import VERSIONS, McpSession
from my_agent_crew.mcp.wire import McpError, Unauthorized
from tests.mcp_fakes import CREATE, MCP_URL, SEARCH, FakeMcp, server

OPENED = {"protocolVersion": VERSIONS[0], "capabilities": {"tools": {}}}


def session_for(fake: FakeMcp, headers=None, renew=None, **settings) -> McpSession:
    return McpSession(server(**settings), fake.client(), lambda: dict(headers or {}), renew)


@pytest.mark.parametrize("sse", [False, True], ids=["one JSON body", "an event stream"])
async def test_a_session_opens_lists_tools_and_calls_one_however_the_server_answers(sse):
    fake = FakeMcp(sse=sse)
    session = session_for(fake)

    await session.start()
    tools = await session.list_tools()
    result = await session.call_tool("search", {"query": "kế hoạch"})

    assert [tool["name"] for tool in tools] == ["search", "create-page"]
    assert result == {"content": [{"type": "text", "text": "ran search"}]}
    assert fake.methods() == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]
    assert fake.calls == [("search", {"query": "kế hoạch"})]
    opened = fake.seen[0].message
    assert opened["params"]["protocolVersion"] == VERSIONS[0]
    assert opened["params"]["clientInfo"]["name"] == "my-agent-crew"
    # Opening names no session; everything after it names the one the server gave.
    assert "mcp-session-id" not in fake.seen[0].headers
    for later in fake.seen[1:]:
        assert later.headers["mcp-session-id"] == "s1"
        assert later.headers["mcp-protocol-version"] == "2025-06-18"
        assert later.headers["accept"] == "application/json, text/event-stream"
    # A notification has no id, so nothing is waited for; every request has its own.
    assert "id" not in fake.seen[1].message
    ids = [seen.message["id"] for seen in fake.seen if "id" in seen.message]
    assert len(set(ids)) == len(ids) == 3


async def test_the_configured_headers_are_read_again_for_every_request():
    fake, key = FakeMcp(), {"Authorization": "Bearer first"}
    session = McpSession(server(), fake.client(), lambda: dict(key))

    await session.start()
    key["Authorization"] = "Bearer second"
    await session.call_tool("search", {})

    assert fake.seen[0].headers["authorization"] == "Bearer first"
    assert fake.seen[-1].headers["authorization"] == "Bearer second"


async def test_tools_are_listed_page_by_page_until_the_server_names_no_more():
    extra = [{"name": f"tool-{n}", "inputSchema": {"type": "object"}} for n in range(3)]
    fake = FakeMcp([SEARCH, CREATE, *extra])
    fake.page_size = 2
    session = session_for(fake)
    await session.start()

    tools = await session.list_tools()

    assert [tool["name"] for tool in tools] == [
        "search",
        "create-page",
        "tool-0",
        "tool-1",
        "tool-2",
    ]
    cursors = [(s.message.get("params") or {}).get("cursor") for s in fake.seen[2:]]
    assert cursors == [None, "2", "4"]


async def test_what_is_not_a_tool_in_the_list_is_left_out():
    fake = FakeMcp([SEARCH, "nonsense", 7, None, CREATE])
    session = session_for(fake)
    await session.start()

    assert await session.list_tools() == [SEARCH, CREATE]


async def test_a_server_that_never_stops_paging_is_stopped(monkeypatch):
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    endless = {"tools": [SEARCH], "nextCursor": "again"}
    fake.before = lambda request, message: (
        httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": endless})
        if message.get("method") == "tools/list"
        else None
    )

    tools = await session.list_tools()

    assert len(tools) == 20 and fake.methods().count("tools/list") == 20


async def test_a_session_the_server_forgot_is_opened_again_and_the_call_made_once():
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    fake.live.clear()  # the server restarted

    result = await session.call_tool("create-page", {"title": "Báo cáo"})

    assert result["content"][0]["text"] == "ran create-page"
    # The refused request never ran, so making it again after reopening is the first time.
    assert fake.calls == [("create-page", {"title": "Báo cáo"})]
    assert fake.sessions == ["s1", "s2"]
    assert fake.seen[-1].headers["mcp-session-id"] == "s2"


async def test_calls_that_learn_together_the_session_is_gone_open_one_between_them():
    """Each new session ends the one before it at the server: a second one opened for the
    second call would take the first call's away again."""
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    fake.live.clear()
    fake.delay = 0.01  # both are on their way before either is told

    results = await asyncio.gather(
        session.call_tool("search", {"query": "a"}),
        session.call_tool("search", {"query": "b"}),
    )

    assert [r["content"][0]["text"] for r in results] == ["ran search"] * 2
    assert fake.sessions == ["s1", "s2"]
    assert sorted(arguments["query"] for _, arguments in fake.calls) == ["a", "b"]


async def test_a_call_made_while_the_session_is_being_opened_again_waits_for_it():
    """Sent at that moment it would name no session at all, and be refused for that."""
    fake = FakeMcp()
    waiting: list[asyncio.Task] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        opening = b'"initialize"' in request.content and len(fake.sessions) == 1
        if opening and not waiting:
            waiting.append(asyncio.ensure_future(session.call_tool("search", {"query": "b"})))
            await asyncio.sleep(0)  # the second call gets as far as it can
        return await fake.handle(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    session = McpSession(server(), client, dict)
    await session.start()
    fake.live.clear()

    first = await session.call_tool("search", {"query": "a"})
    [second] = await asyncio.gather(*waiting)

    assert first["content"][0]["text"] == second["content"][0]["text"] == "ran search"
    assert fake.sessions == ["s1", "s2"]
    named = [
        seen.headers.get("mcp-session-id") for seen in fake.seen if seen.method == "tools/call"
    ]
    assert named == ["s1", "s2", "s2"]


async def test_a_server_that_forgets_every_session_fails_the_call_instead_of_looping():
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    fake.before = lambda request, message: (
        httpx.Response(404, text="gone") if message.get("method") == "tools/call" else None
    )

    with pytest.raises(McpError, match="đã bỏ phiên"):
        await session.call_tool("search", {})

    assert fake.methods().count("tools/call") == 2 and fake.methods().count("initialize") == 2


def refusing_once(method: str):
    """Answers the first `method` it sees with a server that is still starting."""
    refused: list[str] = []

    def before(request: httpx.Request, message: dict) -> httpx.Response | None:
        if message.get("method") != method or refused:
            return None
        refused.append(method)
        return httpx.Response(503, text="starting")

    return before


async def test_a_session_that_could_not_be_opened_again_is_opened_by_the_next_call():
    """The server restarted and was not ready when the session was opened again. Sent with
    no session at all, every later call would be refused for a reason nothing here reads
    as "open one", and the server would stay unusable until someone reconnected it."""
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    fake.live.clear()  # the server restarted
    fake.before = refusing_once("initialize")

    with pytest.raises(McpError, match="HTTP 503"):
        await session.call_tool("search", {"query": "a"})
    result = await session.call_tool("search", {"query": "b"})

    assert result["content"][0]["text"] == "ran search"
    assert fake.calls == [("search", {"query": "b"})]
    assert fake.sessions == ["s1", "s2"]
    assert fake.seen[-1].headers["mcp-session-id"] == "s2"
    # The call that found no session open did not go out before one was.
    assert fake.methods()[-3:] == ["initialize", "notifications/initialized", "tools/call"]


async def test_a_call_waiting_behind_an_opening_that_failed_opens_the_session_itself():
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    fake.live.clear()
    fake.delay = 0.01  # both are on their way before either is told
    fake.before = refusing_once("initialize")

    results = await asyncio.gather(
        session.call_tool("search", {"query": "a"}),
        session.call_tool("search", {"query": "b"}),
        return_exceptions=True,
    )

    failed = [r for r in results if isinstance(r, Exception)]
    assert len(failed) == 1 and "HTTP 503" in str(failed[0])
    assert fake.sessions == ["s1", "s2"] and len(fake.calls) == 1


async def test_a_session_the_server_was_never_told_is_ready_is_not_used():
    """A server may refuse everything in a session until it hears `initialized`."""
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    fake.live.clear()
    fake.before = refusing_once("notifications/initialized")

    with pytest.raises(McpError, match="HTTP 503"):
        await session.call_tool("search", {})
    result = await session.call_tool("search", {})

    assert result["content"][0]["text"] == "ran search"
    assert fake.sessions == ["s1", "s2", "s3"]
    assert fake.seen[-1].headers["mcp-session-id"] == "s3"


async def test_a_call_stopped_while_its_session_was_being_opened_leaves_none_half_open():
    """The owner stops a turn at any moment, this one included."""
    fake = FakeMcp()
    reached = asyncio.Event()

    async def handle(request: httpx.Request) -> httpx.Response:
        if b"notifications/initialized" in request.content and len(fake.sessions) == 2:
            reached.set()
            await asyncio.sleep(3600)
        return await fake.handle(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    session = McpSession(server(), client, dict)
    await session.start()
    fake.live.clear()

    stopped = asyncio.ensure_future(session.call_tool("search", {"query": "a"}))
    await reached.wait()
    stopped.cancel()
    await asyncio.gather(stopped, return_exceptions=True)
    result = await session.call_tool("search", {"query": "b"})

    assert stopped.cancelled() and result["content"][0]["text"] == "ran search"
    assert fake.sessions == ["s1", "s2", "s3"]
    assert fake.seen[-1].headers["mcp-session-id"] == "s3"


async def test_a_server_that_keeps_no_session_is_not_opened_again_for_every_call():
    fake = FakeMcp()
    fake.before = lambda request, message: (
        httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": OPENED})
        if message.get("method") == "initialize"
        else httpx.Response(202)
        if message.get("method") == "notifications/initialized"
        else httpx.Response(
            200, json={"jsonrpc": "2.0", "id": message["id"], "result": {"content": []}}
        )
    )
    session = session_for(fake)
    await session.start()

    await session.call_tool("search", {})
    await session.call_tool("search", {})

    assert fake.methods().count("initialize") == 1
    assert all("mcp-session-id" not in seen.headers for seen in fake.seen)


async def test_a_call_on_a_session_never_started_opens_it_first():
    fake = FakeMcp()
    session = session_for(fake)

    result = await session.call_tool("search", {})

    assert result["content"][0]["text"] == "ran search"
    assert fake.methods() == ["initialize", "notifications/initialized", "tools/call"]


async def test_a_ping_from_the_server_is_answered_while_the_call_waits():
    fake = FakeMcp(sse=True)
    fake.ping = True
    session = session_for(fake)
    await session.start()

    result = await session.call_tool("search", {})

    assert result["content"][0]["text"] == "ran search"
    assert fake.answers == [{"jsonrpc": "2.0", "id": "server-1", "result": {}}]


async def test_anything_else_the_server_asks_for_is_declined():
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    asked = {"jsonrpc": "2.0", "id": 99, "method": "sampling/createMessage", "params": {}}

    def answer_with_a_request_first(request, message):
        if message.get("method") != "tools/call":
            return None
        done = {"jsonrpc": "2.0", "id": message["id"], "result": {"content": []}}
        return httpx.Response(200, json=[asked, done])

    fake.before = answer_with_a_request_first

    assert await session.call_tool("search", {}) == {"content": []}
    [declined] = fake.answers
    assert declined["id"] == 99 and declined["error"]["code"] == -32601


async def test_what_the_server_only_tells_is_given_no_answer():
    """A notification has no id to answer to; only a request is replied to."""
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()
    told = {"jsonrpc": "2.0", "method": "notifications/progress", "params": {"progress": 1}}

    def answer_after_telling(request, message):
        if message.get("method") != "tools/call":
            return None
        done = {"jsonrpc": "2.0", "id": message["id"], "result": {"content": []}}
        return httpx.Response(200, json=[told, done])

    fake.before = answer_after_telling

    assert await session.call_tool("search", {}) == {"content": []}
    assert fake.answers == []


async def test_an_event_stream_that_ends_without_a_blank_line_still_gives_its_answer():
    fake = FakeMcp()
    session = session_for(fake)
    await session.start()

    def unfinished_stream(request, message):
        if message.get("method") != "tools/call":
            return None
        body = f'data: {{"jsonrpc":"2.0","id":{message["id"]},"result":{{"content":[]}}}}'
        return httpx.Response(200, content=body, headers={"Content-Type": "text/event-stream"})

    fake.before = unfinished_stream

    assert await session.call_tool("search", {}) == {"content": []}


def answering(response_for) -> FakeMcp:
    """A server that opens a session as usual and answers a tool call with `response_for`."""
    fake = FakeMcp()
    fake.before = lambda request, message: (
        response_for(message) if message.get("method") == "tools/call" else None
    )
    return fake


@pytest.mark.parametrize(
    ("response_for", "said"),
    [
        (lambda m: httpx.Response(500, text="  boom  "), "trả về HTTP 500: boom."),
        (lambda m: httpx.Response(503), "trả về HTTP 503."),
        (lambda m: httpx.Response(200, text="<html>"), "không đúng giao thức"),
        (lambda m: httpx.Response(200, json={"jsonrpc": "2.0", "id": 0, "result": {}}), "đóng kết"),
        (
            lambda m: httpx.Response(
                200, json={"jsonrpc": "2.0", "id": m["id"], "error": {"message": "no such page"}}
            ),
            "báo lỗi: no such page",
        ),
        (
            lambda m: httpx.Response(200, json={"jsonrpc": "2.0", "id": m["id"], "result": []}),
            "không đúng giao thức",
        ),
        (
            lambda m: httpx.Response(
                200, content=b": nothing\n\n", headers={"Content-Type": "text/event-stream"}
            ),
            "đóng kết nối mà không trả lời",
        ),
    ],
    ids=[
        "an error status with a body",
        "an error status alone",
        "a body that is not JSON",
        "an answer to some other request",
        "a JSON-RPC error",
        "a result that is not an object",
        "a stream with no answer in it",
    ],
)
async def test_a_bad_answer_is_an_error_the_model_can_read(response_for, said):
    fake = answering(response_for)
    session = session_for(fake)
    await session.start()

    with pytest.raises(McpError) as failure:
        await session.call_tool("search", {})

    assert said in str(failure.value) and "notion" in str(failure.value)
    assert fake.methods().count("tools/call") == 1  # never made a second time


async def test_a_redirect_is_refused_not_followed():
    """A key sent to wherever a server points would be a key sent to anyone."""
    elsewhere = "https://elsewhere.example.test/mcp"
    fake = answering(lambda m: httpx.Response(307, headers={"Location": elsewhere}))
    session = session_for(fake, headers={"Authorization": "Bearer secret"})
    await session.start()

    with pytest.raises(McpError, match="chuyển hướng"):
        await session.call_tool("search", {})

    assert all(url == MCP_URL for _, url in fake.fetched)


async def test_an_answer_too_large_to_hold_is_cut_off_while_it_arrives(monkeypatch):
    monkeypatch.setattr(wire, "MAX_ANSWER_BYTES", 1000)
    big = {"content": [{"type": "text", "text": "x" * 5000}]}
    fake = FakeMcp()
    fake.results["search"] = big
    session = session_for(fake)
    await session.start()

    with pytest.raises(McpError, match="quá nhiều dữ liệu"):
        await session.call_tool("search", {})

    fake.sse = True
    with pytest.raises(McpError, match="quá nhiều dữ liệu"):
        await session.call_tool("search", {})


async def test_a_server_that_does_not_answer_in_time_fails_the_call():
    fake = FakeMcp()
    session = session_for(fake, timeout=0.05)
    await session.start()
    fake.delay = 5.0

    with pytest.raises(McpError) as failure:
        await session.call_tool("search", {})

    assert str(failure.value) == t.MCP_TIMEOUT.format(server="notion", seconds=0.05)


async def test_a_server_that_cannot_be_reached_says_so():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    session = McpSession(server(), client, dict)

    with pytest.raises(McpError, match="Không kết nối được máy chủ MCP notion: connection refus"):
        await session.start()


async def test_a_server_speaking_a_version_this_client_does_not_is_not_used():
    fake = FakeMcp()
    fake.version = "2023-01-01"

    with pytest.raises(McpError, match="phiên bản giao thức '2023-01-01'"):
        await session_for(fake).start()

    # Nothing is sent to a server once it is known not to be understood.
    assert fake.methods() == ["initialize"]


async def test_a_refused_sign_in_carries_what_the_server_said_of_where_to_sign_in():
    fake = FakeMcp(oauth=True)

    with pytest.raises(Unauthorized) as failure:
        await session_for(fake).start()

    assert "oauth-protected-resource" in failure.value.challenge


async def test_a_refusal_is_renewed_once_and_the_request_sent_again():
    fake = FakeMcp(oauth=True)
    held = {"Authorization": "Bearer stale"}
    renewals = []

    async def renew(refused: str) -> bool:
        renewals.append(refused)
        fake.required = "fresh"
        held["Authorization"] = "Bearer fresh"
        return True

    session = McpSession(server(), fake.client(), lambda: dict(held), renew)

    await session.start()

    # It is told which sign-in the server refused: the one held may be newer by now.
    assert renewals == ["Bearer stale"]
    assert [seen.headers["authorization"] for seen in fake.seen[:2]] == [
        "Bearer stale",
        "Bearer fresh",
    ]


async def test_a_renewal_that_does_not_help_is_not_tried_a_second_time():
    fake = FakeMcp(oauth=True)
    renewals = []

    async def renew(refused: str) -> bool:
        renewals.append(refused)
        return True

    session = McpSession(server(), fake.client(), dict, renew)

    with pytest.raises(Unauthorized) as failure:
        await session.start()

    # Sent with no sign-in at all, and refused: that is what the renewal is told.
    assert renewals == [""] and fake.methods() == ["initialize", "initialize"]
    assert failure.value.sent == ""


async def test_a_renewal_that_fails_leaves_the_refusal_as_the_answer():
    fake = FakeMcp(oauth=True)

    async def renew(refused: str) -> bool:
        return False

    with pytest.raises(Unauthorized):
        await McpSession(server(), fake.client(), dict, renew).start()

    assert fake.methods() == ["initialize"]
