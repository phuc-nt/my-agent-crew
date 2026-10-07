"""What a script may look up of the tools it can call, and what it is told when it gets one
wrong: `tools.names`, `tools.search` and `tools.describe` ask the process that holds the
tools and run none; a name no tool has comes back with the nearest one; a call that failed on
its parameters is answered with how the tool is called (`script/namespaces.py`,
`script/discovery.py`, `script/scope.py`, `script/signature.py`, `script/tool.py`)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx
import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.profile import ASSISTANT, WORK
from my_agent_crew.mcp.tool_search import DEFAULT_LIMIT, MAX_LIMIT, rank
from my_agent_crew.mcp.tools import SUMMARY_CHARS
from my_agent_crew.script.discovery import discover
from my_agent_crew.script.limits import (
    MAX_CALLS,
    MAX_LOOKUP_CHARS,
    MAX_LOOKUPS,
    MAX_VALUE,
    ScriptError,
)
from my_agent_crew.script.namespaces import LOOKUPS
from my_agent_crew.script.scope import scriptable, why_not
from my_agent_crew.script.signature import MAX_DESCRIBED
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.registry import Tool, ToolError
from tests.script_helpers import play as run_alone
from tests.script_helpers import printed, stopped
from tests.test_mcp_tool_search import CREATE_NAME, SEARCH_NAME
from tests.test_script_tool import SCHEMA, Reads, erred, notion, play, toolbox, unfinished

USAGE = {
    "names": "tools.names()",
    "search": "tools.search(query, limit=5)",
    "describe": "tools.describe(name)",
}


def stand_ins(seen: list, **answers: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """What the parent would answer to each lookup, keeping what it was asked in `seen`."""

    def answering(kind: str, answer: Any) -> Callable[[dict[str, Any]], Any]:
        def ask(arguments: dict[str, Any]) -> Any:
            seen.append((kind, arguments))
            return answer

        return ask

    return {kind: answering(kind, answer) for kind, answer in answers.items()}


def reader(name: str, description: str, schema: dict | None = None, **flags: Any) -> Tool:
    """A tool that only reads, told apart by the words it is described with."""

    async def run(arguments: dict[str, Any]) -> str:
        return f"ran {name}"

    flags.setdefault("replay_safe", True)
    return Tool(name, description, schema or SCHEMA, run, **flags)


# The interpreter alone: how a lookup is written and counted, and what it hands the script.


def test_a_lookup_goes_to_the_parent_with_its_parameters_by_name_however_it_was_written():
    seen: list = []

    ended = run_alone(
        """
        tools.names()
        tools.search("kế hoạch")
        tools.search("kế hoạch", 3)
        tools.search("kế hoạch", limit=3)
        tools.search(limit=3, query="kế hoạch")
        tools.describe("a")
        tools.describe(name="a")
        """,
        lookups=stand_ins(seen, names=["a"], search=[], describe="a()"),
    )

    assert ended["ok"] and ended["asked"] == []
    assert seen == [
        ("names", {}),
        ("search", {"query": "kế hoạch"}),
        ("search", {"query": "kế hoạch", "limit": 3}),
        ("search", {"query": "kế hoạch", "limit": 3}),
        ("search", {"query": "kế hoạch", "limit": 3}),
        ("describe", {"name": "a"}),
        ("describe", {"name": "a"}),
    ]


def test_what_a_lookup_answers_is_data_a_script_works_on():
    parent = stand_ins(
        [],
        names=["rows_read", "notes_read"],
        search=[{"name": "rows_read", "description": "Đọc dòng."}],
        describe="rows_read(page?: integer)",
    )

    said = printed(
        """
        names = sorted(tools.names())
        found = tools.search("dòng")
        print(len(names), names[0], found[0]["name"], found[0]["description"])
        print(tools.describe("rows_read").upper())
        """,
        lookups=parent,
    )

    assert said == "2 notes_read rows_read Đọc dòng.\nROWS_READ(PAGE?: INTEGER)\n"


@pytest.mark.parametrize(
    ("call", "kind"),
    [
        ("tools.names(1)", "names"),
        ("tools.names(page=1)", "names"),
        ("tools.search()", "search"),
        ("tools.search(5)", "search"),
        ("tools.search(['a'])", "search"),
        ("tools.search({'query': 'a'})", "search"),
        ("tools.search(q='a')", "search"),
        ("tools.search('a', '3')", "search"),
        ("tools.search('a', limit=True)", "search"),
        ("tools.search('a', limit=2.0)", "search"),
        ("tools.search('a', 1, 2)", "search"),
        ("tools.search('a', query='b')", "search"),
        (f"tools.search('{'x' * (MAX_LOOKUP_CHARS + 1)}')", "search"),
        ("tools.describe()", "describe"),
        ("tools.describe(name=3)", "describe"),
        ("tools.describe({'name': 'a'})", "describe"),
        ("tools.describe('a', 'b')", "describe"),
        (f"tools.describe('{'y' * (MAX_LOOKUP_CHARS + 1)}')", "describe"),
    ],
)
def test_a_lookup_written_wrong_fails_in_a_way_the_script_may_catch_and_asks_no_one(call, kind):
    seen: list = []

    said = printed(
        f"""
        try:
            {call}
        except Exception as e:
            print(e)
        """,
        lookups=stand_ins(seen, names=[], search=[], describe=""),
    )

    assert said == f"{t.SCRIPT_LOOKUP_USAGE.format(shape=USAGE[kind])}\n"
    assert seen == []


def test_a_lookup_is_asked_with_a_text_as_long_as_the_most_and_the_text_is_kept_whole():
    seen: list = []
    most = "x" * MAX_LOOKUP_CHARS

    printed(f"tools.search('{most}')", lookups=stand_ins(seen, search=[]))

    assert seen == [("search", {"query": most})]


def test_a_lookup_is_not_counted_among_the_calls_nor_a_call_among_the_lookups():
    seen: list = []

    said = printed(
        f"""
        for n in range({MAX_LOOKUPS}):
            tools.names()
        for n in range({MAX_CALLS}):
            tools.read()
        print("both spent")
        """,
        {"read": lambda arguments: "ok"},
        stand_ins(seen, names=[]),
    )

    assert said == "both spent\n" and len(seen) == MAX_LOOKUPS


def test_the_lookup_past_the_most_fails_in_a_way_the_script_may_catch_and_is_not_asked():
    seen: list = []

    said = printed(
        f"""
        for n in range({MAX_LOOKUPS}):
            tools.names()
        try:
            tools.names()
        except Exception as e:
            print(e)
        print(tools.read())
        """,
        {"read": lambda arguments: "ok"},
        stand_ins(seen, names=[]),
    )

    assert said == f"{t.SCRIPT_TOO_MANY_LOOKUPS.format(most=MAX_LOOKUPS)}\nok\n"
    assert len(seen) == MAX_LOOKUPS


def test_the_call_past_the_most_still_ends_the_script_after_as_many_lookups_as_may_be_made():
    ended = run_alone(
        f"""
        for n in range({MAX_LOOKUPS}):
            tools.names()
        for n in range({MAX_CALLS + 1}):
            tools.read()
        """,
        {"read": lambda arguments: "ok"},
        stand_ins([], names=[]),
    )

    assert not ended["ok"]
    assert ended["error"].endswith(t.SCRIPT_TOO_MANY_CALLS.format(most=MAX_CALLS))
    assert len(ended["asked"]) == MAX_CALLS


def test_a_lookup_the_parent_refuses_fails_in_a_way_the_script_may_catch():
    def refuse(arguments: dict[str, Any]) -> Any:
        raise ScriptError("không có công cụ đó")

    said = printed(
        """
        try:
            tools.describe("nope")
        except Exception as e:
            print("hỏi lại:", e)
        print(len(tools.names()))
        """,
        lookups={"describe": refuse, "names": lambda arguments: ["a"]},
    )

    assert said == "hỏi lại: không có công cụ đó\n1\n"


@pytest.mark.parametrize(("kind", "args"), [("names", ""), ("search", "'a'"), ("describe", "'a'")])
def test_a_name_that_is_a_lookup_is_never_a_call_of_a_tool(kind, args):
    ended = run_alone(
        f"print(tools.{kind}({args}))",
        {kind: lambda arguments: "called as a tool"},
        stand_ins([], **{kind: "looked up"}),
    )

    assert (ended["ok"], ended["output"], ended["asked"]) == (True, "looked up\n", [])


def test_what_a_lookup_answers_is_counted_like_any_value_a_script_holds():
    answer = {"describe": lambda arguments: "x" * (MAX_VALUE + 1)}

    error = stopped("tools.describe('a')", lookups=answer)

    assert error == t.SCRIPT_HALTED.format(line=1, reason=t.SCRIPT_OUT_OF_ROOM)


# The tools as the agent holds them: what each lookup answers.


async def test_names_are_what_a_script_may_call_in_the_order_the_agent_holds_them():
    held = [
        Reads("rows_read").tool,
        Reads("notes_write", replay_safe=False).tool,
        Reads("progress_note").tool,
        *notion(read_only=["search", "create-page"], tool_exposure={"create-page": "hidden"}),
        Reads("guarded_read", requires_approval=True).tool,
        Reads("notes_read").tool,
        Reads("always_asks", ask_reason=lambda arguments: "luôn hỏi").tool,
    ]

    result = await play(toolbox(*held), 'print("\\n".join(tools.names()))')

    # What only reads and asks nobody; a hidden tool, the script tool and the agent's own
    # voice are none of them a script's.
    assert (result.ok, result.output) == (True, f"rows_read\n{SEARCH_NAME}\nnotes_read")
    assert result.calls == ()


async def test_a_tool_the_owner_did_not_tell_a_script_of_is_among_the_names_all_the_same():
    registry = toolbox(*notion(read_only=["search"], exposure="deferred"))

    result = await play(registry, "print(tools.names())")

    assert result.output == f"['{SEARCH_NAME}']"
    assert SEARCH_NAME not in registry.get("tool_script").description


async def test_a_search_answers_with_the_tools_that_fit_best_first_and_none_it_may_not_call():
    held = [
        reader("fetch_read", "Search result reader, search again."),
        reader("page_search", "Look things up."),
        reader("search_write", "Search and write notes.", replay_safe=False),
        reader("search_ask", "Search, asking first.", requires_approval=True),
        reader("progress_note", "Search the progress notes."),
        *notion(read_only=["search", "create-page"], tool_exposure={"search": "hidden"}),
    ]

    result = await play(toolbox(*held), 'print(json.dumps(tools.search("search")))')

    # A word in a name outweighs two in a description, and neither tool is first because
    # it was held first. Nothing is a hit that a script could not call.
    assert json.loads(result.output) == [
        {"name": "page_search", "description": "Look things up."},
        {"name": "fetch_read", "description": "Search result reader, search again."},
    ]
    assert result.calls == ()


async def test_a_search_answers_five_by_default_and_never_more_than_the_most():
    held = [reader(f"note{n}_read", "Notes of one kind.") for n in range(MAX_LIMIT + 2)]

    result = await play(
        toolbox(*held),
        """
        print(len(tools.search("notes")), len(tools.search("notes", 3)), end=" ")
        print(len(tools.search("notes", limit=500)), len(tools.search("notes", 0)), end=" ")
        print(len(tools.search("notes", -2)))
        """,
    )

    assert result.output == f"{DEFAULT_LIMIT} 3 {MAX_LIMIT} 1 1"
    assert result.calls == ()


@pytest.mark.parametrize("query", ["zzzz", "", "   ", "?!"])
async def test_a_search_that_matches_nothing_answers_an_empty_list(query):
    registry = toolbox(reader("rows_read", "Đọc dòng."))

    result = await play(registry, f"print(tools.search({query!r}))")

    assert (result.ok, result.output) == (True, "[]")


async def test_a_search_gives_each_description_on_one_line_cut_short():
    held = [
        reader("long_read", "Dòng một.\n\n   Dòng   hai.  " + "x" * 400),
        reader("short_read", "Dòng một.\nDòng hai."),
    ]

    result = await play(toolbox(*held), 'print(json.dumps(tools.search("dòng", 10)))')

    said = {hit["name"]: hit["description"] for hit in json.loads(result.output)}
    assert said["short_read"] == "Dòng một. Dòng hai."
    head = "Dòng một. Dòng hai. "
    assert said["long_read"] == head + "x" * (SUMMARY_CHARS - 1 - len(head)) + "…"


async def test_a_tool_not_told_up_front_is_found_by_a_search_and_then_called_by_name():
    calls: list = []
    registry = toolbox(*notion(calls, read_only=["search"], exposure="deferred"))

    found = await play(registry, 'print(json.dumps(tools.search("pages")))')
    [hit] = json.loads(found.output)
    result = await play(registry, f"print(tools.{hit['name']}(query='kế hoạch'))")

    assert hit == {"name": SEARCH_NAME, "description": "[MCP notion] Find pages by words."}
    assert (result.ok, result.output) == (True, "ran search")
    assert calls == [("search", {"query": "kế hoạch"})]


DETAILED = {
    "name": "query",
    "description": "Run a query over pages.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "What to look for."},
            "limit": {"type": "integer"},
            "mode": {"type": "string", "enum": ["fast", "deep"], "description": "How hard."},
            "filter": {
                "type": "object",
                "properties": {"owner": {"type": "string", "description": "Who wrote it."}},
            },
            "ids": {"type": "array", "items": {"type": "string"}},
            "pages": {
                "type": "array",
                "items": {"type": "object", "properties": {"title": {"type": "string"}}},
            },
        },
        "required": ["text"],
    },
}


async def test_describe_gives_the_call_the_description_and_each_parameter_by_its_path():
    registry = toolbox(*notion(listed=[DETAILED], read_only=["query"]))

    result = await play(registry, 'print(tools.describe("mcp__notion__query"))')

    assert result.output == "\n".join(
        [
            "mcp__notion__query(text: string, limit?: integer, mode?: string, "
            "filter?: object, ids?: array, pages?: array)",
            "[MCP notion] Run a query over pages.",
            "Tham số:",
            "- text (string, bắt buộc): What to look for.",
            "- limit (integer)",
            '- mode (string: "fast"|"deep"): How hard.',
            "- filter (object)",
            "- filter.owner (string): Who wrote it.",
            "- ids (array<string>)",
            "- pages (array<object>)",
            "- pages[].title (string)",
        ]
    )
    assert result.calls == ()


async def test_describe_of_a_tool_with_no_parameters_says_so():
    result = await play(toolbox(Reads("rows_read").tool), 'print(tools.describe("rows_read"))')

    assert result.output == "rows_read()\nĐọc rows_read.\nKhông có tham số."


async def test_describe_stops_after_two_thousand_characters_a_whole_line_at_a_time():
    schema = {
        "type": "object",
        "properties": {
            f"p{n:02d}": {"type": "string", "description": "x" * 100} for n in range(60)
        },
    }

    result = await play(
        toolbox(reader("wide_read", "Wide.", schema)), 'print(tools.describe("wide_read"))'
    )

    body, cut = result.output.rsplit("\n", 1)
    assert cut == t.SCRIPT_DESCRIBE_CUT
    kept = [line for line in body.splitlines() if line.startswith("- p")]
    assert kept == [f"- p{n:02d} (string): {'x' * 100}" for n in range(len(kept))]
    # What is kept fills the room; the next line would not have fitted in it.
    after = f"- p{len(kept):02d} (string): {'x' * 100}"
    assert len(body) + 1 <= MAX_DESCRIBED < len(body) + 1 + len(after) + 1


async def test_describe_of_a_name_no_tool_has_names_the_nearest_and_may_be_caught():
    registry = toolbox(Reads("rows_read").tool, Reads("notes_write", replay_safe=False).tool)

    result = await play(
        registry,
        """
        try:
            tools.describe("row_read")
        except Exception as e:
            print(e)
        tools.describe("notes_writes")
        """,
    )

    near = t.SCRIPT_DID_YOU_MEAN.format(near="rows_read")
    mistake = t.SCRIPT_UNKNOWN_TOOL.format(name="row_read", near=near)
    # A tool a script may not call is not offered as the one it meant.
    lost = t.SCRIPT_UNKNOWN_TOOL.format(name="notes_writes", near="")
    assert (result.ok, result.output) == (False, unfinished(mistake, erred(6, lost)))


@pytest.mark.parametrize(
    ("name", "why", "instead"),
    [
        ("notes_write", t.SCRIPT_ASKS_FIRST, t.SCRIPT_CALL_DIRECTLY),
        ("progress_note", t.SCRIPT_NOT_FROM_SCRIPT, t.SCRIPT_CALL_DIRECTLY),
        (CREATE_NAME, t.SCRIPT_ASKS_FIRST, t.SCRIPT_LOAD_THEN_CALL),
    ],
)
async def test_describe_of_a_tool_held_and_not_a_scripts_says_what_to_do_instead(
    name, why, instead
):
    held = [
        Reads("notes_write", replay_safe=False).tool,
        Reads("progress_note").tool,
        *notion(read_only=["search"], exposure="deferred"),
    ]

    result = await play(
        toolbox(*held),
        f"""
        try:
            tools.describe("{name}")
        except Exception as e:
            print(e)
        """,
    )

    assert (result.ok, result.output) == (True, why.format(name=name, instead=instead))


PAGES = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "page": {"type": "integer"}},
    "required": ["query"],
}
HOW = t.SCRIPT_CALL_LIKE.format(line="pages_read(query: string, page?: integer)")


async def test_a_call_that_failed_on_its_parameters_is_answered_with_how_the_tool_is_called():
    async def run(arguments: dict[str, Any]) -> str:
        if arguments.get("page") == 99:
            raise ToolError("máy chủ bận")
        if "query" not in arguments or "colour" in arguments:
            raise ToolError("tham số sai")
        return "ok"

    registry = toolbox(Tool("pages_read", "Tìm trang.", PAGES, run, replay_safe=True))

    result = await play(
        registry,
        """
        for given in [{}, {"query": "a", "colour": "red"}, {"query": "a", "page": 99}]:
            try:
                tools.pages_read(given)
            except Exception as e:
                print(e)
                print("--")
        print(tools.pages_read(query="a"))
        """,
    )

    wrong, busy = TOOL_FAILED.format(error="tham số sai"), TOOL_FAILED.format(error="máy chủ bận")
    # A required parameter left out, or one the tool has no place for, is told how it is
    # called after what the tool said; a call that fitted and failed is told nothing more.
    assert result.output == "\n".join([wrong, HOW, "--", wrong, HOW, "--", busy, "--", "ok"])
    calls = result.calls
    assert [call.ok for call in calls] == [False, False, False, True]
    assert [HOW in call.output for call in calls] == [True, True, False, False]


async def test_a_call_that_worked_is_told_nothing_more_though_it_did_not_fit():
    async def run(arguments: dict[str, Any]) -> str:
        return "ok"

    registry = toolbox(Tool("pages_read", "Tìm trang.", PAGES, run, replay_safe=True))

    result = await play(registry, 'print(tools.pages_read(colour="red"))')

    assert (result.ok, result.output) == (True, "ok")
    assert [call.output for call in result.calls] == ["ok"]


# A name a script cannot use for a tool, and a tool that is searched without a server.


@pytest.mark.parametrize("kind", sorted(LOOKUPS))
async def test_a_tool_named_like_a_lookup_is_not_one_a_script_may_call(kind):
    named = Reads(kind).tool

    result = await play(toolbox(named, Reads("rows_read").tool), "print(tools.names())")

    assert not scriptable(named)
    assert why_not(named) == t.SCRIPT_NOT_FROM_SCRIPT.format(
        name=kind, instead=t.SCRIPT_CALL_DIRECTLY
    )
    assert result.output == "['rows_read']"


@pytest.mark.parametrize("mode", [ASSISTANT, WORK])
@pytest.mark.parametrize("master", [True, False])
def test_no_tool_the_product_builds_has_the_name_of_a_lookup(settings, store, mode, master):
    """A built-in so named would be shut out of every script, and no one would see it
    go: the lookups own those names, and a new tool takes another."""
    profile = replace(default_profile(settings), mode=mode, id="default" if master else "other")

    held = build_tools(profile, httpx.AsyncClient(), store, []).names()

    assert held and not set(held) & set(LOOKUPS)


def test_tools_that_are_not_an_mcp_servers_are_searched_the_same_way():
    tools = [
        reader("rows_read", "Notes, notes, notes and more notes."),
        reader("notes_read", "Read it. " + "Filler words go here. " * 5),
    ]

    assert [tool.name for tool in rank(tools, "rows")] == ["rows_read"]
    # By its words the first fits better; named outright, the second comes before it.
    assert [tool.name for tool in rank(tools, "notes read")] == ["rows_read", "notes_read"]
    assert [tool.name for tool in rank(tools, "notes_read")] == ["notes_read", "rows_read"]


# What the parent is asked is checked again, whoever asked.


@pytest.mark.parametrize(
    ("kind", "arguments"),
    [
        ("search", {}),
        ("search", {"query": 5}),
        ("search", {"query": None, "limit": 3}),
        ("search", {"query": ["a"]}),
        ("search", {"query": "a", "limit": "3"}),
        ("search", {"query": "a", "limit": True}),
        ("search", {"query": "a", "limit": 2.0}),
        ("search", {"query": "a", "limit": None}),
        ("describe", {}),
        ("describe", {"name": 3}),
        ("describe", {"name": None}),
        ("describe", {"name": ["rows_read"]}),
        ("tools", {}),
        ("run", {"script": "print(1)"}),
        ("", {}),
    ],
)
def test_a_question_asked_wrongly_is_refused_though_the_script_never_asks_it_so(kind, arguments):
    registry = toolbox(reader("rows_read", "Đọc dòng."))

    with pytest.raises(ScriptError) as refused:
        discover(registry, kind, arguments)

    assert str(refused.value) == t.SCRIPT_BAD_CALL.format(name=f"tools.{kind}")
