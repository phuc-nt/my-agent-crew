"""`tool_script` as an agent holds it: which tools a script may call and what it is told
when it may not, what is kept of each call for the run card, what comes back to the model,
how the tool is described, and what a hand-out of its servers' tools does to it
(`script/tool.py`, `mcp/handout.py`). Who is built with it is in `test_script_handout.py`.
Every script here runs in a real child process."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from textwrap import dedent
from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.mcp.tools import PREFIX, CompanionTool, McpTool, build_tools
from my_agent_crew.script import tool as script_module
from my_agent_crew.script.limits import MAX_BATCH, RAW_LIMIT
from my_agent_crew.script.runner import Outcome
from my_agent_crew.script.scope import NOT_FROM_SCRIPT, SCRIPT_TOOL, scriptable, unknown_tool
from my_agent_crew.script.signature import JSON_TYPES, signature
from my_agent_crew.script.tool import ScriptTool, script_tool
from my_agent_crew.texts import TOOL_ARGUMENTS_LEFT_OUT, TOOL_FAILED
from my_agent_crew.texts_kit import TOOL_BLOCKED_BY_HOOK
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from my_agent_crew.tools.registry import MAX_OUTPUT_CHARS, Tool, ToolError, ToolRegistry
from my_agent_crew.tools.result import NestedCall, ToolResult
from tests.mcp_fakes import TOOLS, FakeMcp, make_hub, server
from tests.test_mcp_tool_search import CREATE_NAME, SEARCH_NAME, built, handed

SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
OPENED = {"read_only": ["search"], "tool_exposure": {"search": "codemode"}}
EVERY_NAME = "rows_read, notes_write, guarded_read, always_asks, progress_note"


class Reads:
    """A tool that only reads, unless its flags say otherwise: it answers with what it was
    built with, or raises it, and keeps what it was asked."""

    def __init__(self, name: str, answer: Any = "đã đọc", **flags: Any):
        self.asked: list[dict[str, Any]] = []
        self.answer = answer
        flags.setdefault("replay_safe", True)
        self.tool = Tool(name, f"Đọc {name}.", SCHEMA, self._run, **flags)

    async def _run(self, arguments: dict[str, Any]) -> Any:
        self.asked.append(arguments)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class Hooks:
    """An agent's hooks: they refuse the tools in `blocked`, leave a note after the ones
    in `noted`, and keep what they were asked."""

    def __init__(self, blocked: tuple[str, ...] = (), noted: tuple[str, ...] = ()):
        self.blocked, self.noted = blocked, noted
        self.asked: list[tuple[str, str]] = []
        self.arguments: dict[str, dict[str, Any]] = {}

    async def before(self, name: str, arguments: dict[str, Any]) -> str | None:
        self.asked.append(("before", name))
        self.arguments[name] = arguments
        return "không phải lúc" if name in self.blocked else None

    async def after(self, name: str, arguments: dict[str, Any], ok: bool, output: str) -> str:
        self.asked.append(("after", name))
        return " [đã ghi sổ]" if name in self.noted else ""


def notion(calls: list | None = None, listed=TOOLS, **settings) -> list[McpTool]:
    """A server's tools, answering in process and adding each call to `calls`."""

    async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert calls is not None, "this script calls no server"
        calls.append((name, arguments))
        return {"content": [{"type": "text", "text": f"ran {name}"}]}

    tools, _ = build_tools(server(**settings), listed, call)
    return list(tools)


def toolbox(*tools: Tool, hooks: Any = None, limit: int = MAX_OUTPUT_CHARS) -> ToolRegistry:
    """An agent's tools with the script tool over them, the way a hand-out leaves them."""
    registry = ToolRegistry(list(tools), limit, hooks)
    scripted = [tool for tool in tools if isinstance(tool, McpTool) and scriptable(tool)]
    registry.register(script_tool(lambda: registry, scripted))
    return registry


async def play(registry: ToolRegistry, source: str) -> ToolResult:
    return await registry.execute(SCRIPT_TOOL, {"script": dedent(source)})


async def never_run(source, call, **limits):
    raise AssertionError("no script was to be started")


def halted(line: int, reason: str) -> str:
    return t.SCRIPT_HALTED.format(line=line, reason=reason)


def erred(line: int, error: str) -> str:
    return t.SCRIPT_ERROR.format(line=line, error=error)


def unfinished(*said: str) -> str:
    """The answer of a script that did not run to its end: that it did not, then `said`."""
    return "\n".join((t.SCRIPT_FAILED, *said))


def test_a_script_may_call_a_tool_that_only_reads_and_asks_nobody():
    assert scriptable(Reads("notes_read").tool)
    assert not scriptable(Reads("notes_write", replay_safe=False).tool)
    assert not scriptable(Reads("notes_read", requires_approval=True).tool)
    # A tool with a rule of its own about asking is never a script's, whatever the rule
    # would say of one call.
    assert not scriptable(Reads("notes_read", ask_reason=lambda arguments: "").tool)


KEPT_FROM_SCRIPTS = ["progress_note", "delegate", "tool_search", "tool_script", "artifact_read"]


@pytest.mark.parametrize("name", KEPT_FROM_SCRIPTS)
def test_a_tool_that_speaks_for_the_agent_is_not_a_scripts_though_it_only_reads(name):
    assert not scriptable(Reads(name).tool)


def test_the_tools_kept_from_scripts_are_these_five():
    assert set(KEPT_FROM_SCRIPTS) == NOT_FROM_SCRIPT


@pytest.mark.parametrize(
    ("opened", "may"),
    [
        (OPENED, [SEARCH_NAME]),
        ({"read_only": ["search"], "exposure": "codemode"}, [SEARCH_NAME]),
        (
            {"read_only": ["search", "create-page"], "exposure": "codemode"},
            [SEARCH_NAME, CREATE_NAME],
        ),
        # The owner saying it reads is what lets a script call it; how far it is let in only
        # decides whether the script is told of it up front or finds it.
        ({"read_only": ["search"]}, [SEARCH_NAME]),
        ({"read_only": ["search"], "exposure": "deferred"}, [SEARCH_NAME]),
        ({"read_only": ["search"], "exposure": "direct"}, [SEARCH_NAME]),
        ({"read_only": ["search"], "tool_exposure": {"search": "direct"}}, [SEARCH_NAME]),
        ({"read_only": ["search", "create-page"]}, [SEARCH_NAME, CREATE_NAME]),
        # A hidden tool is no agent's, so no script's.
        ({"read_only": ["search"], "tool_exposure": {"search": "hidden"}}, []),
        ({"read_only": ["search"], "exposure": "hidden"}, []),
        # Only the server says it reads, or the owner opened it without saying so: that
        # decides nothing.
        ({"exposure": "codemode"}, []),
        ({"exposure": "direct"}, []),
        ({}, []),
        ({"tool_exposure": {"search": "codemode"}}, []),
    ],
)
def test_a_servers_tool_is_a_scripts_when_the_owner_says_it_reads_and_does_not_hide_it(opened, may):
    assert [tool.name for tool in built(**opened) if scriptable(tool)] == may


async def test_a_script_makes_the_calls_and_only_what_it_prints_comes_back():
    rows = Reads("rows_read", json.dumps({"rows": [3, 4, 5]}))

    result = await play(
        toolbox(rows.tool),
        """
        total = 0
        for page in range(2):
            total += sum(json.loads(tools.rows_read(page=page))["rows"])
        print("tổng", total)
        """,
    )

    assert (result.ok, result.output) == (True, "tổng 24")
    assert rows.asked == [{"page": 0}, {"page": 1}]
    # The script paid nothing itself: what its calls cost is charged call by call.
    assert (result.cost_usd, result.metered, result.reply) == (None, False, None)


async def test_a_script_calls_a_servers_tool_by_the_name_the_agent_holds_it_under():
    calls: list = []

    result = await play(
        toolbox(*notion(calls, **OPENED)),
        f"""
        print(tools.{SEARCH_NAME}(query="kế hoạch"))
        print(tools.{SEARCH_NAME}({{"query": "báo cáo"}}))
        """,
    )

    assert (result.ok, result.output) == (True, "ran search\nran search")
    assert calls == [("search", {"query": "kế hoạch"}), ("search", {"query": "báo cáo"})]


async def test_each_call_a_script_made_is_kept_for_the_run_card():
    async def slowly(arguments: dict[str, Any]) -> str:
        await asyncio.sleep(0.3)
        return "dòng\n" * 100

    rows = Tool("rows_read", "Đọc dòng.", SCHEMA, slowly, replay_safe=True)
    gone = Reads("gone_read", ToolError("không có trang"))

    result = await play(
        toolbox(rows, gone.tool),
        """
        tools.rows_read(query="a" * 300, page=2, tags=["x", "y"])
        try:
            tools.gone_read()
        except Exception as e:
            print("lỗi:", e)
        """,
    )

    failed = TOOL_FAILED.format(error="không có trang")
    assert (result.ok, result.output) == (True, f"lỗi: {failed}")
    first, second = result.calls
    # What was asked and what came back are previews, as a step of the timeline keeps them.
    assert first == NestedCall(
        name="rows_read",
        arguments={"query": "a" * 160 + "…", "page": 2, "tags": '["x", "y"]'},
        ok=True,
        output=("dòng " * 100)[:160] + "…",
        ms=first.ms,
    )
    assert 290 <= first.ms < 2900
    assert second == NestedCall("gone_read", {}, False, failed, second.ms)
    assert 0 <= second.ms < 290


async def test_a_call_given_a_wide_mapping_is_kept_by_its_first_dozen_arguments():
    rows = Reads("rows_read")

    result = await play(
        toolbox(rows.tool),
        """
        wide = {}
        for n in range(300):
            wide[f"field_{n}"] = "x" * 200
        tools.batch([{"tool": "rows_read", "args": wide}])
        print(len(wide))
        """,
    )

    assert (result.ok, result.output) == (True, "300")
    # The tool is handed every argument: only what is kept of the call is held down.
    assert len(rows.asked[0]) == 300
    (call,) = result.calls
    left_out = TOOL_ARGUMENTS_LEFT_OUT.format(count=288)
    assert call.arguments == {
        **{f"field_{n}": "x" * 160 + "…" for n in range(12)},
        "…": left_out,
    }


async def test_a_script_reports_what_its_calls_handed_it_and_what_it_printed():
    rows = Reads("rows_read", "dòng\n" * 100)
    note = Reads("note_read", "ghi chú")

    result = await play(
        toolbox(rows.tool, note.tool),
        """
        text = tools.rows_read()
        short = tools.note_read()
        print(len(text.split()), short)
        """,
    )

    assert result.output == "100 ghi chú"
    # 500 characters of rows and 7 of the note went in; 11 came out.
    assert (result.received_chars, result.printed_chars) == (507, 11)


async def test_a_script_that_calls_nothing_received_nothing():
    result = await play(toolbox(Reads("rows_read").tool), 'print("không gọi gì")')

    assert (result.received_chars, result.printed_chars) == (0, 12)


async def test_a_call_that_failed_counts_as_what_the_script_was_handed():
    gone = Reads("gone_read", ToolError("không có trang"))
    failed = TOOL_FAILED.format(error="không có trang")

    result = await play(
        toolbox(gone.tool),
        """
        try:
            tools.gone_read()
        except Exception as e:
            print("lỗi")
        """,
    )

    assert result.ok and result.output == "lỗi"
    assert (result.received_chars, result.printed_chars) == (len(failed), 3)


async def test_a_name_that_is_no_tool_hands_the_script_no_answer_to_count():
    result = await play(
        toolbox(Reads("rows_read").tool),
        """
        try:
            tools.rows_raed()
        except Exception as e:
            print("sai tên")
        """,
    )

    assert result.ok and result.output == "sai tên" and result.calls == ()
    assert (result.received_chars, result.printed_chars) == (0, 7)


async def test_a_script_that_failed_printed_only_what_it_printed_before_it_did():
    rows = Reads("rows_read", "mười chữ.")

    result = await play(
        toolbox(rows.tool),
        """
        print("trước", len(tools.rows_read()))
        tools.rows_raed()
        """,
    )

    assert not result.ok and result.output.startswith(f"{t.SCRIPT_FAILED}\ntrước 9\n")
    # The report of the failure is not something the script printed, nor is the line's end.
    assert (result.received_chars, result.printed_chars) == (9, 7)


async def test_a_call_that_paid_a_model_carries_its_price_and_a_free_one_carries_none():
    priced = Reads("priced_read", ToolResult(ok=True, output="một", cost_usd=0.004, metered=True))
    unpriced = Reads("unpriced_read", ToolResult(ok=True, output="hai", metered=True))
    free = Reads("free_read", ToolResult(ok=True, output="ba", cost_usd=0.5))

    result = await play(
        toolbox(priced.tool, unpriced.tool, free.tool),
        "print(tools.priced_read(), tools.unpriced_read(), tools.free_read())",
    )

    assert result.output == "một hai ba"
    assert [(call.name, call.cost_usd, call.metered) for call in result.calls] == [
        ("priced_read", 0.004, True),
        ("unpriced_read", None, True),
        ("free_read", None, False),
    ]


async def test_two_scripts_at_once_each_keep_their_own_calls():
    rows, notes = Reads("rows_read", "dòng"), Reads("notes_read", "ghi chú")
    registry = toolbox(rows.tool, notes.tool)

    first, second = await asyncio.gather(
        play(registry, "print(tools.rows_read(), tools.rows_read())"),
        play(registry, "print(tools.notes_read())"),
    )

    assert (first.output, second.output) == ("dòng dòng", "ghi chú")
    assert [call.name for call in first.calls] == ["rows_read", "rows_read"]
    assert [call.name for call in second.calls] == ["notes_read"]


async def test_a_script_that_calls_too_often_is_stopped_before_the_call_too_many():
    rows = Reads("rows_read", "dòng")

    result = await play(
        toolbox(rows.tool),
        """
        for page in range(40):
            tools.rows_read(page=page)
            print(page)
        """,
    )

    printed = "\n".join(str(page) for page in range(25))
    reason = "Script đã dùng quá 25 lời gọi. Gộp việc lại hoặc chia nhiều script."
    assert (result.ok, result.output) == (False, unfinished(printed, halted(3, reason)))
    assert rows.asked == [{"page": page} for page in range(25)]
    assert len(result.calls) == 25


REFUSED = [
    ("tools.notes_write(text='x')", "notes_write", t.SCRIPT_ASKS_FIRST, "gọi trực tiếp", {}),
    ("tools.guarded_read()", "guarded_read", t.SCRIPT_ASKS_FIRST, "gọi trực tiếp", {}),
    ("tools.always_asks()", "always_asks", t.SCRIPT_ASKS_FIRST, "gọi trực tiếp", {}),
    (
        "tools.progress_note(text='x')",
        "progress_note",
        t.SCRIPT_NOT_FROM_SCRIPT,
        "gọi trực tiếp",
        {},
    ),
    ("tools.tool_script(script='1')", "tool_script", t.SCRIPT_NOT_FROM_SCRIPT, "gọi trực tiếp", {}),
    # A server's tool waits to be found unless it is let in directly, and the script is
    # told which of the two ways reaches it.
    (
        f"tools.{CREATE_NAME}(title='x')",
        CREATE_NAME,
        t.SCRIPT_ASKS_FIRST,
        "nạp bằng tool_search rồi gọi trực tiếp",
        {},
    ),
    (
        f"tools.{CREATE_NAME}(title='x')",
        CREATE_NAME,
        t.SCRIPT_ASKS_FIRST,
        "gọi trực tiếp",
        {"tool_exposure": {"create-page": "direct"}},
    ),
    (
        f"tools.{CREATE_NAME}(title='x')",
        CREATE_NAME,
        t.SCRIPT_ASKS_FIRST,
        "nạp bằng tool_search rồi gọi trực tiếp",
        {"tool_exposure": {"create-page": "codemode"}},
    ),
    # Opening a tool does not make it a read: only the owner's `read_only` does.
    (
        f"tools.{SEARCH_NAME}(query='x')",
        SEARCH_NAME,
        t.SCRIPT_ASKS_FIRST,
        "gọi trực tiếp",
        {"tool_exposure": {"search": "direct"}},
    ),
    (
        f"tools.{SEARCH_NAME}(query='x')",
        SEARCH_NAME,
        t.SCRIPT_ASKS_FIRST,
        "nạp bằng tool_search rồi gọi trực tiếp",
        {"tool_exposure": {"search": "codemode"}},
    ),
]


@pytest.mark.parametrize(("call", "name", "why", "instead", "opened"), REFUSED)
async def test_a_call_a_script_may_not_make_ends_it_and_says_how_to_make_it(
    call, name, why, instead, opened
):
    reached: list = []
    held = [
        Reads("rows_read"),
        Reads("notes_write", replay_safe=False),
        Reads("guarded_read", requires_approval=True),
        Reads("always_asks", ask_reason=lambda arguments: "luôn hỏi"),
        Reads("progress_note"),
    ]
    registry = toolbox(*(one.tool for one in held), *notion(reached, **opened))

    result = await play(
        registry,
        f"""
        print("trước")
        try:
            {call}
        except Exception as e:
            print("bắt được")
        print("sau")
        """,
    )

    # Not a failure the script can catch and carry on from: it ends where it asked.
    reason = why.format(name=name, instead=instead)
    assert (result.ok, result.output) == (False, unfinished("trước", halted(4, reason)))
    assert name in reason and reason.endswith(f": {instead}.")
    assert [one.asked for one in held] == [[]] * 5 and reached == []
    assert result.calls == ()


@pytest.mark.parametrize(
    "opened",
    [
        OPENED,
        {"read_only": ["search"]},
        {"read_only": ["search"], "exposure": "deferred"},
        {"read_only": ["search"], "exposure": "direct"},
        {"read_only": ["search"], "tool_exposure": {"search": "direct"}},
    ],
)
async def test_a_tool_the_owner_says_reads_is_run_from_a_script_whatever_its_exposure(opened):
    calls: list = []

    result = await play(
        toolbox(*notion(calls, **opened)), f"print(tools.{SEARCH_NAME}(query='kế hoạch'))"
    )

    assert (result.ok, result.output) == (True, "ran search")
    assert calls == [("search", {"query": "kế hoạch"})]
    assert [(call.name, call.ok) for call in result.calls] == [(SEARCH_NAME, True)]


async def test_a_tool_left_out_of_the_listing_for_scripts_is_a_scripts_to_call_all_the_same():
    """Being listed in the description is a convenience for the model, not a gate: a name it
    learned from `tool_search` is as good as a listed one."""
    calls: list = []
    registry = toolbox(*notion(calls, read_only=["search"]))

    result = await play(registry, f"print(tools.{SEARCH_NAME}(query='x'))")

    assert (result.ok, result.output) == (True, "ran search")
    assert SEARCH_NAME not in registry.get(SCRIPT_TOOL).description


@pytest.mark.parametrize(
    "opened",
    [
        {"read_only": ["search"], "tool_exposure": {"search": "hidden"}},
        {"read_only": ["search"], "exposure": "hidden"},
    ],
)
async def test_a_hidden_tool_is_not_run_from_a_script_even_when_one_holds_it(opened):
    """No agent is handed a hidden tool, so the script tool never meets one outside a test;
    were one registered it would still be refused, not run."""
    reached: list = []
    registry = toolbox(*notion(reached, **opened), Reads("rows_read").tool)

    result = await play(
        registry,
        f"""
        print("trước")
        try:
            tools.{SEARCH_NAME}(query='x')
        except Exception as e:
            print("bắt được")
        print("sau")
        """,
    )

    assert not result.ok and result.output.startswith(t.SCRIPT_FAILED)
    assert result.output.splitlines()[1] == "trước" and SEARCH_NAME in result.output
    assert "bắt được" not in result.output and "sau" not in result.output
    assert reached == [] and result.calls == ()


async def test_a_tool_the_agent_does_not_hold_fails_the_call_and_says_where_to_look():
    held = [
        Reads("rows_read").tool,
        Reads("notes_write", replay_safe=False).tool,
        Reads("progress_note").tool,
        Reads("notes_read").tool,
        *notion(**OPENED),
    ]

    result = await play(toolbox(*held), "tools.nope()")

    reason = t.SCRIPT_UNKNOWN_TOOL.format(name="nope", near="")
    assert (result.ok, result.output, result.calls) == (False, unfinished(erred(1, reason)), ())
    assert "tools.names()" in reason and "tools.search(" in reason


async def test_a_script_told_the_nearest_name_may_catch_the_mistake_and_call_again():
    rows = Reads("rows_read", "ba dòng")
    held = [rows.tool, Reads("notes_read").tool, Reads("progress_note").tool]

    result = await play(
        toolbox(*held),
        """
        try:
            tools.row_read()
        except Exception as e:
            print(e)
        print(tools.rows_read())
        """,
    )

    near = t.SCRIPT_DID_YOU_MEAN.format(near="rows_read")
    mistake = t.SCRIPT_UNKNOWN_TOOL.format(name="row_read", near=near)
    assert (result.ok, result.output) == (True, f"{mistake}\nba dòng")
    assert "Ý bạn là `rows_read`?" in mistake
    # The slip made no call; the one that followed did.
    assert [call.name for call in result.calls] == ["rows_read"] and rows.asked == [{}]


async def test_a_name_near_only_to_a_tool_a_script_may_not_call_is_not_offered():
    held = [Reads("notes_write", replay_safe=False).tool, Reads("rows_read").tool]

    result = await play(toolbox(*held), "tools.notes_writes()")

    assert result.output == unfinished(
        erred(1, t.SCRIPT_UNKNOWN_TOOL.format(name="notes_writes", near=""))
    )


async def test_the_agents_hooks_are_asked_about_each_call_a_script_makes():
    rows, secret = Reads("rows_read", "ba dòng"), Reads("secret_read")
    hooks = Hooks(blocked=("secret_read",), noted=("rows_read",))

    result = await play(
        toolbox(rows.tool, secret.tool, hooks=hooks),
        """
        try:
            tools.secret_read(path="két")
        except Exception as e:
            print("bị chặn:", e)
        print(tools.rows_read())
        """,
    )

    blocked = TOOL_BLOCKED_BY_HOOK.format(name="secret_read", reason="không phải lúc")
    assert (result.ok, result.output) == (True, f"bị chặn: {blocked}\nba dòng [đã ghi sổ]")
    assert secret.asked == [] and rows.asked == [{}]
    assert hooks.asked == [
        ("before", SCRIPT_TOOL),
        ("before", "secret_read"),
        ("before", "rows_read"),
        ("after", "rows_read"),
        ("after", SCRIPT_TOOL),
    ]
    assert hooks.arguments["secret_read"] == {"path": "két"}
    assert [(call.name, call.ok, call.output) for call in result.calls] == [
        ("secret_read", False, blocked),
        ("rows_read", True, "ba dòng [đã ghi sổ]"),
    ]


async def test_a_call_a_script_may_not_make_is_answered_as_one_that_went_wrong(monkeypatch):
    """The process a script runs in ends at `halt`. One that knew only `ok` would still not
    hand the refusal to the script as what the tool said."""
    answers = []

    async def asking(source, call, **limits):
        answers.extend([await call("notes_write", {}), await call("nowhere", {})])
        return Outcome(True, "")

    monkeypatch.setattr(script_module, "run_script", asking)
    writes = Reads("notes_write", replay_safe=False)

    await play(toolbox(writes.tool), "pass")

    # A tool that exists and may not be called ends the script; a name that is no tool's is
    # an error it can catch.
    assert [(answer.ok, answer.halt) for answer in answers] == [(False, True), (False, False)]
    assert writes.asked == []


async def test_a_script_calls_the_tools_the_agent_holds_when_it_runs():
    old, new = Reads("old_read", "cũ"), Reads("new_read", "mới")
    held = {"now": ToolRegistry([old.tool])}
    registry = ToolRegistry([script_tool(lambda: held["now"], [])])
    held["now"] = ToolRegistry([new.tool])

    result = await registry.execute(SCRIPT_TOOL, {"script": "print(tools.new_read())"})
    gone = await registry.execute(SCRIPT_TOOL, {"script": "tools.old_read()"})

    assert (result.ok, result.output) == (True, "mới")
    assert (gone.ok, gone.output) == (
        False,
        unfinished(erred(1, unknown_tool("old_read", [new.tool]))),
    )
    assert old.asked == []


async def test_a_script_is_handed_far_more_of_an_answer_than_a_turn_is():
    big = Reads("big_read", "x" * 150_000)
    registry = toolbox(big.tool)

    direct = await registry.execute("big_read", {})
    result = await play(registry, "print(len(tools.big_read()))")

    assert direct.shaped_kind == "cut" and len(direct.output) <= 8000
    assert result.output == "150000"
    # The run card keeps a preview of it, like of any other call.
    assert result.calls[0].output == "x" * 160 + "…"


async def test_an_answer_past_what_a_script_is_handed_is_cut_for_it_too():
    big = Reads("big_read", "x" * 250_000)

    result = await play(
        toolbox(big.tool),
        """
        text = tools.big_read()
        print(len(text), text.count("x") < len(text))
        """,
    )

    size, noted = result.output.split()
    assert RAW_LIMIT == 200_000 and RAW_LIMIT - 10 <= int(size) <= RAW_LIMIT
    assert noted == "True"


async def test_what_a_script_prints_is_cut_to_the_agents_cap_with_its_calls_kept():
    rows = Reads("rows_read", "một dòng")

    result = await play(
        toolbox(rows.tool, limit=1000),
        """
        tools.rows_read()
        print("y" * 5000)
        """,
    )

    assert result.ok and len(result.output) <= 1000
    assert (result.shaped_kind, result.original_chars) == ("cut", 5000)
    assert [call.name for call in result.calls] == ["rows_read"]
    # The measure is what the script printed, not the part of it the cap let through.
    assert result.printed_chars == 5000


@pytest.mark.parametrize(
    "arguments",
    [{}, {"script": ""}, {"script": " \n\t"}, {"script": 5}, {"script": None}, {"code": "1"}],
)
async def test_a_call_without_a_script_starts_nothing(monkeypatch, arguments):
    monkeypatch.setattr(script_module, "run_script", never_run)

    result = await toolbox().execute(SCRIPT_TOOL, arguments)

    wanted = TOOL_FAILED.format(error="Thiếu `script`: mã Python cần chạy.")
    assert (result.ok, result.output, result.calls) == (False, wanted, ())


async def test_a_script_as_long_as_the_most_is_run_and_one_letter_longer_is_not(monkeypatch):
    most = "print(1)\n" + "#" * 19_991
    assert len(most) == 20_000
    registry = toolbox()

    ran = await registry.execute(SCRIPT_TOOL, {"script": most})
    monkeypatch.setattr(script_module, "run_script", never_run)
    refused = await registry.execute(SCRIPT_TOOL, {"script": most + "#"})

    assert (ran.ok, ran.output) == (True, "1")
    wanted = TOOL_FAILED.format(error="Script dài quá 20000 ký tự. Viết gọn lại.")
    assert (refused.ok, refused.output) == (False, wanted)


@pytest.mark.parametrize(
    ("source", "ok", "output"),
    [
        ("x = 1", True, "(script chạy xong, không in ra gì: dùng print để lấy kết quả)"),
        ("print()\nprint('  ')", True, t.SCRIPT_NO_OUTPUT),
        # The end of what was printed is trimmed, the start is the script's own.
        ("print('  thụt vào')\nprint()\nprint()", True, "  thụt vào"),
        ("1 + 2", True, "3"),
        # One that did not run to its end says so first, whatever ended it.
        ("print('trước')\nnope", False, unfinished("trước", "Lỗi ở dòng 2: chưa có tên `nope`.")),
        (
            "print('trước')\nprint()\nnope",
            False,
            unfinished("trước", "Lỗi ở dòng 3: chưa có tên `nope`."),
        ),
        ("nope", False, unfinished("Lỗi ở dòng 1: chưa có tên `nope`.")),
        ("import os", False, unfinished("Dòng 1: `import os` không dùng được trong script.")),
        ("x = = 1", False, unfinished("Lỗi cú pháp ở dòng 1: invalid syntax")),
        # Saying the same words does not make a script that ran to its end one that did not.
        ("print('Script không chạy xong.')", True, "Script không chạy xong."),
    ],
)
async def test_what_comes_back_is_what_was_printed_and_then_why_it_ended(source, ok, output):
    result = await toolbox().execute(SCRIPT_TOOL, {"script": source})

    assert (result.ok, result.output) == (ok, output)


@pytest.mark.parametrize(
    "ended",
    [
        Outcome(False, "", t.SCRIPT_DIED),
        Outcome(False, "", t.SCRIPT_OUT_OF_CPU),
        Outcome(False, "", t.SCRIPT_TIMED_OUT.format(seconds=60)),
        # What a tool answered a failed call with may run over many lines, and so may what
        # the script had printed: the line that says it failed is still the first one.
        Outcome(False, "một\nhai\n", "Lỗi ở dòng 3: không đọc được\nthử lại sau"),
        Outcome(False, "", ""),
    ],
    ids=["died", "out of cpu", "timed out", "failed over many lines", "no reason given"],
)
async def test_a_script_that_did_not_run_to_its_end_says_so_before_anything_else(
    monkeypatch, ended
):
    """The web reads a stored answer by how it opens, and a script prints what it likes: only
    this line tells the two kinds of answer apart once the turn is over."""

    async def ends(source, call, **limits):
        return ended

    monkeypatch.setattr(script_module, "run_script", ends)

    result = await toolbox().execute(SCRIPT_TOOL, {"script": "x = 1"})

    rest = [part for part in (ended.output.rstrip(), ended.error) if part]
    assert (result.ok, result.output) == (False, unfinished(*rest))


def test_the_script_tool_asks_nobody_and_may_be_run_again():
    tool = toolbox().get(SCRIPT_TOOL)

    assert isinstance(tool, ScriptTool) and tool.name == "tool_script"
    # It follows what the agent may read, not its allow-list and not its servers: it says so
    # to the owner's screens, apart from the search that comes with a server.
    assert not isinstance(tool, CompanionTool)
    assert tool.to_dict() == {
        "name": "tool_script",
        "description": tool.description,
        "requires_approval": False,
        "with_reads": True,
    }
    assert tool.replay_safe and tool.ask_reason is None and not tool.parallel
    assert tool.parameters == {
        "type": "object",
        "properties": {"script": {"type": "string", "description": t.SCRIPT_SOURCE}},
        "required": ["script"],
    }
    assert not scriptable(tool)


def test_the_model_is_told_which_tools_a_script_can_call():
    held = [
        Reads("rows_read").tool,
        Reads("notes_write", replay_safe=False).tool,
        Reads("progress_note").tool,
        Reads("notes_read").tool,
        *built(**OPENED),
    ]

    told = toolbox(*held).get(SCRIPT_TOOL).description

    assert told == t.SCRIPT_DESCRIPTION.format(
        calls=25,
        batch=MAX_BATCH,
        example=t.SCRIPT_BATCH_EXAMPLE,
        builtins="\nCông cụ có sẵn gọi được từ script (tham số như khi gọi trực tiếp):\n"
        "- rows_read()\n- notes_read()",
        mcp="\nCông cụ MCP gọi được từ script (cần tham số chi tiết thì tra bằng tools.describe):\n"
        f"- {SEARCH_NAME}(query: string): [MCP notion] Find pages by words.",
    )
    assert "Mỗi script được tối đa 25 lời gọi." in told
    # How to ask for several calls at once, how many, and a script that does it.
    assert "tools.batch(" in told and f"tối đa {MAX_BATCH} lời gọi" in told
    assert t.SCRIPT_BATCH_EXAMPLE in told
    # What a batch does not change: one call that failed spoils none of the others, and each
    # call still counts among the most a script may make.
    assert "một lời gọi lỗi không làm hỏng các lời gọi còn lại." in told
    assert "Mỗi lời gọi trong lô vẫn tính vào 25 lời gọi đó." in told
    # A tool is named once, where it belongs; one a script may not call is not named.
    assert told.count(SEARCH_NAME) == 1 and CREATE_NAME not in told
    assert "notes_write" not in told and "progress_note" not in told


def test_a_part_with_nothing_to_list_is_left_out_of_what_the_model_is_told():
    nothing = toolbox().get(SCRIPT_TOOL).description
    own = toolbox(Reads("rows_read").tool).get(SCRIPT_TOOL).description
    served = toolbox(*built(**OPENED)).get(SCRIPT_TOOL).description

    assert nothing == t.SCRIPT_DESCRIPTION.format(
        calls=25, batch=MAX_BATCH, example=t.SCRIPT_BATCH_EXAMPLE, builtins="", mcp=""
    )
    assert "Công cụ có sẵn" not in nothing and "Công cụ MCP" not in nothing
    head = "\nCông cụ có sẵn gọi được từ script (tham số như khi gọi trực tiếp):\n- rows_read()\n"
    assert head in own and "Công cụ MCP" not in own
    assert "Công cụ có sẵn" not in served and f"- {SEARCH_NAME}(" in served


def one(schema: Any, description: str = "Does it.") -> str:
    [tool] = built([{"name": "act", "description": description, "inputSchema": schema}])
    return signature(tool)


def test_a_tool_is_listed_with_its_parameters_by_name_and_kind():
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
            "deep": {"type": "boolean"},
        },
        "required": ["query", "deep"],
    }

    listed = one(schema)

    wanted = "- mcp__notion__act(query: string, limit?: integer, deep: boolean): "
    assert listed == wanted + "[MCP notion] Does it."


@pytest.mark.parametrize("kind", sorted(JSON_TYPES))
def test_a_kind_json_knows_is_shown_as_it_is(kind):
    schema = {"type": "object", "properties": {"x": {"type": kind}}}

    assert one(schema) == f"- mcp__notion__act(x?: {kind}): [MCP notion] Does it."


def test_the_kinds_json_knows_are_these_seven():
    assert JSON_TYPES == {"string", "number", "integer", "boolean", "array", "object", "null"}


@pytest.mark.parametrize(
    "said",
    [{"type": "date"}, {"type": ["string", "null"]}, {"type": 5}, {}, "string", None, [1]],
)
def test_a_kind_that_is_anything_else_is_shown_as_any(said):
    schema = {"type": "object", "properties": {"x": said}}

    assert one(schema) == "- mcp__notion__act(x?: any): [MCP notion] Does it."


@pytest.mark.parametrize(
    ("schema", "shown"),
    [
        ({"type": "object"}, ""),
        ({"type": "object", "properties": [{"type": "string"}]}, ""),
        ({"type": "object", "properties": {}}, ""),
        # Without a list of the required ones, every parameter may be left out.
        ({"type": "object", "properties": {"x": {}}, "required": "x"}, "x?: any"),
        ({"type": "object", "properties": {"x": {}}, "required": {"x": True}}, "x?: any"),
        # A server that sends no schema of an object has no parameters here.
        ({"type": "array", "properties": {"x": {}}}, ""),
    ],
)
def test_a_schema_of_any_shape_is_read_without_failing(schema, shown):
    assert one(schema) == f"- mcp__notion__act({shown}): [MCP notion] Does it."


def test_a_parameter_whose_name_is_not_a_plain_word_is_left_out():
    names = [
        "ok_name",
        "two words",
        "x-y",
        "",
        "a" * 40,
        "b" * 41,
        "x): done.\n- mcp__notion__other(",
        "tên",
    ]
    schema = {"type": "object", "properties": {name: {"type": "string"} for name in names}}

    listed = one(schema)

    shown = f"ok_name?: string, {'a' * 40}?: string, tên?: string"
    assert listed == f"- mcp__notion__act({shown}): [MCP notion] Does it."


def test_a_tool_with_many_parameters_is_listed_with_its_first_dozen():
    def schema(count: int) -> dict:
        return {"type": "object", "properties": {f"p{i}": {"type": "null"} for i in range(count)}}

    dozen = ", ".join(f"p{i}?: null" for i in range(12))

    assert one(schema(12)) == f"- mcp__notion__act({dozen}): [MCP notion] Does it."
    assert one(schema(13)) == f"- mcp__notion__act({dozen}, …): [MCP notion] Does it."


def test_a_long_description_is_one_short_line_of_the_list():
    def said(description: str) -> str:
        return one(SCHEMA, description).removeprefix("- mcp__notion__act(): ")

    # "[MCP notion] " is thirteen letters of the hundred.
    assert said("d" * 87) == "[MCP notion] " + "d" * 87
    assert said("d" * 88) == "[MCP notion] " + "d" * 86 + "…"
    spread = said("Reads\n  a page.\n" + "word " * 60)
    assert spread.startswith("[MCP notion] Reads a page. word word ")
    assert len(spread) == 100 and spread.endswith("…") and "\n" not in spread


def many(count: int) -> list[McpTool]:
    listed = [{"name": f"read-{i:02}", "description": f"Reads {i}."} for i in range(count)]
    names = [raw["name"] for raw in listed]
    return built(listed, read_only=names, exposure="codemode")


def listed_lines(tools: list[Tool]) -> list[str]:
    told = toolbox(*tools).get(SCRIPT_TOOL).description
    return [line for line in told.splitlines() if line.startswith("- ")]


def test_a_script_is_told_of_thirty_tools_and_of_how_many_more_there_are():
    assert listed_lines(many(30)) == [
        f"- mcp__notion__read_{i:02}(): [MCP notion] Reads {i}." for i in range(30)
    ]

    lines = listed_lines(many(32))

    assert len(lines) == 31 and lines[:30] == listed_lines(many(30))
    assert lines[30] == "- … và 2 công cụ nữa, tìm bằng tools.search."


def test_a_script_is_told_up_front_only_of_the_tools_the_owner_opened_for_scripts():
    listed = [{"name": f"read-{i}", "description": f"Reads {i}."} for i in range(5)]
    names = [raw["name"] for raw in listed]
    opened = {"read-1": "codemode", "read-3": "codemode"}

    lines = listed_lines(built(listed, read_only=names, tool_exposure=opened))

    # The other three are the script's to call as well: it is told how many there are.
    assert lines == [
        "- mcp__notion__read_1(): [MCP notion] Reads 1.",
        "- mcp__notion__read_3(): [MCP notion] Reads 3.",
        "- … và 3 công cụ nữa, tìm bằng tools.search.",
    ]


def test_a_script_with_no_tool_opened_for_it_is_still_told_how_many_it_may_call():
    listed = [{"name": f"read-{i}", "description": f"Reads {i}."} for i in range(4)]
    names = [raw["name"] for raw in listed]

    told = toolbox(*built(listed, read_only=names)).get(SCRIPT_TOOL).description

    assert [line for line in told.splitlines() if line.startswith("- ")] == [
        "- … và 4 công cụ nữa, tìm bằng tools.search."
    ]
    assert "Công cụ MCP gọi được từ script" in told


def test_the_tools_not_listed_are_counted_with_those_past_the_thirtieth():
    listed = [{"name": f"read-{i:02}", "description": f"Reads {i}."} for i in range(35)]
    names = [raw["name"] for raw in listed]
    opened = {f"read-{i:02}": "codemode" for i in range(32)}

    lines = listed_lines(built(listed, read_only=names, tool_exposure=opened))

    assert len(lines) == 31 and lines[:30] == listed_lines(many(30))
    assert lines[30] == "- … và 5 công cụ nữa, tìm bằng tools.search."


def rows(count: int) -> list[Tool]:
    return [Reads(f"row_{i:02}_read").tool for i in range(count)]


def test_the_agents_own_tools_are_listed_first_and_count_among_the_thirty():
    lines = listed_lines([*rows(2), *many(30)])

    assert lines[:2] == ["- row_00_read()", "- row_01_read()"]
    assert lines[2:30] == listed_lines(many(30))[:28]
    # The two a server's that found no room are counted, not dropped.
    assert lines[30:] == ["- … và 2 công cụ nữa, tìm bằng tools.search."]


def test_a_tool_of_the_agents_own_is_listed_with_its_parameters_and_no_summary():
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["path"],
    }
    own = replace(Reads("rows_read").tool, description="Đọc các dòng.", parameters=schema)

    told = toolbox(own).get(SCRIPT_TOOL).description

    # The agent is told what the tool is for where the tool itself is declared.
    assert "\n- rows_read(path: string, limit?: integer)\n" in told
    assert "Đọc các dòng" not in told


def test_an_agent_with_more_than_thirty_tools_of_its_own_is_told_how_many_more():
    told = toolbox(*rows(32)).get(SCRIPT_TOOL).description

    lines = [line for line in told.splitlines() if line.startswith("- ")]
    assert lines[:30] == [f"- row_{i:02}_read()" for i in range(30)]
    assert lines[30:] == ["- … và 2 công cụ nữa, tìm bằng tools.search."]
    assert "Công cụ MCP" not in told


def test_what_is_not_listed_is_counted_once_whichever_kind_it_is():
    told = toolbox(*rows(31), *many(3)).get(SCRIPT_TOOL).description

    lines = [line for line in told.splitlines() if line.startswith("- ")]
    # One of the agent's own and the server's three, in one line that ends the list.
    assert lines[:30] == [f"- row_{i:02}_read()" for i in range(30)]
    assert lines[30:] == ["- … và 4 công cụ nữa, tìm bằng tools.search."]
    assert told.count("công cụ nữa") == 1 and "mcp__notion__read_" not in told
    assert told.index("Công cụ MCP gọi được từ script") < told.index("- … và 4 công cụ nữa")


async def test_a_tool_past_the_thirty_listed_is_a_scripts_to_call_all_the_same():
    calls: list = []
    listed = [{"name": f"read-{i:02}", "description": f"Reads {i}."} for i in range(32)]
    names = [raw["name"] for raw in listed]
    tools = notion(calls, listed, read_only=names, exposure="codemode")

    result = await play(toolbox(*tools), "print(tools.mcp__notion__read_31())")

    assert (result.ok, result.output) == (True, "ran read-31")
    assert calls == [("read-31", {})]


async def test_an_agent_with_a_tool_opened_for_scripts_is_handed_the_script_tool(deps_factory):
    deps, own, _ = await handed(deps_factory, server(**OPENED))

    # After the search and ahead of the tools themselves: what is told up front never moves.
    assert deps.tools.names() == [*own, SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME]
    told = deps.tools.get(SCRIPT_TOOL).description
    assert f"- {SEARCH_NAME}(query: string): [MCP notion] Find pages by words." in told
    # Only what a script may call is told of. The tool that writes is the turn's to call.
    assert CREATE_NAME not in told
    builtins = [
        "- workspace_list(path?: string)",
        "- workspace_read(path: string, offset?: integer, limit?: integer)",
        "- memory_search(query: string)",
        "- skill_read(name: string)",
    ]
    assert [line for line in told.splitlines() if line.startswith("- ")][:-1] == builtins
    assert told.index("Công cụ có sẵn gọi được từ script") < told.index("Công cụ MCP gọi được")


@pytest.mark.parametrize(
    ("opened", "told"),
    [
        ({"read_only": ["search"]}, [SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME]),
        (
            {"read_only": ["search"], "exposure": "deferred"},
            [SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME],
        ),
        (
            {"read_only": ["search"], "tool_exposure": {"search": "direct"}},
            [SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME],
        ),
        # Every tool let in directly: nothing waits to be found, and the script tool is
        # still there for the one that reads.
        (
            {"read_only": ["search"], "exposure": "direct"},
            [SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME],
        ),
    ],
)
async def test_an_agent_with_a_tool_that_reads_is_handed_the_script_tool_however_far_it_is_let_in(
    deps_factory, opened, told
):
    deps, own, _ = await handed(deps_factory, server(**opened))

    assert deps.tools.names() == [*own, *told]
    description = deps.tools.get(SCRIPT_TOOL).description
    # Not opened for scripts, so not listed; the script is told how many it may call.
    assert SEARCH_NAME not in description
    assert "- … và 1 công cụ nữa, tìm bằng tools.search." in description
    assert CREATE_NAME not in description


@pytest.mark.parametrize(
    "opened",
    [
        {},
        # Opened for scripts without the owner saying it only reads: a script may not
        # call it, so the script tool has nothing of the server's to name.
        {"tool_exposure": {"search": "codemode"}},
        {"exposure": "codemode"},
        {"exposure": "direct"},
        # What reads is hidden: no agent holds it.
        {"read_only": ["search"], "tool_exposure": {"search": "hidden"}},
        {"read_only": ["search"], "exposure": "hidden"},
    ],
)
async def test_an_agent_whose_server_has_no_tool_a_script_may_call_holds_it_for_its_own_tools(
    deps_factory, opened
):
    alone, _, _ = await handed(deps_factory, server(**opened), mcp=())

    deps, own, _ = await handed(deps_factory, server(**opened))

    held = [name for name in deps.tools.names() if not name.startswith(PREFIX)]
    # Last of what is the agent's own, behind the search when a tool waits to be found.
    assert held[: len(own)] == own and held[-1] == SCRIPT_TOOL and held.count(SCRIPT_TOOL) == 1
    assert set(held[len(own) : -1]) <= {SEARCH_TOOL}
    told = deps.tools.get(SCRIPT_TOOL).description
    assert told == alone.tools.get(SCRIPT_TOOL).description
    assert "Công cụ MCP" not in told and PREFIX not in told and "công cụ nữa" not in told


async def test_an_agent_that_names_no_server_is_handed_the_script_tool_for_its_own_tools(
    deps_factory,
):
    deps, own, _ = await handed(deps_factory, server(**OPENED), mcp=())

    assert deps.tools.names() == [*own, SCRIPT_TOOL]
    assert SEARCH_NAME not in deps.tools.get(SCRIPT_TOOL).description


async def test_handing_out_again_leaves_one_script_tool_in_its_place(deps_factory):
    deps, _, hub = await handed(deps_factory, server(**OPENED))
    first = deps.tools.names()

    hub.attach({"default": deps})

    assert deps.tools.names() == first and first.count(SCRIPT_TOOL) == 1


async def test_the_script_tool_stops_naming_a_tool_the_owner_no_longer_calls_a_read(
    deps_factory,
):
    deps, own, _ = await handed(deps_factory, server(**OPENED))
    before = deps.tools.get(SCRIPT_TOOL).description
    # The owner took `read_only` off: the search asks first again, and is no script's.
    closed = make_hub(FakeMcp(), server())
    await closed.connect()

    closed.attach({"default": deps})

    # Still there, in its place, for the agent's own tools. That it goes with the last tool
    # a script may call is in `test_script_handout.py`.
    assert deps.tools.names() == [*own, SEARCH_TOOL, SCRIPT_TOOL, SEARCH_NAME, CREATE_NAME]
    after = deps.tools.get(SCRIPT_TOOL).description
    assert SEARCH_NAME in before and PREFIX not in after and "Công cụ MCP" not in after
    refused = await play(deps.tools, 'tools.mcp__notion__search(query="kế hoạch")')
    reason = t.SCRIPT_ASKS_FIRST.format(name=SEARCH_NAME, instead=t.SCRIPT_LOAD_THEN_CALL)
    assert (refused.ok, refused.output) == (False, unfinished(halted(1, reason)))


async def test_a_script_of_an_agents_reads_its_files_and_its_servers(deps_factory):
    fake = FakeMcp()
    deps, _, hub = await handed(deps_factory, server(**OPENED), fake=fake)
    (deps.agent.workspace / "ghi.txt").write_text("ba\nbốn\n", encoding="utf-8")
    # Handed out twice, as a start and a later change of a server do: the script still
    # calls the tools the agent holds now.
    hub.attach({"default": deps})

    result = await play(
        deps.tools,
        """
        print(tools.mcp__notion__search(query="kế hoạch"))
        print(tools.workspace_read(path="ghi.txt").split())
        """,
    )
    refused = await play(deps.tools, "tools.mcp__notion__create_page(title='x')")

    assert (result.ok, result.output) == (True, "ran search\n['ba', 'bốn']")
    assert [call.name for call in result.calls] == [SEARCH_NAME, "workspace_read"]
    reason = t.SCRIPT_ASKS_FIRST.format(name=CREATE_NAME, instead=t.SCRIPT_LOAD_THEN_CALL)
    assert (refused.ok, refused.output) == (False, unfinished(halted(1, reason)))
    assert fake.calls == [("search", {"query": "kế hoạch"})]


async def test_a_delegated_run_calls_from_a_script_what_its_agent_holds_now(deps_factory):
    """A delegated run keeps the copy of the tools it was handed when it began. A tool the
    owner stopped calling a read meanwhile is not reached through the script tool of that
    copy."""
    fake = FakeMcp()
    deps, _, _ = await handed(deps_factory, server(**OPENED), fake=fake)
    delegated = deps.tools.without(DELEGATE_TOOL_NAME)
    closed = make_hub(FakeMcp(), server())
    await closed.connect()
    closed.attach({"default": deps})

    refused = await play(delegated, 'tools.mcp__notion__search(query="kế hoạch")')

    reason = t.SCRIPT_ASKS_FIRST.format(name=SEARCH_NAME, instead=t.SCRIPT_LOAD_THEN_CALL)
    assert (refused.ok, refused.output) == (False, unfinished(halted(1, reason)))
    assert fake.calls == []
