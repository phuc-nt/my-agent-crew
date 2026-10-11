"""Who is built with `tool_script`, and where among its tools: every agent that holds a tool
a script may call, whatever its servers, its `tools:` list and its mode say; what a crew
leaves of it when it wires an agent again, and what the master is told of who has it
(`script/tool.py`, `server/agent_assembly.py`, `mcp/handout.py`). What a hand-out of a
server's tools does to it is in `test_script_tool.py`."""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from my_agent_crew.agent.declared_tools import declared_names
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.profile import ASSISTANT, WORK
from my_agent_crew.llm.fake import EchoProvider, ScriptedProvider
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.script.scope import SCRIPT_TOOL, callable_tools
from my_agent_crew.script.signature import call_line
from my_agent_crew.server.agent_assembly import build_agent_deps
from my_agent_crew.server.crew_abilities import crew_abilities
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from my_agent_crew.tools.registry import ToolRegistry
from tests.mcp_fakes import FakeMcp, make_hub, server
from tests.test_crew_roster_abilities import TOOLS as TOLD_TOOLS
from tests.test_crew_roster_abilities import crew_of, said
from tests.test_mcp_tool_search import CREATE_NAME, SEARCH_NAME, handed
from tests.test_script_tool import OPENED, play

OWN_PART, SERVED_PART = "Công cụ có sẵn gọi được từ script", "Công cụ MCP gọi được từ script"


@pytest.fixture
async def assembled(settings, store):
    """An agent as the server builds it from its profile, before any server is handed out."""
    providers = {"scripted": ScriptedProvider([]), "fake": EchoProvider()}
    async with httpx.AsyncClient() as client:

        def build(**profile) -> AgentDeps:
            made = replace(default_profile(settings), **profile)
            return build_agent_deps(made, providers, client, store)

        yield build


def listed(deps: AgentDeps) -> list[str]:
    """The tools the script tool names, a line each."""
    told = deps.tools.get(SCRIPT_TOOL).description
    return [line for line in told.splitlines() if line.startswith("- ")]


async def test_an_agent_that_names_no_server_is_built_with_the_script_tool_last(assembled):
    deps = assembled()

    names = deps.tools.names()
    assert deps.agent.mcp == ()
    assert names[-1] == SCRIPT_TOOL and names.count(SCRIPT_TOOL) == 1
    # What a script of it calls are its own tools that only read.
    reads = [tool.name for tool in callable_tools(deps.tools)]
    assert {"workspace_list", "workspace_read", "memory_search", "skill_read"} <= set(reads)
    assert not {"workspace_write", "shell_run", "memory_save", SCRIPT_TOOL} & set(reads)


@pytest.mark.parametrize("mode", [ASSISTANT, WORK])
async def test_the_script_tool_follows_neither_the_tools_list_nor_the_mode(assembled, mode):
    # `tools:` names one tool, and not this one. The agent reads, so a script of it may.
    deps = assembled(tools=("workspace_read",), mode=mode)

    assert deps.tools.names() == ["workspace_read", SCRIPT_TOOL]
    assert listed(deps) == ["- workspace_read(path: string, offset?: integer, limit?: integer)"]


@pytest.mark.parametrize(
    "tools",
    [
        ("workspace_write",),
        ("memory_save", "shell_run"),
        ("ask_user",),
        # It only reads, and speaks for the agent: no script's to call (`script/scope.py`).
        ("progress_note",),
    ],
)
async def test_an_agent_with_no_tool_a_script_may_call_is_built_without_the_script_tool(
    assembled, tools
):
    deps = assembled(tools=tools)

    assert deps.tools.names() == list(tools)


async def test_a_script_of_an_agent_with_no_server_reads_its_files(assembled):
    deps = assembled()
    (deps.agent.workspace / "ghi.txt").write_text("ba\nbốn\n", encoding="utf-8")

    result = await play(deps.tools, 'print(tools.workspace_read(path="ghi.txt").split())')

    assert (result.ok, result.output) == (True, "['ba', 'bốn']")
    assert [call.name for call in result.calls] == ["workspace_read"]


async def test_the_script_tool_names_each_of_the_agents_own_tools_with_its_parameters(assembled):
    deps = assembled()

    told = deps.tools.get(SCRIPT_TOOL).description
    # In the order the agent holds them. What each is for is in its own declaration.
    assert listed(deps) == [f"- {call_line(tool)}" for tool in callable_tools(deps.tools)]
    head = f"\n{OWN_PART} (tham số như khi gọi trực tiếp):\n- workspace_list(path?: string)\n"
    assert head in told and SERVED_PART not in told
    assert "- workspace_read(path: string, offset?: integer, limit?: integer)\n" in told


async def test_a_crew_keeps_the_script_tool_last_behind_the_tool_that_hands_work_out(assembled):
    deps = assembled()
    own = [name for name in deps.tools.names() if name != SCRIPT_TOOL]

    rt = Runtime.single(deps)

    assert rt.default.tools.names() == [*own, DELEGATE_TOOL_NAME, SCRIPT_TOOL]
    rt.wire_delegation()  # wired again, as when an agent is added or edited
    assert rt.default.tools.names() == [*own, DELEGATE_TOOL_NAME, SCRIPT_TOOL]
    # The one that hands work out is the turn's to call, and a script is not told of it.
    assert DELEGATE_TOOL_NAME not in rt.default.tools.get(SCRIPT_TOOL).description


async def test_a_script_calls_what_the_agent_holds_after_the_crew_wired_it(assembled):
    """The crew replaces an agent's tools when it wires the tool that hands work out: the
    script tool reads the tools the agent holds when a script runs, not when it was built."""
    deps = assembled()
    rt = Runtime.single(deps)
    held = rt.default
    held.tools = held.tools.without("workspace_list")

    refused = await play(held.tools, "tools.workspace_list()")
    answered = await play(held.tools, 'print(len(tools.search("đọc tệp")) > 0)')

    assert not refused.ok and "workspace_list" in refused.output
    assert (answered.ok, answered.output) == (True, "True")


async def test_a_server_coming_and_going_changes_what_the_script_tool_says_and_not_its_place(
    deps_factory,
):
    deps, own, hub = await handed(deps_factory, server(**OPENED), mcp=())
    alone = deps.tools.get(SCRIPT_TOOL).description
    assert deps.tools.names() == declared_names(deps.tools) == [*own, SCRIPT_TOOL]
    assert OWN_PART in alone and SERVED_PART not in alone

    deps.profile = replace(deps.agent, mcp=("notion",))
    hub.attach({"default": deps})

    served = deps.tools.get(SCRIPT_TOOL).description
    assert deps.tools.names() == [*own, SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME]
    # Told up front under the same name, behind the same tools of the agent's own.
    assert declared_names(deps.tools) == [*own, SEARCH_TOOL, SCRIPT_TOOL]
    assert listed(deps)[:-1] == [line for line in alone.splitlines() if line[:2] == "- "]
    assert listed(deps)[-1] == f"- {SEARCH_NAME}(query: string): [MCP notion] Find pages by words."

    out_of_reach = make_hub(FakeMcp(), server(**OPENED))  # never connected
    out_of_reach.attach({"default": deps})

    assert deps.tools.names() == declared_names(deps.tools) == [*own, SCRIPT_TOOL]
    assert deps.tools.get(SCRIPT_TOOL).description == alone != served


async def test_an_agent_that_only_writes_holds_the_script_tool_while_a_servers_tool_reads(
    deps_factory,
):
    hub = make_hub(FakeMcp(), server(**OPENED))
    await hub.connect()
    deps = deps_factory()
    deps.tools = ToolRegistry([deps.tools.get("workspace_write")])
    deps.profile = replace(deps.agent, mcp=("notion",))

    hub.attach({"default": deps})

    held = ["workspace_write", SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME]
    assert deps.tools.names() == held
    told = deps.tools.get(SCRIPT_TOOL).description
    assert OWN_PART not in told and listed(deps) == [
        f"- {SEARCH_NAME}(query: string): [MCP notion] Find pages by words."
    ]

    # The owner took `read_only` off: nothing is left for a script to call.
    closed = make_hub(FakeMcp(), server())
    await closed.connect()
    closed.attach({"default": deps})

    assert deps.tools.names() == ["workspace_write", SEARCH_TOOL, SEARCH_NAME, CREATE_NAME]


def test_the_master_is_told_which_agent_writes_scripts(deps_factory, store):
    rt = crew_of(deps_factory, store)
    master, helper = rt.default, rt.deps_for("helper")
    # Both read: neither is told apart by it.
    assert SCRIPT_TOOL in master.tools.names() and SCRIPT_TOOL in helper.tools.names()
    assert said(rt, TOLD_TOOLS) == "như của bạn"

    # The master reads nothing any more, and the helper one file at a time.
    reads = [tool.name for tool in callable_tools(master.tools)]
    master.tools = master.tools.without(*reads)
    helper.tools = helper.tools.without(*(name for name in reads if name != "workspace_read"))
    rt.wire_delegation()

    assert SCRIPT_TOOL not in master.tools.names()
    assert crew_abilities(rt)["helper"].tools[-1] == SCRIPT_TOOL
    assert said(rt, TOLD_TOOLS) == f"như của bạn, thêm: workspace_read, {SCRIPT_TOOL}"


def test_the_master_is_told_of_an_agent_left_with_no_script_tool(deps_factory, store):
    rt = crew_of(deps_factory, store)
    helper = rt.deps_for("helper")

    helper.tools = helper.tools.without("workspace_list", "skill_read")
    rt.wire_delegation()
    # It still reads, so it still writes scripts.
    assert said(rt, TOLD_TOOLS) == "như của bạn, không có: workspace_list, skill_read"

    helper.tools = ToolRegistry([helper.tools.get("workspace_write")])
    rt.wire_delegation()

    assert helper.tools.names() == ["workspace_write"]
    # Too unlike the master's to be told against them: listed whole, without it.
    assert said(rt, TOLD_TOOLS) == "workspace_write"
