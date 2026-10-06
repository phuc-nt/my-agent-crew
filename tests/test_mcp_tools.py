"""A server's tools as tools of the crew: what each is called here, what the model is told
of it, when it asks first, and who is handed it (`mcp/tools.py`, `mcp/hub.py`,
`agent/declared_tools.py`)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace

import httpcore
import httpx
import pytest

from my_agent_crew import texts_mcp as t
from my_agent_crew.agent.declared_tools import declared_names, declared_specs
from my_agent_crew.agent.prompt import system_prompt_for
from my_agent_crew.agent.tool_gate import pauses_for_a_person
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.mcp.config import DEFERRED, DIRECT, HIDDEN
from my_agent_crew.mcp.hub import CONNECTED, FAILED, IDLE, SIGNED_OUT, McpHub
from my_agent_crew.mcp.tokens import TokenStore
from my_agent_crew.mcp.tools import McpTool, build_tools, render, tool_name
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.registry import ToolRegistry
from tests.mcp_fakes import CREATE, SEARCH, TOOLS, FakeMcp, make_hub, public, server, unparsed

SEARCH_NAME, CREATE_NAME = "mcp__notion__search", "mcp__notion__create_page"


async def never_called(name, arguments):
    raise AssertionError("no call is made while tools are only being listed")


def built(listed=TOOLS, **settings) -> dict[str, McpTool]:
    tools, _ = build_tools(server(**settings), listed, never_called)
    return {tool.remote: tool for tool in tools}


def test_a_tool_is_named_after_its_server_in_letters_every_provider_takes():
    assert tool_name("notion", "search") == SEARCH_NAME
    assert tool_name("my-notes", "pages.get/v2") == "mcp__my_notes__pages_get_v2"
    long_a, long_b = "export-" + "a" * 80, "export-" + "a" * 79 + "b"

    name_a, name_b = tool_name("notion", long_a), tool_name("notion", long_b)

    assert len(name_a) == len(name_b) == 64
    # Cut at the same place, two long names still do not meet.
    assert name_a != name_b and name_a[:50] == name_b[:50]
    assert tool_name("notion", long_a) == name_a


def test_what_the_model_reads_of_a_tool_says_which_server_it_is_on():
    tools = built(
        [
            SEARCH,
            {"name": "bare"},
            {"name": "wordy", "description": "d" * 5000, "inputSchema": {"type": "string"}},
        ]
    )

    assert tools["search"].description == "[MCP notion] Find pages by words."
    assert tools["search"].parameters == SEARCH["inputSchema"]
    # A tool that says nothing of itself is at least named, and one whose schema no
    # provider would take is given the empty one instead of being lost.
    assert tools["bare"].description == "[MCP notion] bare"
    assert tools["bare"].parameters == {"type": "object", "properties": {}}
    assert tools["wordy"].parameters == {"type": "object", "properties": {}}
    assert len(tools["wordy"].description) < 2100 and tools["wordy"].description.endswith("…")


def test_every_tool_asks_first_until_the_owner_says_it_only_reads():
    """The server's own word that a tool only reads is shown and decides nothing: the one
    saying it is the one being trusted."""
    asking = built()
    trusted = built(read_only=["search"])

    assert asking["search"].read_only_hint is True
    assert asking["search"].requires_approval and not asking["search"].replay_safe
    assert asking["create-page"].requires_approval and not asking["create-page"].replay_safe
    assert not trusted["search"].requires_approval and trusted["search"].replay_safe
    assert trusted["create-page"].requires_approval and not trusted["create-page"].replay_safe
    # None of them has a reason of its own to ask: the person's "always allow" and an
    # autonomous conversation stand for these as for any other tool.
    assert all(tool.ask_reason is None for tool in asking.values())


def test_a_tool_carries_how_far_it_is_let_in():
    tools = built(exposure="direct", tool_exposure={"create-*": "hidden"})

    assert tools["search"].exposure == DIRECT and tools["create-page"].exposure == HIDDEN
    assert built()["search"].exposure == DEFERRED
    assert tools["search"].to_dict() == {
        "name": SEARCH_NAME,
        "description": "[MCP notion] Find pages by words.",
        "requires_approval": True,
        "server": "notion",
        "exposure": "direct",
    }


def left_out(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "my_agent_crew.mcp.tools"]


def test_two_tools_that_come_to_one_name_keep_the_first_and_name_the_other(caplog):
    listed = [{"name": "get page"}, {"name": "get_page"}, {"name": ""}, "junk", {"title": "x"}]

    with caplog.at_level(logging.WARNING, logger="my_agent_crew.mcp.tools"):
        tools, skipped = build_tools(server(), listed, never_called)

    assert [tool.remote for tool in tools] == ["get page"] and skipped == ("get_page",)
    assert left_out(caplog) == ["MCP server notion: tool 'get_page' left out, its name is taken"]


def sized(chars: int) -> dict:
    """An object schema whose JSON is exactly this many letters long."""
    schema = {"type": "object", "description": ""}
    schema["description"] = "x" * (chars - len(json.dumps(schema)))
    assert len(json.dumps(schema)) == chars
    return schema


def test_a_tool_with_more_name_or_parameters_than_is_taken_is_left_out_and_named(caplog):
    fits, long = "n" * 128, "n" * 129
    listed = [
        {"name": fits},
        {"name": long},
        {"name": "wide", "inputSchema": sized(50_000)},
        {"name": "wider", "inputSchema": sized(50_001)},
        # Measured in letters, whatever the language they are in.
        {"name": "việt", "inputSchema": {"type": "object", "description": "ữ" * 49_000}},
        SEARCH,
    ]

    with caplog.at_level(logging.WARNING, logger="my_agent_crew.mcp.tools"):
        tools, skipped = build_tools(server(), listed, never_called)

    assert [tool.remote for tool in tools] == [fits, "wide", "việt", "search"]
    # Named in few enough letters to read: a name can be as long as a page of the list.
    cut = "n" * 59 + "…"
    assert skipped == (cut, "wider")
    assert left_out(caplog) == [
        f"MCP server notion: tool '{cut}' left out, its name is too long",
        "MCP server notion: tool 'wider' left out, its parameters are too large",
    ]


def test_a_name_left_out_for_being_too_long_does_not_keep_others_from_the_name_it_comes_to():
    """Cut to the letters a provider takes, a long name can meet a short one's."""
    long = "a" * 200

    tools, skipped = build_tools(server(), [{"name": long}, {"name": long}], never_called)

    assert tools == () and skipped == ("a" * 59 + "…",) * 2


def test_a_tool_too_large_is_said_to_be_that_even_where_its_name_is_taken_too(caplog):
    """Its size is looked at first, so a name of any length is never worked on."""
    listed = [SEARCH, {"name": "search", "inputSchema": sized(50_001)}]

    with caplog.at_level(logging.WARNING, logger="my_agent_crew.mcp.tools"):
        tools, skipped = build_tools(server(), listed, never_called)

    assert [tool.remote for tool in tools] == ["search"] and skipped == ("search",)
    assert left_out(caplog) == [
        "MCP server notion: tool 'search' left out, its parameters are too large"
    ]


def test_a_tool_left_out_is_logged_on_one_line_whatever_its_name_holds(caplog):
    listed = [{"name": "a b"}, {"name": "a\nb"}]  # both come to mcp__notion__a_b

    with caplog.at_level(logging.WARNING, logger="my_agent_crew.mcp.tools"):
        _, skipped = build_tools(server(), listed, never_called)

    assert skipped == ("a\nb",)
    assert left_out(caplog) == ["MCP server notion: tool 'a\\nb' left out, its name is taken"]


def test_parameters_nested_too_deep_to_write_out_again_are_too_large():
    schema = inner = {"type": "object"}
    for _ in range(20_000):
        inner["properties"] = {"a": {"type": "object"}}
        inner = inner["properties"]["a"]
    listed = [{"name": "deep", "inputSchema": schema}, SEARCH]

    tools, skipped = build_tools(server(), listed, never_called)

    assert [tool.remote for tool in tools] == ["search"] and skipped == ("deep",)


@pytest.mark.parametrize(
    ("result", "text"),
    [
        (
            {"content": [{"type": "text", "text": "một"}, {"type": "text", "text": "hai"}]},
            "một\nhai",
        ),
        (
            {"content": [{"type": "image", "mimeType": "image/png", "data": "AAAA"}]},
            "[image: image/png]",
        ),
        (
            {
                "content": [
                    {"type": "resource", "resource": {"uri": "file:///a", "text": "nội dung"}}
                ]
            },
            "nội dung",
        ),
        (
            {"content": [{"type": "resource", "resource": {"uri": "file:///a", "blob": "AAAA"}}]},
            "[resource: file:///a]",
        ),
        ({"content": [{"type": "resource_link", "uri": "https://x/y"}]}, "[link: https://x/y]"),
        ({"content": [], "structuredContent": {"n": 2, "tên": "số"}}, '{"n": 2, "tên": "số"}'),
        (
            {"content": [{"type": "text", "text": "hai trang"}], "structuredContent": {"n": 2}},
            "hai trang",
        ),
        ({"content": ["junk", {"type": "text", "text": "còn lại"}]}, "còn lại"),
        ({}, ""),
    ],
    ids=[
        "text",
        "image",
        "resource text",
        "resource blob",
        "link",
        "structured",
        "text beside the same thing structured",
        "junk",
        "empty",
    ],
)
def test_a_result_is_read_as_text_and_what_is_not_text_is_named(result, text):
    assert render(result) == text


async def connected(fake: FakeMcp, *servers, **kwargs) -> McpHub:
    hub = make_hub(fake, *servers, **kwargs)
    await hub.connect()
    return hub


async def test_a_call_through_the_registry_reaches_the_server_and_returns_its_text(deps_factory):
    fake = FakeMcp()
    hub = await connected(fake, server(read_only=["search"]))
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))
    hub.attach({"default": deps})

    result = await deps.tools.execute(SEARCH_NAME, {"query": "kế hoạch"})

    assert result.ok and result.output == "ran search"
    assert fake.calls == [("search", {"query": "kế hoạch"})]


@pytest.mark.parametrize(
    ("result", "said"),
    [
        (
            {"isError": True, "content": [{"type": "text", "text": "không có trang đó"}]},
            "không có trang đó",
        ),
        ({"isError": True, "content": []}, t.MCP_TOOL_FAILED),
        ({"rpc_error": {"code": -32000, "message": "quota"}}, "báo lỗi: quota"),
    ],
    ids=["the tool says why", "the tool says nothing", "the server refuses the call"],
)
async def test_a_tool_that_fails_is_a_failed_result_the_model_reads(deps_factory, result, said):
    fake = FakeMcp()
    fake.results["search"] = result
    hub = await connected(fake)
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))
    hub.attach({"default": deps})

    outcome = await deps.tools.execute(SEARCH_NAME, {})

    assert not outcome.ok and said in outcome.output


async def test_a_tool_with_nothing_to_say_still_tells_the_model_it_ran(deps_factory):
    fake = FakeMcp()
    fake.results["search"] = {"content": []}
    hub = await connected(fake)
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))
    hub.attach({"default": deps})

    outcome = await deps.tools.execute(SEARCH_NAME, {})

    assert outcome.ok and outcome.output == t.MCP_EMPTY_RESULT


async def test_a_key_taken_away_after_connecting_fails_the_call_by_naming_it(deps_factory):
    environ = {"NOTION_KEY": "k"}
    keyed = server(headers={"Authorization": "Bearer ${NOTION_KEY}"})
    hub = await connected(FakeMcp(), keyed, environ=environ)
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))
    hub.attach({"default": deps})
    del environ["NOTION_KEY"]

    outcome = await deps.tools.execute(SEARCH_NAME, {})

    missing = t.MCP_MISSING_ENV.format(names="NOTION_KEY")
    assert not outcome.ok and outcome.output == TOOL_FAILED.format(error=missing)


async def test_an_agent_holds_only_the_tools_of_the_servers_its_profile_names(deps_factory):
    hub = await connected(
        FakeMcp(), server("notion"), server("tracker", tool_exposure={"create-page": "hidden"})
    )
    coach, ledger, plain = deps_factory(), deps_factory(), deps_factory()
    coach.profile = replace(coach.agent, id="coach", mcp=("notion",))
    ledger.profile = replace(ledger.agent, id="ledger", mcp=("tracker", "notion"))
    agents = {"coach": coach, "ledger": ledger, "plain": plain}
    before = plain.tools.names()

    hub.attach(agents)

    held = lambda deps: [n for n in deps.tools.names() if n.startswith("mcp__")]  # noqa: E731
    assert held(coach) == [SEARCH_NAME, CREATE_NAME]
    # In the order the profile names its servers; a hidden tool is handed to nobody.
    assert held(ledger) == ["mcp__tracker__search", SEARCH_NAME, CREATE_NAME]
    assert plain.tools.names() == before
    # The agent's own tools stay where they were, ahead of what the servers add.
    assert coach.tools.names()[: len(before)] == before


async def test_two_servers_whose_tools_come_to_one_name_give_the_agent_the_first(deps_factory):
    """`a` with a tool `b__c` and `a__b` with a tool `c` are both mcp__a__b__c. The file
    takes no such pair of names; were one ever there, neither tool would stand in for the
    other."""
    fake = FakeMcp([{"name": "b__c"}, {"name": "c"}])
    hub = await connected(fake, server("a"), unparsed("a__b"))
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("a", "a__b"))

    hub.attach({"default": deps})  # the second is left out, not a start that fails

    held = [n for n in deps.tools.names() if n.startswith("mcp__")]
    assert held == ["mcp__a__b__c", "mcp__a__c", "mcp__a__b__b__c"]
    assert deps.tools.get("mcp__a__b__c").server == "a"


async def test_handing_out_again_takes_back_what_a_profile_no_longer_names(deps_factory):
    hub = await connected(FakeMcp())
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))
    agents = {"default": deps}
    hub.attach(agents)
    hub.attach(agents)  # twice changes nothing: no tool is registered a second time
    assert declared_names(deps.tools) == [n for n in deps.tools.names() if "mcp__" not in n]
    assert SEARCH_NAME in deps.tools.names()

    deps.profile = replace(deps.agent, mcp=())
    hub.attach(agents)

    assert not [n for n in deps.tools.names() if n.startswith("mcp__")]


async def test_handing_out_again_takes_every_tool_back_in_one_build_of_the_toolbox(
    deps_factory, monkeypatch
):
    hub = await connected(FakeMcp([{"name": f"tool-{n}"} for n in range(50)]))
    deps, plain = deps_factory(), deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))
    agents = {"default": deps, "plain": plain}
    hub.attach(agents)
    untouched, held = plain.tools, deps.tools.names()
    assert len([name for name in held if name.startswith("mcp__")]) == 50
    builds: list[ToolRegistry] = []
    init = ToolRegistry.__init__

    def counted(self, *args, **kwargs) -> None:
        builds.append(self)
        init(self, *args, **kwargs)

    monkeypatch.setattr(ToolRegistry, "__init__", counted)

    hub.attach(agents)

    # A build for each tool taken back is time that grows with the square of what a server
    # lists, spent on the loop every turn runs on.
    assert len(builds) == 1 and deps.tools.names() == held
    # An agent with nothing to take back keeps the toolbox it had.
    assert plain.tools is untouched


async def test_a_server_that_lists_too_many_tools_is_down_and_says_why():
    hub = await connected(FakeMcp([{"name": f"tool-{n}"} for n in range(1001)]))

    link = hub.links["notion"]
    assert (link.status, link.tools) == (FAILED, ())
    assert link.error == t.MCP_TOO_MANY_TOOLS.format(server="notion", limit=1000)
    assert hub.waiting() == ["notion"]


async def test_a_server_no_agent_was_told_of_is_a_warning_not_a_failure(deps_factory, caplog):
    hub = await connected(FakeMcp())
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("jira", "notion"))

    with caplog.at_level(logging.WARNING, logger="my_agent_crew.mcp.handout"):
        hub.attach({"default": deps})

    assert "agent default: no MCP server named jira" in caplog.text
    assert SEARCH_NAME in deps.tools.names()


async def test_only_tools_let_in_directly_are_told_to_the_model_on_every_call(deps_factory):
    """A server can list dozens of tools. The ones held back are still the agent's and
    still run by name; they are just not paid for on every call of every turn."""
    hub = await connected(FakeMcp(), server(tool_exposure={"search": "direct"}))
    deps = deps_factory()
    own = deps.tools.names()
    deps.profile = replace(deps.agent, mcp=("notion",))
    hub.attach({"default": deps})

    # `tool_search` is how the one held back is found (`test_mcp_tool_search.py`).
    assert declared_names(deps.tools) == [*own, "tool_search", SEARCH_NAME]
    assert [spec.name for spec in declared_specs(deps.tools)] == [*own, "tool_search", SEARCH_NAME]
    assert CREATE_NAME in deps.tools.names() and deps.tools.get(CREATE_NAME) is not None
    prompt = system_prompt_for(deps)
    assert SEARCH_NAME in prompt and CREATE_NAME not in prompt


async def test_an_mcp_tool_asks_like_any_other_and_a_trusted_one_does_not(deps_factory, store):
    hub = await connected(FakeMcp(), server(read_only=["search"]))
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))
    hub.attach({"default": deps})
    conv = store.create("việc")
    write = ToolCall("c1", CREATE_NAME, {"title": "x"})
    read = ToolCall("c2", SEARCH_NAME, {"query": "x"})

    assert pauses_for_a_person(deps, conv, write)
    assert not pauses_for_a_person(deps, conv, read)
    # The person's standing answers hold for it as for the crew's own tools.
    assert not pauses_for_a_person(deps, replace(conv, auto_approve=(CREATE_NAME,)), write)
    assert not pauses_for_a_person(deps, replace(conv, autonomous=True), write)


def boom(request, message):
    raise RuntimeError("boom")


@pytest.mark.parametrize(
    ("break_it", "status", "said"),
    [
        (lambda fake: setattr(fake, "version", "1999-01-01"), FAILED, "phiên bản giao thức"),
        (
            lambda fake: setattr(
                fake, "before", lambda r, m: httpx.Response(502, text="bad gateway")
            ),
            FAILED,
            "HTTP 502",
        ),
        (
            lambda fake: setattr(fake, "before", lambda r, m: httpx.Response(403, text="no")),
            FAILED,
            "HTTP 403: no",
        ),
        (lambda fake: setattr(fake, "tools", 7), FAILED, "không đúng giao thức"),
        (lambda fake: setattr(fake, "before", boom), FAILED, "RuntimeError: boom"),
        (lambda fake: setattr(fake, "required", "something"), SIGNED_OUT, ""),
    ],
    ids=[
        "a version not spoken",
        "an error status",
        "a no that is not a request to sign in",
        "nonsense for a tool list",
        "a failure nobody foresaw",
        "wants a sign-in",
    ],
)
async def test_a_server_that_does_not_connect_is_a_row_that_says_why(break_it, status, said):
    fake = FakeMcp()
    break_it(fake)
    hub = make_hub(fake)
    assert hub.links["notion"].status == IDLE

    await hub.connect()  # never raises

    link = hub.links["notion"]
    assert link.status == status and said in link.error
    assert link.tools == () and link.session is None


async def test_one_server_down_does_not_keep_the_others_from_connecting(deps_factory):
    fake = FakeMcp()
    down = server("down", url="https://down.example.test/mcp")
    hub = make_hub(fake, down, server("notion"))

    await hub.connect()

    assert hub.links["down"].status == FAILED and "HTTP 404" in hub.links["down"].error
    assert hub.links["notion"].status == CONNECTED
    assert hub.waiting() == ["down"]
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("down", "notion"))
    hub.attach({"default": deps})
    assert [n for n in deps.tools.names() if n.startswith("mcp__")] == [SEARCH_NAME, CREATE_NAME]


async def test_connecting_as_a_whole_gets_the_time_one_request_gets():
    """Requests that each come in time can add up to a start that does not end, and the
    round that tries the servers that are down waits for every one of them."""
    fake = FakeMcp()
    fake.delay = 0.06  # three requests open a session and list its tools
    hub = make_hub(fake, server(timeout=0.15))

    await asyncio.wait_for(hub.connect(), 3)

    link = hub.links["notion"]
    assert link.status == FAILED
    assert link.error == t.MCP_TIMEOUT.format(server="notion", seconds=0.15)
    assert link.session is None and link.tools == ()
    assert hub.waiting() == ["notion"]


async def test_a_key_the_environment_lacks_is_named_and_one_refused_is_not_a_sign_in():
    keyed = server(headers={"Authorization": "Bearer ${NOTION_KEY}"})
    environ: dict[str, str] = {}
    fake = FakeMcp()
    fake.required = "right"
    hub = make_hub(fake, keyed, environ=environ)

    await hub.connect()
    assert hub.links["notion"].status == FAILED
    assert hub.links["notion"].error == t.MCP_MISSING_ENV.format(names="NOTION_KEY")
    assert fake.seen == []  # nothing is sent without the key the file asks for

    environ["NOTION_KEY"] = "wrong"
    await hub.connect()
    # The file says how this server is authorised; a sign-in button would be no help.
    assert hub.links["notion"].status == FAILED
    assert hub.links["notion"].error == t.MCP_KEY_REFUSED

    environ["NOTION_KEY"] = "right"
    await hub.connect(["notion", "no-such-server"])
    assert hub.links["notion"].status == CONNECTED and hub.links["notion"].error == ""
    assert fake.seen[-1].headers["authorization"] == "Bearer right"


def writing_for_real() -> httpx.AsyncClient:
    """A client whose requests go through the real HTTP/1.1 writer and no further: no socket
    is opened. `MockTransport` skips that writer, and it is the writer that refuses a header."""
    transport = httpx.AsyncHTTPTransport()
    backend = httpcore.AsyncMockBackend([])
    transport._pool = httpcore.AsyncConnectionPool(network_backend=backend)
    return httpx.AsyncClient(transport=transport)


async def test_a_header_that_cannot_be_written_is_refused_without_showing_its_value():
    """The writer's own refusal quotes the value it would not write, and that value is a key."""
    keyed = server(headers={"Authorization": "Bearer ${NOTION_KEY}"})
    environ = {"NOTION_KEY": "the-first-half\nthe-second-half"}
    hub = McpHub((keyed,), writing_for_real(), TokenStore(None, environ), public, environ)

    await hub.connect()

    row = hub.describe({})[0]
    assert (row["status"], row["error"]) == ("failed", t.MCP_BAD_HEADER.format(server="notion"))
    assert "half" not in json.dumps(row)


async def test_a_key_in_the_file_is_what_is_sent_even_with_a_sign_in_kept():
    """The file says how this server is authorised. A token left from a sign-in made
    before the key was written must not go in its place."""
    keyed = server(headers={"Authorization": "Bearer ${NOTION_KEY}"})
    environ = {"NOTION_KEY": "from-the-file", "MCP_NOTION_ACCESS_TOKEN": "from-a-sign-in"}
    fake = FakeMcp()

    hub = await connected(fake, keyed, environ=environ)

    assert hub.links["notion"].status == CONNECTED
    assert {seen.headers["authorization"] for seen in fake.seen} == {"Bearer from-the-file"}


async def test_a_try_that_is_cut_off_leaves_the_server_as_one_still_to_try():
    """Connected before, and cut while being connected again: what it held is gone, so
    it must not go on looking connected, or nothing would ever try it again."""
    fake = FakeMcp()
    hub = await connected(fake)
    link = hub.links["notion"]
    assert link.status == CONNECTED and hub.waiting() == []
    fake.delay = 30.0

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(hub.connect(), 0.05)

    assert (link.status, link.tools, link.session) == (IDLE, (), None)
    assert hub.waiting() == ["notion"]


async def test_connecting_again_replaces_what_was_learnt_before(deps_factory):
    fake = FakeMcp()
    hub = await connected(fake)
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))
    agents = {"default": deps}
    hub.attach(agents)

    fake.tools = [SEARCH, {"name": "archive", "description": "Put away."}]
    await hub.connect()
    hub.attach(agents)

    held = [n for n in deps.tools.names() if n.startswith("mcp__")]
    assert held == [SEARCH_NAME, "mcp__notion__archive"]
    assert CREATE["name"] not in [tool.remote for tool in hub.links["notion"].tools]


async def test_the_owner_is_shown_one_line_of_what_a_tool_says_of_itself():
    wordy = {"name": "wordy", "description": "First line.\n\n  Second   line.\n" + "x" * 300}
    hub = await connected(FakeMcp([wordy]))

    [row] = hub.describe({})
    [tool] = row["tools"]

    assert tool["description"].startswith("[MCP notion] First line. Second line. xxx")
    assert len(tool["description"]) == 200 and tool["description"].endswith("x…")
    # The model is still told all of it.
    assert "\n" in hub.links["notion"].tools[0].description


async def test_what_the_owner_is_shown_of_a_server_holds_no_key(deps_factory):
    environ = {"NOTION_KEY": "sk-very-secret"}
    keyed = server(
        description="Sổ tay",
        headers={"Authorization": "Bearer ${NOTION_KEY}"},
        read_only=["search"],
        tool_exposure={"create-page": "hidden"},
    )
    hub = await connected(FakeMcp(), keyed, environ=environ)
    deps = deps_factory()
    deps.profile = replace(deps.agent, mcp=("notion",))

    [row] = hub.describe({"default": deps, "other": deps_factory()})

    assert "sk-very-secret" not in repr(row)
    assert row == {
        "name": "notion",
        "url": "https://mcp.example.test/mcp",
        "description": "Sổ tay",
        "status": "connected",
        "error": "",
        "exposure": "deferred",
        "signed_in": False,
        "uses_key": True,
        "env": ["NOTION_KEY"],
        "agents": ["default"],
        "skipped": [],
        "tools": [
            {
                "name": SEARCH_NAME,
                "remote": "search",
                "description": "[MCP notion] Find pages by words.",
                "exposure": "deferred",
                "requires_approval": False,
                "read_only_hint": True,
            },
            {
                "name": CREATE_NAME,
                "remote": "create-page",
                "description": "[MCP notion] Make a page.",
                "exposure": "hidden",
                "requires_approval": True,
                "read_only_hint": False,
            },
        ],
    }
