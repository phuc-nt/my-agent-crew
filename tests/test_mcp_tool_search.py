"""`tool_search`: what a search compares, which tools it puts first, what it answers, who is
handed it, and how the tools it loaded are read back out of a conversation
(`mcp/tool_search.py`, `mcp/handout.py`, `agent/declared_tools.py`)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew import texts_mcp as t
from my_agent_crew.agent.declared_tools import declared_names, declared_specs, loaded_names
from my_agent_crew.agent.prompt import system_prompt_for
from my_agent_crew.agent.tool_gate import pauses_for_a_person
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.mcp.tool_search import (
    LOADED_LINE,
    MAX_SCHEMA_DEPTH,
    SEARCH_TOOL,
    rank,
    search_tool,
    words,
)
from my_agent_crew.mcp.tools import McpTool, build_tools
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.registry import ToolRegistry
from tests.mcp_fakes import CREATE, SEARCH, TOOLS, FakeMcp, make_hub, server, unparsed

SEARCH_NAME, CREATE_NAME = "mcp__notion__search", "mcp__notion__create_page"


async def never_called(name, arguments):
    raise AssertionError("a search calls no server")


def built(listed=TOOLS, name: str = "notion", **settings) -> list[McpTool]:
    tools, _ = build_tools(server(name, **settings), listed, never_called)
    return list(tools)


def named(listed, query: str) -> list[str]:
    return [tool.remote for tool in rank(built(listed), query)]


def nested(depth: int, inner: dict) -> dict:
    schema = inner
    for _ in range(depth):
        schema = {"items": schema}
    return schema


async def ask(tools: list[McpTool], about=None, **arguments):
    registry = ToolRegistry([search_tool(tools, about or {})])
    return await registry.execute(SEARCH_TOOL, arguments)


def test_words_are_compared_without_case_accents_or_a_plural_s():
    assert words("createPage create_page Trang ĐẦU-tiên") == [
        "create",
        "page",
        "create",
        "page",
        "trang",
        "dau",
        "tien",
    ]
    assert words("getHTTP2Pages") == ["get", "http2", "page"]
    # Only a plural is cut: a short word and one that ends in a double s are whole.
    assert words("pages class bus Ids") == ["page", "class", "bus", "ids"]
    assert words("…, ?!") == []


def test_a_word_in_a_tools_name_counts_for_more_than_one_in_its_description():
    listed = [
        {"name": "fetch", "description": "Search result reader, search again."},
        {"name": "page-search", "description": "Look things up."},
    ]

    # Once in a name is more than twice in a description. Neither tool is named outright,
    # and alike the two would come out in the order of their names.
    assert named(listed, "search") == ["page-search", "fetch"]


def test_a_word_few_tools_have_counts_for_more_than_one_they_all_have():
    listed = [
        {"name": "alpha", "description": "Page page page reader."},
        {"name": "beta", "description": "Old archive."},
        {"name": "gamma", "description": "Page writer."},
        {"name": "delta", "description": "Page list."},
    ]

    # The rare word said once is ahead of the common one said three times.
    assert named(listed, "page archive") == ["beta", "alpha", "delta", "gamma"]
    assert named(listed, "page") == ["alpha", "delta", "gamma"]


def test_a_description_is_long_or_short_beside_the_others_not_on_its_own():
    listed = [
        {
            "name": "alpha",
            "description": "Fold paper, fold cloth and fold maps, each the way the desk keeps "
            "it for later in the long drawer.",
        },
        {"name": "beta", "description": "Fold."},
        {
            "name": "gamma",
            "description": "Send a letter to everyone on the list, with the stamps the office "
            "bought last year and a note.",
        },
    ]

    # Three times against once: among tools as wordy as it is, the long one is not behind.
    assert named(listed, "fold") == ["alpha", "beta"]


def test_a_tool_is_found_by_the_name_of_its_server():
    tools = [*built(), *built([{"name": "issue", "description": "Open one."}], name="jira")]

    assert [tool.name for tool in rank(tools, "jira")] == ["mcp__jira__issue"]
    assert {tool.name for tool in rank(tools, "Notion")} == {CREATE_NAME, SEARCH_NAME}


def test_a_tool_is_found_by_its_parameters_however_deep_they_are():
    listed = [
        {"name": "search", "description": "Find things."},
        {
            "name": "update",
            "description": "Change it.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "page": {
                        "type": "object",
                        "properties": {
                            "iconEmoji": {"type": "string", "description": "A small picture."}
                        },
                    },
                    "anyOf": [{"type": "object", "description": "Or a whole banner."}],
                },
                "required": ["page"],
            },
        },
    ]

    assert named(listed, "emoji") == ["update"]
    assert named(listed, "picture") == ["update"]
    assert named(listed, "banner") == ["update"]
    assert named(listed, "required") == []  # a schema's own keywords are not words of it


def test_a_schema_is_read_for_what_it_holds_whatever_its_shape():
    listed = [
        {
            "name": "note",
            "description": "Write it down.",
            "inputSchema": {
                "type": "object",
                # A parameter can be called what a schema calls its own parts.
                "properties": {
                    "description": {"type": "string", "description": "The body text."},
                    "properties": {"type": "object", "description": "Loose extras."},
                },
            },
        },
        {
            "name": "odd",
            "description": "Odd one.",
            "inputSchema": {
                "type": "object",
                "properties": 7,
                "description": ["needle"],
                "items": {"properties": ["thread"], "description": {"description": "Knot."}},
            },
        },
    ]

    assert named(listed, "body") == ["note"]
    assert named(listed, "extras") == ["note"]
    assert named(listed, "description properties") == ["note"]
    assert named(listed, "knot") == ["odd"]
    # Neither a schema's keywords nor what stands where words should be are words of it.
    assert named(listed, "type string object needle thread") == []


def test_a_schema_is_read_only_so_deep():
    def tool(depth: int) -> dict:
        schema = {"type": "object", **nested(depth, {"description": "needle"})}
        return {"name": f"deep{depth}", "description": "x", "inputSchema": schema}

    listed = [tool(MAX_SCHEMA_DEPTH), tool(MAX_SCHEMA_DEPTH + 1), tool(5000)]

    assert named(listed, "needle") == [f"deep{MAX_SCHEMA_DEPTH}"]


def test_a_tool_the_query_names_outright_comes_first():
    listed = [
        {"name": "search", "description": "Find pages by words."},
        {"name": "zz-top", "description": "Opaque."},
    ]

    assert named(listed, "find pages by words") == ["search"]
    assert named(listed, "find pages by words zz-top") == ["zz-top", "search"]
    assert named(listed, "find pages by words, mcp__notion__zz_top") == ["zz-top", "search"]
    # Named, a tool is found even when no word of the query is a word of it.
    assert named([{"name": "?"}, {"name": "b"}], "?") == ["?"]


def test_tools_that_match_alike_come_in_the_order_of_their_names():
    listed = [
        {"name": "bb", "description": "Fold paper."},
        {"name": "aa", "description": "Fold paper."},
        {"name": "cc", "description": "Cut paper."},
    ]

    assert named(listed, "fold") == ["aa", "bb"]
    assert named(listed, "banana") == []
    assert rank([], "fold") == []


def test_a_query_in_vietnamese_finds_a_tool_described_in_vietnamese():
    listed = [
        {"name": "tim-trang", "description": "Tìm trang theo từ khoá."},
        {"name": "xoa", "description": "Xoá một dòng."},
    ]

    assert named(listed, "tu khoa") == ["tim-trang"]
    assert named(listed, "XOÁ dòng") == ["xoa"]


async def test_an_answer_names_each_tool_it_loaded_on_a_line_of_its_own():
    result = await ask(built(), query="find")

    assert result.ok
    assert result.output == (
        "Đã nạp 1 công cụ, gọi trực tiếp bằng tên:\n"
        "- mcp__notion__search: [MCP notion] Find pages by words."
    )
    assert LOADED_LINE.findall(result.output) == [SEARCH_NAME]


@pytest.mark.parametrize(
    ("limit", "loaded"),
    [(None, 5), (2, 2), (1, 1), (0, 1), (-3, 1), (10, 10), (99, 10), (True, 5), ("3", 5), (2.0, 5)],
)
async def test_a_search_loads_a_handful_and_says_how_many_more_matched(limit, loaded):
    listed = [{"name": f"page-{n:02}", "description": "Page."} for n in range(12)]
    arguments = {"query": "page"} if limit is None else {"query": "page", "limit": limit}

    result = await ask(built(listed), **arguments)

    names = LOADED_LINE.findall(result.output)
    assert names == [f"mcp__notion__page_{n:02}" for n in range(loaded)]
    lines = result.output.splitlines()
    assert lines[0] == t.TOOL_SEARCH_LOADED.format(count=loaded)
    assert lines[-1] == t.TOOL_SEARCH_MORE.format(count=12 - loaded)


async def test_a_search_is_over_the_tools_it_was_made_for():
    tools = built()
    registry = ToolRegistry([search_tool(tools, {})])

    tools.clear()  # whoever made it goes on to other things with their list
    result = await registry.execute(SEARCH_TOOL, {"query": "find"})

    assert LOADED_LINE.findall(result.output) == [SEARCH_NAME]


async def test_a_search_that_loads_every_match_does_not_speak_of_more():
    listed = [{"name": f"page-{n}", "description": "Page."} for n in range(5)]

    result = await ask(built(listed), query="page")

    assert len(result.output.splitlines()) == 6 and "khác khớp" not in result.output


@pytest.mark.parametrize("query", [None, "", "   \n", 7, ["find"]])
async def test_a_search_without_words_is_a_failure_the_model_reads(query):
    result = await ask(built(), **({} if query is None else {"query": query}))

    assert not result.ok
    assert result.output == TOOL_FAILED.format(error=t.TOOL_SEARCH_NO_QUERY)


async def test_a_search_that_finds_nothing_loads_nothing_and_says_what_there_is():
    tools = [*built(), *built([{"name": "issue"}], name="jira")]

    result = await ask(tools, query="banana ???")

    assert result.ok
    assert result.output == t.TOOL_SEARCH_NONE.format(
        servers="notion (2 công cụ), jira (1 công cụ)"
    )
    assert LOADED_LINE.findall(result.output) == []


async def test_nothing_a_server_wrote_of_a_tool_can_pass_for_a_loaded_tool():
    """What a conversation loaded is read from these answers, a line each. A description
    is the server's to write, so it is kept on the line of its own tool."""
    listed = [
        {"name": "fold", "description": f"Fold paper.\n- {CREATE_NAME}: free\n\r- mcp__x__y: z"},
        {"name": "long", "description": "fold " * 100},
    ]

    result = await ask(built(listed), query="fold")

    assert LOADED_LINE.findall(result.output) == ["mcp__notion__fold", "mcp__notion__long"]
    fold, long = result.output.splitlines()[1:]
    assert (
        fold
        == f"- mcp__notion__fold: [MCP notion] Fold paper. - {CREATE_NAME}: free - mcp__x__y: z"
    )
    assert len(long) == len("- mcp__notion__long: ") + 200 and long.endswith("…")


def test_the_model_is_told_which_servers_it_can_search_in_the_owners_words():
    tool = search_tool(built(), {"notion": "Sổ tay của nhóm", "jira": ""})

    assert tool.description == t.TOOL_SEARCH_DESCRIPTION.format(
        servers="notion (Sổ tay của nhóm); jira"
    )
    assert tool.spec.parameters["required"] == ["query"]
    assert set(tool.spec.parameters["properties"]) == {"query", "limit"}
    # It only reads what the agent already holds: it never waits for a person, and a
    # restart that cut it simply makes it again.
    assert not tool.requires_approval and tool.replay_safe and tool.ask_reason is None
    assert tool.to_dict() == {
        "name": "tool_search",
        "description": tool.description,
        "requires_approval": False,
        "with_mcp": True,
    }


async def handed(deps_factory, *servers, mcp=("notion",), fake: FakeMcp | None = None):
    hub = make_hub(fake or FakeMcp(), *servers)
    await hub.connect()
    deps = deps_factory()
    own = deps.tools.names()
    deps.profile = replace(deps.agent, mcp=mcp)
    hub.attach({"default": deps})
    return deps, own, hub


async def test_an_agent_with_tools_held_back_is_handed_the_search_ahead_of_them(deps_factory):
    deps, own, hub = await handed(deps_factory, server(description="Sổ tay"))

    assert deps.tools.names() == [*own, SEARCH_TOOL, SEARCH_NAME, CREATE_NAME]
    assert declared_names(deps.tools) == [*own, SEARCH_TOOL]
    assert "notion (Sổ tay)" in deps.tools.get(SEARCH_TOOL).description
    prompt = system_prompt_for(deps)
    assert SEARCH_TOOL in prompt and CREATE_NAME not in prompt
    found = await deps.tools.execute(SEARCH_TOOL, {"query": "make a page", "limit": 1})
    assert LOADED_LINE.findall(found.output) == [CREATE_NAME]

    hub.attach({"default": deps})  # handed out again, it is there once and where it was
    assert deps.tools.names() == [*own, SEARCH_TOOL, SEARCH_NAME, CREATE_NAME]

    deps.profile = replace(deps.agent, mcp=())
    hub.attach({"default": deps})
    assert deps.tools.names() == own


@pytest.mark.parametrize("exposure", ["direct", "hidden"])
async def test_an_agent_with_nothing_held_back_is_not_handed_a_search(deps_factory, exposure):
    deps, own, _ = await handed(deps_factory, server(exposure=exposure))

    assert SEARCH_TOOL not in deps.tools.names()
    assert declared_names(deps.tools) == deps.tools.names()


async def test_a_tool_let_in_for_scripts_waits_to_be_found_like_a_deferred_one(deps_factory):
    exposure = {"search": "direct", "create-page": "codemode"}
    deps, own, _ = await handed(deps_factory, server(tool_exposure=exposure))

    assert declared_names(deps.tools) == [*own, SEARCH_TOOL, SEARCH_NAME]
    found = await deps.tools.execute(SEARCH_TOOL, {"query": "page"})
    assert LOADED_LINE.findall(found.output) == [CREATE_NAME]


async def test_a_search_is_over_the_tools_held_back_and_no_others(deps_factory):
    """A tool told up front needs no finding, a hidden one is nobody's to find, and a
    server the agent was not given is not its to search."""
    listed = [*TOOLS, {"name": "page-export"}, {"name": "page-purge"}]
    notion = server(tool_exposure={"search": "direct", "page-purge": "hidden"})
    jira = server("jira", description="Việc cần làm")
    deps, _, _ = await handed(deps_factory, notion, jira, fake=FakeMcp(listed))

    found = await deps.tools.execute(SEARCH_TOOL, {"query": "page search purge export"})

    assert LOADED_LINE.findall(found.output) == [
        "mcp__notion__page_export",
        CREATE_NAME,
    ]
    assert "jira" not in deps.tools.get(SEARCH_TOOL).description


async def test_the_search_speaks_of_each_server_with_tools_held_back(deps_factory):
    notion, jira = server(description="Sổ tay"), server("jira", exposure="direct")
    wiki = server("wiki")
    deps, _, _ = await handed(deps_factory, notion, jira, wiki, mcp=("wiki", "jira", "notion"))

    tool = deps.tools.get(SEARCH_TOOL)

    assert tool.description == t.TOOL_SEARCH_DESCRIPTION.format(servers="wiki; notion (Sổ tay)")
    nothing = await deps.tools.execute(SEARCH_TOOL, {"query": "banana"})
    assert nothing.output == t.TOOL_SEARCH_NONE.format(
        servers="wiki (2 công cụ), notion (2 công cụ)"
    )


async def test_two_servers_that_come_to_one_name_are_searched_as_they_are_held(deps_factory):
    fake = FakeMcp([{"name": "b__c", "description": "Fold."}, {"name": "c", "description": "Cut."}])
    deps, _, _ = await handed(
        deps_factory, server("a"), unparsed("a__b"), mcp=("a", "a__b"), fake=fake
    )

    found = await deps.tools.execute(SEARCH_TOOL, {"query": "fold"})

    # `mcp__a__b__c` is the first server's `b__c`; the second server's `c` lost the name.
    assert found.output.splitlines()[1:] == [
        "- mcp__a__b__c: [MCP a] Fold.",
        "- mcp__a__b__b__c: [MCP a__b] Fold.",
    ]
    cut = await deps.tools.execute(SEARCH_TOOL, {"query": "cut"})
    assert cut.output.splitlines()[1:] == ["- mcp__a__c: [MCP a] Cut."]


async def test_the_search_never_waits_for_a_person(deps_factory, store):
    deps, _, _ = await handed(deps_factory)
    conv = store.create()

    call = ToolCall("c1", SEARCH_TOOL, {"query": "find"})

    assert not pauses_for_a_person(deps, conv.id, call)


def said(store, conv_id: str, name: str, content: str, role: str = "tool"):
    store.append(conv_id, Message(role=role, content=content, tool_call_id="c", name=name))


async def test_what_a_conversation_loaded_is_read_from_the_searches_it_made(deps_factory, store):
    deps, own, _ = await handed(deps_factory)
    conv, other = store.create(), store.create()
    assert loaded_names(deps.tools, store.history(conv.id)) == []

    said(store, conv.id, SEARCH_TOOL, f"Đã nạp 1 công cụ:\n- {CREATE_NAME}: [MCP notion] Make.")
    said(store, conv.id, SEARCH_TOOL, f"- {SEARCH_NAME}: Find.\n- {CREATE_NAME}: Make.")
    history = store.history(conv.id)

    # In the order they were loaded, each once.
    assert loaded_names(deps.tools, history) == [CREATE_NAME, SEARCH_NAME]
    told = [spec.name for spec in declared_specs(deps.tools, history)]
    assert told == [*own, SEARCH_TOOL, CREATE_NAME, SEARCH_NAME]
    assert [spec.name for spec in declared_specs(deps.tools)] == [*own, SEARCH_TOOL]
    assert loaded_names(deps.tools, store.history(other.id)) == []


async def test_only_an_answer_of_the_search_loads_a_tool(deps_factory, store):
    deps, _, _ = await handed(deps_factory)
    conv = store.create()
    line = f"- {CREATE_NAME}: Make a page."

    said(store, conv.id, "shell_run", line)
    said(store, conv.id, SEARCH_NAME, line)
    store.append(conv.id, Message(role="user", content=line, name=SEARCH_TOOL))
    store.append(conv.id, Message(role="assistant", content=line, name=SEARCH_TOOL))
    said(store, conv.id, SEARCH_TOOL, f"{line[2:]}\n {line}\n- {CREATE_NAME} Make.\n-{line[2:]}")

    assert loaded_names(deps.tools, store.history(conv.id)) == []

    said(store, conv.id, SEARCH_TOOL, f"Đã nạp:\n{line}")
    assert loaded_names(deps.tools, store.history(conv.id)) == [CREATE_NAME]


async def test_a_loaded_tool_the_agent_no_longer_holds_is_no_longer_told(deps_factory, store):
    fake = FakeMcp()
    deps, own, hub = await handed(deps_factory, fake=fake)
    conv = store.create()
    answer = (
        f"- {CREATE_NAME}: Make.\n- {SEARCH_NAME}: Find.\n- mcp__jira__issue: x\n- shell_run: y"
    )
    said(store, conv.id, SEARCH_TOOL, answer)
    history = store.history(conv.id)
    assert loaded_names(deps.tools, history) == [CREATE_NAME, SEARCH_NAME]

    fake.tools = [SEARCH]  # the server stopped listing one
    await hub.connect()
    hub.attach({"default": deps})
    assert loaded_names(deps.tools, history) == [SEARCH_NAME]

    deps.profile = replace(deps.agent, mcp=())  # the owner took the server back
    hub.attach({"default": deps})
    assert loaded_names(deps.tools, history) == []
    assert [spec.name for spec in declared_specs(deps.tools, history)] == own


async def test_a_loaded_tool_since_let_in_directly_is_told_once(deps_factory, store):
    deps, own, hub = await handed(deps_factory, server(tool_exposure={"search": "direct"}))
    conv = store.create()
    said(store, conv.id, SEARCH_TOOL, f"- {SEARCH_NAME}: Find.\n- {CREATE_NAME}: Make.")

    told = [spec.name for spec in declared_specs(deps.tools, store.history(conv.id))]

    assert told == [*own, SEARCH_TOOL, SEARCH_NAME, CREATE_NAME]
    assert deps.tools.get(CREATE_NAME).spec.parameters == CREATE["inputSchema"]
