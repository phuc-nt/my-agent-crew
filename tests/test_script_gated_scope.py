"""Which tools a script may call when its agent's file says `script_calls: gated`: what only
reads, as before, and what changes things too, but the tools that always wait for a person,
the ones kept from every script and a server's tool the owner hid (`script/scope.py`). What
such a script is told of them and finds when it looks, who is handed its script tool, and a
script of an agent as the server builds it writing a file and running a command
(`script/discovery.py`, `script/tool.py`, `mcp/handout.py`). What the approval gate says of
each call is in `test_script_gate.py`."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import httpx
import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.profile import ASSISTANT, WORK
from my_agent_crew.llm.fake import EchoProvider, ScriptedProvider
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.mcp.tools import McpTool
from my_agent_crew.script.limits import MAX_BATCH, MAX_CALLS
from my_agent_crew.script.namespaces import RESERVED
from my_agent_crew.script.scope import (
    ALWAYS_ASKS,
    NOT_FROM_SCRIPT,
    SCRIPT_TOOL,
    callable_tools,
    scriptable,
    why_not,
)
from my_agent_crew.script.signature import call_line
from my_agent_crew.script.tool import script_tool
from my_agent_crew.server.agent_assembly import build_agent_deps
from my_agent_crew.tools.registry import Tool, ToolRegistry
from tests.mcp_fakes import FakeMcp, server
from tests.test_mcp_tool_search import CREATE_NAME, SEARCH_NAME, handed
from tests.test_script_discovery import reader
from tests.test_script_gate import SUPERVISED, conversation, ran
from tests.test_script_tool import Reads, erred, halted, notion, play, toolbox, unfinished

GATED_PART = "Script của bạn gọi được cả công cụ ghi dữ liệu hay chạy lệnh."
READS_ONLY_PART = "Công cụ phải hỏi trước hoặc có ghi dữ liệu thì không gọi được từ script"
# What a script of an agent the server builds gains with `script_calls: gated`, in the order
# the agent holds them. A new tool that changes things lands here, or is kept from scripts.
GAINED = [
    "workspace_write",
    "memory_save",
    "user_memory_save",
    "user_memory_forget",
    "wiki_apply",
    "shell_run",
    "artifact_create",
    "artifact_edit",
    "artifact_rewrite",
    "artifact_import",
    "artifact_export",
]
STILL_OUT = ["ask_user", "progress_note", "schedule_create", "artifact_read", SCRIPT_TOOL]


def let_run(name: str, arguments: dict[str, Any]) -> None:
    """A gate that lets every call run, as the gate of an autonomous conversation does for
    a tool on no list."""
    return None


def gated_toolbox(*tools: Tool) -> ToolRegistry:
    """An agent's tools under the script tool of an agent whose scripts may change things."""
    registry = ToolRegistry(list(tools))
    scripted = [tool for tool in tools if isinstance(tool, McpTool) and scriptable(tool, True)]
    registry.register(script_tool(lambda: registry, scripted, let_run))
    return registry


@pytest.fixture
async def assembled(settings, store):
    """An agent as the server builds it from its profile. Its scripts may change things
    unless `script_calls` says not."""
    providers = {"scripted": ScriptedProvider([]), "fake": EchoProvider()}
    async with httpx.AsyncClient() as client:

        def build(script_calls: str = "gated", **profile: Any) -> AgentDeps:
            own = replace(settings, script_calls=script_calls)
            made = replace(default_profile(own), **profile)
            return build_agent_deps(made, providers, client, store)

        yield build


# --- which tools ---


def test_a_script_that_may_change_things_calls_what_writes_and_what_asks_first():
    reads = Reads("notes_read").tool
    writes = Reads("notes_write", replay_safe=False).tool
    guarded = Reads("pay_send", replay_safe=False, requires_approval=True).tool
    careful = Reads("rows_read", requires_approval=True).tool

    for tool in (reads, writes, guarded, careful):
        assert scriptable(tool, gated=True) and why_not(tool, gated=True) is None
    # Left as it was, an agent's scripts call the one that only reads and asks nobody.
    assert [scriptable(tool) for tool in (reads, writes, guarded, careful)] == [
        True,
        False,
        False,
        False,
    ]


def test_the_tools_that_always_wait_for_a_person_are_these_two():
    assert ALWAYS_ASKS == {"ask_user", "schedule_create"}


@pytest.mark.parametrize("name", sorted(ALWAYS_ASKS))
@pytest.mark.parametrize(
    "flags",
    [
        {"requires_approval": True},
        {"replay_safe": False},
        {"replay_safe": False, "requires_approval": True},
        {"ask_reason": lambda arguments: "luôn hỏi"},
    ],
)
def test_a_tool_that_always_waits_for_a_person_is_no_scripts_however_it_asks(name, flags):
    """A script waits for nobody, so the call would only ever end it. Told apart from a tool
    kept from every script: this one is the turn's to call, where a person can answer."""
    tool = Reads(name, **flags).tool

    assert not scriptable(tool, gated=True)
    assert why_not(tool, gated=True) == t.SCRIPT_ALWAYS_ASKS.format(
        name=name, instead=t.SCRIPT_CALL_DIRECTLY
    )
    # An agent left as it was is told what it was always told.
    assert why_not(tool) == t.SCRIPT_ASKS_FIRST.format(name=name, instead=t.SCRIPT_CALL_DIRECTLY)


@pytest.mark.parametrize("name", sorted(NOT_FROM_SCRIPT | RESERVED))
@pytest.mark.parametrize("flags", [{}, {"replay_safe": False}, {"requires_approval": True}])
def test_a_tool_kept_from_every_script_stays_out_though_the_script_may_change_things(name, flags):
    tool = Reads(name, **flags).tool

    assert not scriptable(tool, gated=True)
    # Not for what it changes, which is no reason here.
    assert why_not(tool, gated=True) == t.SCRIPT_NOT_FROM_SCRIPT.format(
        name=name, instead=t.SCRIPT_CALL_DIRECTLY
    )


@pytest.mark.parametrize(
    ("opened", "may"),
    [
        # Not listed under `read_only`, so it asks first: a script that may change things
        # calls it however far it is let in...
        ({}, True),
        ({"exposure": "deferred"}, True),
        ({"exposure": "direct"}, True),
        ({"tool_exposure": {"create-page": "codemode"}}, True),
        # ...but never one the owner hid.
        ({"tool_exposure": {"create-page": "hidden"}}, False),
        ({"exposure": "hidden"}, False),
        ({"read_only": ["create-page"], "exposure": "hidden"}, False),
    ],
)
def test_a_servers_tool_that_changes_things_is_such_a_scripts_unless_the_owner_hid_it(opened, may):
    [_, create] = notion(**opened)

    assert create.name == CREATE_NAME
    assert scriptable(create, gated=True) is may
    # Hidden and read-only apart, an agent left as it was calls it from no script.
    assert not scriptable(create) or opened.get("read_only")


def test_a_servers_tool_a_script_may_not_call_is_told_which_way_reaches_it():
    [_, waiting] = notion(tool_exposure={"create-page": "hidden"})

    assert why_not(waiting, gated=True) == t.SCRIPT_NOT_FROM_SCRIPT.format(
        name=CREATE_NAME, instead=t.SCRIPT_LOAD_THEN_CALL
    )


def test_what_a_script_may_call_is_in_the_order_held_with_the_tools_that_change_things_in_it():
    held = [
        Reads("rows_read").tool,
        Reads("notes_write", replay_safe=False).tool,
        Reads("ask_user", replay_safe=False, requires_approval=True).tool,
        Reads("progress_note").tool,
        *notion(tool_exposure={"search": "hidden"}),
        Reads("pay_send", replay_safe=False, requires_approval=True).tool,
        Reads("schedule_create", replay_safe=False, requires_approval=True).tool,
    ]
    registry = ToolRegistry(held)

    assert [tool.name for tool in callable_tools(registry, gated=True)] == [
        "rows_read",
        "notes_write",
        CREATE_NAME,
        "pay_send",
    ]
    assert [tool.name for tool in callable_tools(registry)] == ["rows_read"]


# --- what such a script finds when it looks ---


async def test_the_names_a_script_is_given_include_the_tools_that_change_things():
    held = [
        Reads("rows_read").tool,
        Reads("notes_write", replay_safe=False).tool,
        Reads("ask_user", replay_safe=False, requires_approval=True).tool,
        Reads("progress_note").tool,
        Reads("pay_send", replay_safe=False, requires_approval=True).tool,
    ]

    wider = await play(gated_toolbox(*held), "print(tools.names())")
    as_it_was = await play(toolbox(*held), "print(tools.names())")

    assert (wider.ok, wider.output) == (True, "['rows_read', 'notes_write', 'pay_send']")
    assert (as_it_was.ok, as_it_was.output) == (True, "['rows_read']")


async def test_a_search_of_such_a_script_finds_a_tool_that_changes_things():
    held = [
        reader("page_read", "Read a page."),
        reader("page_write", "Write a page of notes.", replay_safe=False),
    ]
    source = 'print([found["name"] for found in tools.search("write notes")])'

    wider = await play(gated_toolbox(*held), source)
    as_it_was = await play(toolbox(*held), source)

    assert (wider.ok, wider.output) == (True, "['page_write']")
    assert (as_it_was.ok, as_it_was.output) == (True, "[]")


async def test_such_a_script_is_told_how_a_tool_that_changes_things_is_called():
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    writes = reader("notes_write", "Keep a note.", schema, replay_safe=False)

    wider = await play(gated_toolbox(writes), 'print(tools.describe("notes_write"))')
    as_it_was = await play(toolbox(writes), 'tools.describe("notes_write")')

    assert wider.ok and wider.output.splitlines()[0] == "notes_write(text: string)"
    assert "Keep a note." in wider.output
    refused = t.SCRIPT_ASKS_FIRST.format(name="notes_write", instead=t.SCRIPT_CALL_DIRECTLY)
    assert (as_it_was.ok, as_it_was.output) == (False, unfinished(erred(1, refused)))


@pytest.mark.parametrize(
    ("name", "why"),
    [("ask_user", t.SCRIPT_ALWAYS_ASKS), ("progress_note", t.SCRIPT_NOT_FROM_SCRIPT)],
)
async def test_describe_says_why_a_tool_is_still_not_such_a_scripts_to_call(name, why):
    held = [
        Reads("ask_user", replay_safe=False, requires_approval=True).tool,
        Reads("progress_note").tool,
    ]

    result = await play(
        gated_toolbox(*held),
        f"""
        try:
            tools.describe("{name}")
        except Exception as e:
            print(e)
        """,
    )

    refused = why.format(name=name, instead=t.SCRIPT_CALL_DIRECTLY)
    assert (result.ok, result.output) == (True, refused)


async def test_a_name_near_a_tool_that_changes_things_is_offered_to_such_a_script_alone():
    writes = Reads("notes_write", "đã ghi", replay_safe=False)
    source = """
        try:
            tools.notes_writes()
        except Exception as e:
            print(e)
        """

    wider = await play(gated_toolbox(writes.tool), source)
    as_it_was = await play(toolbox(writes.tool), source)

    near = t.SCRIPT_DID_YOU_MEAN.format(near="notes_write")
    assert wider.output == t.SCRIPT_UNKNOWN_TOOL.format(name="notes_writes", near=near)
    assert as_it_was.output == t.SCRIPT_UNKNOWN_TOOL.format(name="notes_writes", near="")
    assert writes.asked == []


# --- what the model is told ---


def test_the_model_is_told_its_scripts_call_the_tools_that_change_things_too():
    held = [
        Reads("rows_read").tool,
        Reads("notes_write", replay_safe=False).tool,
        Reads("ask_user", replay_safe=False, requires_approval=True).tool,
        Reads("progress_note").tool,
        *notion(tool_exposure={"create-page": "codemode"}),
    ]

    told = gated_toolbox(*held).get(SCRIPT_TOOL).description

    assert told == t.SCRIPT_DESCRIPTION_GATED.format(
        calls=MAX_CALLS,
        batch=MAX_BATCH,
        example=t.SCRIPT_BATCH_EXAMPLE,
        builtins="\nCông cụ có sẵn gọi được từ script (tham số như khi gọi trực tiếp):\n"
        "- rows_read()\n- notes_write()",
        mcp="\nCông cụ MCP gọi được từ script (cần tham số chi tiết thì tra bằng tools.describe):\n"
        f"- {CREATE_NAME}(title?: string): [MCP notion] Make a page.\n"
        # The search asks first too and was not opened for scripts: counted, not named.
        "- … và 1 công cụ nữa, tìm bằng tools.search.",
    )
    assert "- ask_user" not in told and "- progress_note" not in told
    # What changes with the mode is said in so many words: the gate sees each such call,
    # the script waits for nobody, and a batch that writes runs in the order written.
    assert GATED_PART in told and READS_ONLY_PART not in told
    assert "Cổng duyệt xét từng lời gọi như vậy trước khi nó chạy" in told
    assert "Script không bao giờ chờ người dùng" in told
    assert "gọi công cụ đó trực tiếp, ngoài script, để người dùng được hỏi" in told
    assert "Lô có lời gọi ghi thì chạy lần lượt theo thứ tự đã viết." in told


def test_an_agent_left_as_it_was_is_told_what_it_was_always_told():
    held = [Reads("rows_read").tool, Reads("notes_write", replay_safe=False).tool]

    told = toolbox(*held).get(SCRIPT_TOOL).description

    assert READS_ONLY_PART in told and GATED_PART not in told
    assert "- rows_read()" in told and "notes_write" not in told
    # How a script is written is said the same way to both.
    wider = gated_toolbox(*held).get(SCRIPT_TOOL).description
    how = told[told.index("chỉ những gì script in ra") : told.index("\nCông cụ có sẵn")]
    assert how in wider


# --- who is handed such a script tool ---


@pytest.mark.parametrize(("mode", "more"), [(ASSISTANT, []), (WORK, ["workspace_edit"])])
async def test_a_built_agents_scripts_gain_the_tools_that_change_things_and_no_other(
    assembled, mode, more
):
    wider, as_it_was = assembled(mode=mode), assembled("read_only", mode=mode)

    assert wider.tools.names() == as_it_was.tools.names()
    assert wider.tools.names()[-1] == SCRIPT_TOOL
    may = [tool.name for tool in callable_tools(wider.tools, gated=True)]
    reads = [tool.name for tool in callable_tools(as_it_was.tools)]
    assert [name for name in may if name not in reads] == [*GAINED, *more]
    assert [name for name in wider.tools.names() if name not in may] == STILL_OUT
    # Each is named to the model with its parameters, in the order held.
    told = wider.tools.get(SCRIPT_TOOL).description
    lines = [line for line in told.splitlines() if line.startswith("- ")]
    assert lines == [f"- {call_line(wider.tools.get(name))}" for name in may]
    assert "- workspace_write(path: string, content: string)" in lines
    assert GATED_PART in told
    assert GATED_PART not in as_it_was.tools.get(SCRIPT_TOOL).description


async def test_a_script_tool_whose_scripts_may_change_things_is_never_run_again(assembled):
    """What a cut script had done is kept nowhere, so a restart closes it as cut
    (`test_tool_replay.py`). One that only reads is run again, as before."""
    wider, as_it_was = assembled(), assembled("read_only")

    assert not wider.tools.get(SCRIPT_TOOL).replay_safe
    assert as_it_was.tools.get(SCRIPT_TOOL).replay_safe
    for deps in (wider, as_it_was):
        tool = deps.tools.get(SCRIPT_TOOL)
        assert not tool.requires_approval and tool.ask_reason is None


@pytest.mark.parametrize(
    ("tools", "held"),
    [
        (("workspace_write",), True),
        (("memory_save", "shell_run"), True),
        # Nothing a script may call: a question, a note of the agent's, a schedule to agree to.
        (("ask_user",), False),
        (("progress_note",), False),
        (("schedule_create",), False),
        (("ask_user", "progress_note", "schedule_create"), False),
    ],
)
async def test_an_agent_holds_the_script_tool_while_it_holds_one_tool_its_scripts_may_call(
    assembled, tools, held
):
    deps = assembled(tools=tools)

    assert deps.tools.names() == [*tools, *([SCRIPT_TOOL] if held else [])]
    # Left as it was, none of these is an agent with a tool a script may call.
    assert assembled("read_only", tools=tools).tools.names() == list(tools)


async def test_a_servers_tool_that_changes_things_is_handed_to_such_a_script(deps_factory):
    opened = server(tool_exposure={"create-page": "codemode"})
    fake = FakeMcp()

    def gated():
        return deps_factory(script_calls="gated")

    deps, own, hub = await handed(gated, opened, fake=fake)
    as_it_was, _, _ = await handed(deps_factory, opened)

    assert deps.tools.names() == [*own, SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME]
    told = deps.tools.get(SCRIPT_TOOL).description
    assert f"- {CREATE_NAME}(title?: string): [MCP notion] Make a page." in told
    # The search was not listed under `read_only`: it asks first, and is counted with it.
    assert SEARCH_NAME not in told and "- … và 1 công cụ nữa, tìm bằng tools.search." in told
    assert CREATE_NAME not in as_it_was.tools.get(SCRIPT_TOOL).description
    # Handed out again, as a later change of a server does: once, and where it was.
    before = deps.tools.names()
    hub.attach({"default": deps})
    assert deps.tools.names() == before and deps.tools.get(SCRIPT_TOOL).description == told

    made = await ran(deps, conversation(deps), f'print(tools.{CREATE_NAME}(title="Kế hoạch"))')

    assert (made.ok, made.output) == (True, "ran create-page")
    assert fake.calls == [("create-page", {"title": "Kế hoạch"})]
    assert [(call.name, call.gated) for call in made.calls] == [(CREATE_NAME, True)]


async def test_a_servers_tool_a_person_would_be_asked_about_is_not_called_by_such_a_script(
    deps_factory,
):
    fake = FakeMcp()
    deps, _, _ = await handed(lambda: deps_factory(script_calls="gated"), server(), fake=fake)
    conv = conversation(deps, SUPERVISED)
    source = f'print(tools.{CREATE_NAME}(title="Kế hoạch"))'

    asked = await ran(deps, conv, source)

    reason = t.SCRIPT_GATE_ASKS.format(name=CREATE_NAME)
    assert (asked.ok, asked.output) == (False, unfinished(halted(1, reason)))
    assert fake.calls == [] and asked.calls == ()
    # A tool the person said to always allow in this conversation is theirs to let by.
    always = deps.store.update(conv.id, auto_approve=[CREATE_NAME])
    allowed = await ran(deps, always, source)
    assert (allowed.ok, allowed.output) == (True, "ran create-page")
    assert fake.calls == [("create-page", {"title": "Kế hoạch"})]


# --- an agent as the server builds it ---


async def test_a_script_of_a_built_agent_writes_a_file_and_runs_a_command(assembled):
    deps = assembled()
    noted = deps.agent.workspace / "ghi.txt"

    result = await ran(
        deps,
        conversation(deps),
        """
        print(tools.workspace_write(path="ghi.txt", content="một\\nhai\\n"))
        print(tools.shell_run(command="wc -l < ghi.txt").strip())
        print(tools.workspace_read(path="ghi.txt").split())
        """,
    )

    assert (result.ok, result.output) == (True, "Đã ghi 8 ký tự vào ghi.txt\n2\n['một', 'hai']")
    assert noted.read_text(encoding="utf-8") == "một\nhai\n"
    # Marked on the run card: the two that went by the gate, and not the read.
    assert [(call.name, call.gated) for call in result.calls] == [
        ("workspace_write", True),
        ("shell_run", True),
        ("workspace_read", False),
    ]


async def test_a_script_of_a_built_agent_changes_nothing_a_person_would_be_asked_about(assembled):
    deps = assembled()
    noted = deps.agent.workspace / "ghi.txt"
    noted.write_text("cũ\n", encoding="utf-8")
    conv = conversation(deps, SUPERVISED)

    result = await ran(
        deps,
        conv,
        """
        print(tools.workspace_read(path="ghi.txt").strip())
        tools.workspace_write(path="ghi.txt", content="mới")
        tools.shell_run(command="rm ghi.txt")
        """,
    )

    reason = t.SCRIPT_GATE_ASKS.format(name="workspace_write")
    assert (result.ok, result.output) == (False, unfinished("cũ", halted(3, reason)))
    assert noted.read_text(encoding="utf-8") == "cũ\n"
    assert [call.name for call in result.calls] == ["workspace_read"]
    # Nobody was asked: the turn is the one to ask, when the model makes the call directly.
    assert deps.store.approvals.pending(conv.id) is None


async def test_a_script_of_a_built_agent_left_as_it_was_writes_nothing(assembled):
    deps = assembled("read_only")

    result = await ran(
        deps, conversation(deps), 'tools.workspace_write(path="ghi.txt", content="mới")'
    )

    reason = t.SCRIPT_ASKS_FIRST.format(name="workspace_write", instead=t.SCRIPT_CALL_DIRECTLY)
    assert (result.ok, result.output) == (False, unfinished(halted(1, reason)))
    assert not (deps.agent.workspace / "ghi.txt").exists()
