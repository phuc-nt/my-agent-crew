"""A tool whose parameters are more than is taken as its server wrote them: when it is
taken folded, what a model is told of it, and what everything else here goes on reading
(`mcp/tool_limits.py`, `mcp/tools.py`, `mcp/hub.py`)."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest

from my_agent_crew.agent.declared_tools import declared_specs
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message
from my_agent_crew.mcp.schema_fold import MAX_FOLD_CHARS, fold
from my_agent_crew.mcp.tool_limits import MAX_SCHEMA_CHARS
from my_agent_crew.mcp.tool_search import SEARCH_TOOL, rank
from my_agent_crew.mcp.tools import McpTool, build_tools
from my_agent_crew.script.signature import call_line, describe
from tests.conftest import collect
from tests.mcp_fakes import SEARCH, FakeMcp, make_hub, server
from tests.mcp_schema_fakes import (
    FOUND,
    FOUND_NAME,
    UNREAD,
    chars,
    padded,
    parameters,
    text,
    unfolded,
    where,
)
from tests.test_openrouter import delta, provider_with, sse

LOGGER = "my_agent_crew.mcp.tools"
QUERY = "mcp__notion__query"
LEFT_OUT = ("WARNING", "MCP server notion: tool 'query' left out, its parameters are too large")


async def never_called(name, arguments):
    raise AssertionError("no call is made while tools are only being listed")


def query(schema: dict) -> dict:
    return {
        "name": "query",
        "description": "Rows of a table that pass its filters.",
        "inputSchema": schema,
    }


def built(*listed: dict, **settings) -> tuple[tuple[McpTool, ...], tuple[str, ...]]:
    return build_tools(server(**settings), listed, never_called)


def logged(caplog) -> list[tuple[str, str]]:
    return [(r.levelname, r.getMessage()) for r in caplog.records if r.name == LOGGER]


def with_definitions() -> dict:
    """Parameters that come with definitions and pointers of their own, and repeat besides."""
    schema = parameters(kinds=5)
    schema["$defs"] = {"where": where(5)}
    schema["properties"]["also"] = {"$ref": "#/$defs/where"}
    return schema


def deep() -> dict:
    schema = inner = {"type": "object"}
    for _ in range(1500):
        inner["properties"] = {"a": {"type": "object"}}
        inner = inner["properties"]["a"]
    return schema


def test_a_tool_whose_parameters_fit_once_folded_is_taken_and_told_folded(caplog):
    schema = parameters()

    with caplog.at_level(logging.INFO, logger=LOGGER):
        [tool], skipped = built(query(schema))

    told = tool.spec.parameters
    assert skipped == ()
    assert chars(schema) > MAX_SCHEMA_CHARS >= chars(told)
    assert text(unfolded(told)) == text(schema)
    # What the server wrote is what the tool keeps, for everything that reads it here.
    assert tool.parameters is schema
    assert (tool.spec.name, tool.spec.description) == (tool.name, tool.description)
    assert tool.folded.to_dict() == {"from": chars(schema), "to": chars(told)}
    assert logged(caplog) == [
        (
            "INFO",
            f"MCP server notion: tool 'query' parameters folded, {chars(schema)} chars "
            f"to {chars(told)}",
        )
    ]


@pytest.mark.parametrize(
    "schema",
    [parameters(kinds=8), padded(parameters(kinds=8), MAX_SCHEMA_CHARS), with_definitions()],
    ids=["repeats", "exactly as much as is taken", "definitions of its own"],
)
def test_parameters_that_fit_are_handed_on_as_the_server_wrote_them(schema, caplog):
    """They repeat as much as the ones that are folded do. Nothing asks for them shorter."""
    before = text(schema)
    assert fold(schema) is not None

    with caplog.at_level(logging.INFO, logger=LOGGER):
        [tool], skipped = built(query(schema))

    assert skipped == () and tool.folded is None
    assert tool.spec.parameters is schema and tool.parameters is schema
    assert text(tool.spec.parameters) == before
    assert logged(caplog) == []


def test_one_letter_more_than_is_taken_is_what_folds_them():
    schema = padded(parameters(kinds=8), MAX_SCHEMA_CHARS + 1)

    [tool], _ = built(query(schema))

    assert tool.folded.before == MAX_SCHEMA_CHARS + 1
    assert text(unfolded(tool.spec.parameters)) == text(schema)


def test_a_tool_still_too_large_once_folded_is_left_out_and_named_as_before(caplog):
    schema = parameters()
    schema["properties"]["note"] = {"type": "string", "description": "x" * MAX_SCHEMA_CHARS}
    assert MAX_SCHEMA_CHARS < chars(fold(schema)) < chars(schema)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        tools, skipped = built(query(schema), SEARCH)

    assert [tool.remote for tool in tools] == ["search"] and skipped == ("query",)
    assert logged(caplog) == [LEFT_OUT]


def test_the_size_asked_of_a_folded_tool_is_the_folded_forms():
    base = parameters()
    some = padded(base, chars(base) + 100)
    most = chars(some) + MAX_SCHEMA_CHARS - chars(fold(some))

    [fits], none = built(query(padded(base, most)))
    tools, skipped = built(query(padded(base, most + 1)))

    assert none == () and fits.folded.to_dict() == {"from": most, "to": MAX_SCHEMA_CHARS}
    assert tools == () and skipped == ("query",)


@pytest.mark.parametrize(
    "make",
    [
        lambda: {**parameters(), "$id": "https://example.test/query"},
        lambda: padded(parameters(tuple(f"place{n}" for n in range(26))), MAX_FOLD_CHARS + 1),
        lambda: {"type": "object", "properties": {"x": deep(), "y": deep()}},
    ],
    ids=["names itself", "longer than is read", "nested deeper than can be walked"],
)
def test_parameters_too_large_that_are_not_folded_leave_the_tool_out_as_before(make, caplog):
    schema = make()
    assert chars(schema) > MAX_SCHEMA_CHARS

    with caplog.at_level(logging.INFO, logger=LOGGER):
        tools, skipped = built(query(schema), SEARCH)

    assert [tool.remote for tool in tools] == ["search"] and skipped == ("query",)
    assert logged(caplog) == [LEFT_OUT]


def test_a_tool_left_out_for_its_name_is_not_said_to_be_folded(caplog):
    """Two names that come to one here. The second is left out, and its parameters, which
    would have been folded, are nothing anyone is told."""
    first = {**query({"type": "object", "properties": {}}), "name": "query_rows"}
    second = {**query(parameters()), "name": "query.rows"}

    with caplog.at_level(logging.INFO, logger=LOGGER):
        tools, skipped = built(first, second)

    assert [tool.remote for tool in tools] == ["query_rows"] and skipped == ("query.rows",)
    assert [tool.folded for tool in tools] == [None]
    assert logged(caplog) == [
        ("WARNING", "MCP server notion: tool 'query.rows' left out, its name is taken")
    ]


async def test_the_owner_is_shown_which_tools_are_told_folded():
    schema = parameters()
    hub = make_hub(FakeMcp([query(schema), SEARCH]))
    await hub.connect()

    [row] = hub.describe({})

    assert row["skipped"] == []
    assert [(tool["remote"], tool["folded"]) for tool in row["tools"]] == [
        ("query", {"from": chars(schema), "to": chars(fold(schema))}),
        ("search", None),
    ]


def test_a_search_reads_a_folded_tools_parameters_as_the_server_wrote_them():
    tools, _ = built(query(parameters()), SEARCH)

    assert [tool.remote for tool in rank(tools, FOUND)] == ["query"]
    assert [tool.remote for tool in rank(tools, FOUND_NAME)] == ["query"]
    # No deeper than a search reads any schema. Folded, that part stands nearer the top,
    # and a search of what the model is told would find it.
    assert rank(tools, UNREAD) == []
    assert rank([replace(tools[0], parameters=tools[0].spec.parameters)], UNREAD) != []


def test_a_script_is_told_of_a_folded_tool_by_what_the_server_wrote():
    [tool], _ = built(query(parameters()))

    # The model is told `since` by a pointer, which says nothing of its kind.
    assert list(tool.spec.parameters["properties"]["since"]) == ["$ref"]
    assert call_line(tool) == (
        "mcp__notion__query(filter: object, exclude?: object, highlight?: object, "
        "group?: object, since?: object, until?: object)"
    )
    said = describe(tool).splitlines()
    assert "- since (object): A day and an hour of it, in the owner's own time." in said
    assert "- since.hour (integer)" in said


async def handed(deps_factory, schema: dict, **settings):
    hub = make_hub(FakeMcp([query(schema), SEARCH]), server(**settings))
    await hub.connect()
    deps = deps_factory(script=[completion("ok")])
    deps.profile = replace(deps.agent, mcp=("notion",))
    hub.attach({"default": deps})
    return deps


async def test_a_model_is_told_a_folded_tool_folded_on_every_call(deps_factory):
    schema = parameters()
    deps = await handed(deps_factory, schema, tool_exposure={"query": "direct"})
    conv = deps.store.create()

    await collect(run_turn(deps, conv.id, "hi"))

    [request] = deps.chain.providers["scripted"].requests
    told = {spec.name: spec.parameters for spec in request.tools}[QUERY]
    assert chars(told) <= MAX_SCHEMA_CHARS and text(unfolded(told)) == text(schema)

    # The same list as a provider writes it out: the long form is nowhere in what is sent.
    captured: list = []
    provider = provider_with(sse(delta("ok"), delta(finish="stop")), capture=captured)
    await collect(provider.stream([Message(role="user", content="hi")], request.tools, "x/y"))
    wired = [tool["function"] for tool in json.loads(captured[0].content)["tools"]]
    [sent] = [function["parameters"] for function in wired if function["name"] == QUERY]
    assert text(sent) == text(told)
    assert len(captured[0].content) < chars(schema)


async def test_a_folded_tool_loaded_by_a_search_is_told_folded_too(deps_factory, store):
    schema = parameters()
    deps = await handed(deps_factory, schema)
    conv = store.create()
    assert QUERY not in [spec.name for spec in declared_specs(deps.tools)]

    found = await deps.tools.execute(SEARCH_TOOL, {"query": FOUND})
    store.append(
        conv.id, Message(role="tool", content=found.output, tool_call_id="c", name=SEARCH_TOOL)
    )

    # A search answers with a name and a line; it writes out no parameters.
    assert QUERY in found.output and len(found.output) < 1000
    specs = declared_specs(deps.tools, store.history(conv.id))
    [told] = [spec.parameters for spec in specs if spec.name == QUERY]
    assert chars(told) <= MAX_SCHEMA_CHARS and text(unfolded(told)) == text(schema)
