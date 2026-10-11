"""A script that may change things writes to the canvas, by the rules of the turn it is a
call of.

No canvas tool that writes waits for a person, so the approval gate lets a script of an agent
whose file says `script_calls: gated` make a canvas, edit it, write it over and bring a file
into one. Each of those tools reads the turn it is called in, and a script is one call of that
turn: what it writes lands in the turn's conversation under the agent's name, is counted with
what the model wrote in the turn, and is refused where the turn came from somewhere no canvas
gets back from (`tools/artifact*.py` under `script/nested.py`). The result of a write opens
with the tag that names the canvas, and what is kept of the call opens with that tag whole:
the web opens the canvas from it. A page of a canvas stays out of every script
(`test_script_canvas.py`), an agent left as it was writes none from a script, and the script
of a schedule has no conversation to write one in. Every script here runs in a real child
process."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from textwrap import dedent
from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.activity.step_previews import argument_preview, preview
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.turn_context import (
    API,
    CHAT,
    DELEGATE,
    JOB,
    TELEGRAM,
    set_tool_call_id,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.agents import default_profile
from my_agent_crew.artifacts.kinds import TITLE_MAX
from my_agent_crew.artifacts.tag import Tag, artifact_tag, parse_artifact_tag
from my_agent_crew.channels.telegram_canvas_notice import tags_of, written_by
from my_agent_crew.config import Settings
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.script.scope import SCRIPT_TOOL
from my_agent_crew.store import Conversation, Store
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.runs import DONE, FAILED
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_CHANNEL_CLOSED,
    ARTIFACT_CREATE_BUDGET,
    ARTIFACT_NO_CONVERSATION,
    ARTIFACT_VERSION_CONFLICT,
    ARTIFACT_WRITE_BUDGET,
)
from my_agent_crew.tools import artifact_scope
from my_agent_crew.tools.artifact import build_artifact_tools
from my_agent_crew.tools.artifact_files import build_artifact_file_tools
from my_agent_crew.tools.artifact_scope import CANVAS_WRITE_TOOLS
from my_agent_crew.tools.artifact_texts import ARTIFACT_SEND_LINE
from my_agent_crew.tools.registry import Tool
from my_agent_crew.tools.result import ToolResult
from tests.restart_helpers import stored_run
from tests.test_mcp_turns import say
from tests.test_script_gate import AUTONOMOUS, SUPERVISED, agent, conversation
from tests.test_script_gated_turns import KEPT, stored_calls
from tests.test_script_job_gate import DUE, scheduled
from tests.test_script_tool import Hooks, erred, halted, unfinished
from tests.test_script_turns import the_result, the_step
from tests.test_tool_replay import changing

AGENT, AUTHOR, CAP = "default", "agent:default", 8000
TITLE, NOTE = "Kế hoạch tuần", "# Tuần này\n- chạy 5 km\n"
MAKING = {"title": TITLE, "kind": "markdown", "content": NOTE}
MAKE = f"artifact_create(title={TITLE!r}, kind='markdown', content={NOTE!r})"
FROM_FILE = "từ tệp\n"
LONG = "T" * TITLE_MAX


def canvas_tools(store: Store, settings: Settings) -> list[Tool]:
    """The canvas tools as the server hands them to the default agent, over its workspace."""
    root = default_profile(settings).workspace
    return [
        *build_artifact_tools(store, AGENT, False, CAP),
        *build_artifact_file_tools(store, AGENT, False, CAP, root, ()),
    ]


@pytest.fixture
def writer(deps_factory, store, settings):
    """An agent with the canvas tools and a file in its workspace, handed the script tool as
    the server hands it. Its scripts may change things unless it is told otherwise."""

    def build(script_calls: str = "gated") -> AgentDeps:
        held = canvas_tools(store, settings)
        deps, _ = agent(deps_factory, *held, script_calls=script_calls)
        (deps.agent.workspace / "ghi.md").write_text(FROM_FILE, encoding="utf-8")
        return deps

    return build


async def in_a_turn[T](
    conv: Conversation, work: Callable[[], Awaitable[T]], came_from: str = CHAT
) -> T:
    """`work` as part of one turn of the conversation, begun where `came_from` says. The turn
    is set in a task of its own, so nothing of it is left for the next test."""

    async def turn() -> T:
        set_turn_source(came_from)
        set_turn_conversation(conv.id)
        set_tool_call_id("s1")
        return await work()

    return await asyncio.create_task(turn())


def scripted(deps: AgentDeps, source: str) -> Awaitable[ToolResult]:
    return deps.tools.execute(SCRIPT_TOOL, {"script": dedent(source)})


def directly(deps: AgentDeps, name: str, **arguments: Any) -> Awaitable[ToolResult]:
    """The call as the model makes it itself, outside any script."""
    return deps.tools.execute(name, arguments)


async def a_turn(
    deps: AgentDeps, conv: Conversation, source: str, came_from: str = CHAT
) -> ToolResult:
    """One turn whose one call is the script."""
    return await in_a_turn(conv, lambda: scripted(deps, source), came_from)


async def made_directly(deps: AgentDeps, conv: Conversation) -> str:
    """A canvas the model made in a turn of its own, at its first version."""
    made = await in_a_turn(conv, lambda: directly(deps, "artifact_create", **MAKING))
    return named(made.output).id


def named(output: str) -> Tag:
    tag = parse_artifact_tag(output)
    assert tag is not None, output
    return tag


def trying(*calls: str) -> str:
    """A script that makes each call and prints what it was answered, or how it failed."""
    return "\n".join(
        f"try:\n    print(tools.{call})\nexcept Exception as e:\n    print(e)" for call in calls
    )


def every_write(art: str) -> list[str]:
    """One call of each canvas tool that writes, in the order of `CANVAS_WRITE_TOOLS`."""
    return [
        MAKE,
        f"artifact_edit(id={art!r}, old='5 km', new='8 km')",
        f"artifact_rewrite(id={art!r}, content='viết lại\\n')",
        f"artifact_import(path='ghi.md', id={art!r})",
    ]


def left(store: Store, conv: Conversation, tag: Tag) -> tuple:
    """What a write leaves of a canvas, but for the id it was given."""
    summary, head = store.artifacts.get(tag.id), store.artifacts.head(tag.id)
    link = store.artifact_links.get(conv.id, tag.id)
    return (
        (summary.title, summary.kind, summary.agent_id, summary.head_version),
        (head.version, head.author, head.conversation_id == conv.id, head.content),
        (link.shared, link.seen_version),
        [
            (written.id == tag.id, written.version)
            for written in store.artifacts.written_in(conv.id)
        ],
    )


# --- in the turn's conversation, under the agent's name ---


@pytest.mark.parametrize("kind", [AUTONOMOUS, SUPERVISED])
async def test_a_canvas_a_script_makes_is_the_one_a_direct_call_would_have_made(
    writer, store, kind
):
    deps = writer()
    by_script, by_model = conversation(deps, kind), conversation(deps, kind)

    result = await a_turn(deps, by_script, f"print(tools.{MAKE})")
    direct = await in_a_turn(by_model, lambda: directly(deps, "artifact_create", **MAKING))

    assert result.ok and direct.ok
    made, same = named(result.output), named(direct.output)
    assert made.id != same.id
    # The script was handed the tool's whole answer, the tag first, as the model is.
    assert result.output.replace(made.id, same.id) == direct.output
    assert left(store, by_script, made) == left(store, by_model, same)
    assert left(store, by_script, made) == (
        (TITLE, "markdown", AGENT, 1),
        (1, AUTHOR, True, NOTE),
        # Shared with the conversation, and seen there at the version just written.
        (True, 1),
        [(True, 1)],
    )
    # Nobody was asked, whoever watches: no canvas tool that writes waits for a person.
    assert deps.store.approvals.pending(by_script.id) is None
    [call] = result.calls
    assert (call.name, call.ok, call.gated) == ("artifact_create", True, True)
    assert (call.metered, call.cost_usd) == (False, None)


async def test_a_script_edits_writes_over_and_brings_a_file_into_a_canvas(writer, store):
    deps = writer()
    conv = conversation(deps, SUPERVISED)
    source = f"""
        made = tools.{MAKE}
        art = made.split()[1]
        tools.artifact_edit(id=art, old="5 km", new="8 km")
        tools.artifact_rewrite(id=art, content="viết lại\\n")
        tools.artifact_import(path="ghi.md", id=art)
        tools.artifact_import(path="ghi.md", title="Bản chép")
        print(art)
        """

    result = await a_turn(deps, conv, source)

    assert result.ok
    art = result.output
    history = store.artifacts.versions(art)
    assert [(version.version, version.author, version.conversation_id) for version in history] == [
        (number, AUTHOR, conv.id) for number in (1, 2, 3, 4)
    ]
    assert store.artifacts.head(art).content == FROM_FILE
    # Each call is kept as one that went by the gate, and opens with the canvas it wrote.
    tags = [named(call.output) for call in result.calls]
    other = tags[-1].id
    assert tags == [Tag(art, 1), Tag(art, 2), Tag(art, 3), Tag(art, 4), Tag(other, 1)]
    assert [(call.name, call.ok, call.gated) for call in result.calls] == [
        ("artifact_create", True, True),
        ("artifact_edit", True, True),
        ("artifact_rewrite", True, True),
        ("artifact_import", True, True),
        ("artifact_import", True, True),
    ]
    written = {
        canvas.id: (canvas.version, canvas.title) for canvas in store.artifacts.written_in(conv.id)
    }
    assert written == {art: (4, TITLE), other: (1, "Bản chép")}
    assert store.artifacts.head(other).author == AUTHOR
    assert store.artifact_links.get(conv.id, art).seen_version == 4


async def test_a_script_reads_no_page_and_so_writes_over_nothing_a_person_saved_unseen(
    writer, store
):
    """A rewrite goes over the version its conversation last saw and no other. Seeing the one a
    person saved since takes a read, and that read is no script's to make, whatever else its
    scripts may do."""
    deps = writer()
    conv = conversation(deps)
    art = await made_directly(deps, conv)
    store.artifacts.write(art, "người sửa\n", USER, "")
    source = "\n".join(
        [
            trying(f"artifact_rewrite(id={art!r}, content='của script\\n')"),
            f"tools.artifact_read(id={art!r})",
            'print("đã đọc")',
        ]
    )

    result = await a_turn(deps, conv, source)

    # The write is refused as it is for the model, which is told what changed since it looked...
    newer = TOOL_FAILED.format(error=ARTIFACT_VERSION_CONFLICT.format(head=2))
    assert not result.ok and result.output.startswith(unfinished(newer) + "\n")
    # ...and the read that would let it through ends the script where it was asked.
    kept_out = t.SCRIPT_NOT_FROM_SCRIPT.format(name="artifact_read", instead=t.SCRIPT_CALL_DIRECTLY)
    assert result.output.splitlines()[-1] == halted(5, kept_out)
    head = store.artifacts.head(art)
    assert (head.version, head.author, head.content) == (2, USER, "người sửa\n")
    assert store.artifact_links.get(conv.id, art).seen_version == 1
    assert [(call.name, call.ok) for call in result.calls] == [("artifact_rewrite", False)]


# --- counted with what the turn wrote ---


@pytest.fixture
def two_a_turn(monkeypatch) -> int:
    """A turn may make two canvases, and write two versions of one."""
    monkeypatch.setattr(artifact_scope, "CANVAS_WRITES_PER_TURN", 2)
    return 2


async def test_the_canvases_a_script_made_are_counted_when_the_model_makes_one_after_it(
    writer, store, two_a_turn
):
    deps = writer()
    conv = conversation(deps)

    async def script_then_model() -> tuple[ToolResult, ToolResult]:
        by_script = await scripted(deps, trying(MAKE, MAKE))
        return by_script, await directly(deps, "artifact_create", **MAKING)

    by_script, direct = await in_a_turn(conv, script_then_model)

    spent = TOOL_FAILED.format(error=ARTIFACT_CREATE_BUDGET.format(limit=two_a_turn))
    assert by_script.ok and [call.ok for call in by_script.calls] == [True, True]
    assert (direct.ok, direct.output) == (False, spent)
    assert len(store.artifacts.list(conv.id)) == 2


async def test_the_canvases_the_model_made_are_counted_when_a_script_makes_one_after_them(
    writer, store, two_a_turn
):
    deps = writer()
    conv = conversation(deps)

    async def model_then_script() -> ToolResult:
        assert (await directly(deps, "artifact_create", **MAKING)).ok
        return await scripted(deps, trying(MAKE, MAKE))

    by_script = await in_a_turn(conv, model_then_script)

    # A mistake the script catches, in the words the model is told when it makes the call.
    spent = TOOL_FAILED.format(error=ARTIFACT_CREATE_BUDGET.format(limit=two_a_turn))
    assert by_script.ok and by_script.output.splitlines()[-1] == spent
    first, second = by_script.calls
    assert first.ok and (second.ok, second.output) == (False, preview(spent))
    assert len(store.artifacts.list(conv.id)) == 2
    # The turn after counts from nothing, as it does for the model.
    assert (await a_turn(deps, conv, f"print(tools.{MAKE})")).ok


async def test_the_versions_a_script_writes_of_a_canvas_are_counted_with_the_models(
    writer, store, two_a_turn
):
    deps = writer()
    conv = conversation(deps)

    async def model_then_script() -> tuple[str, ToolResult]:
        art = named((await directly(deps, "artifact_create", **MAKING)).output).id
        assert (await directly(deps, "artifact_edit", id=art, old="Tuần này", new="Tuần sau")).ok
        return art, await scripted(deps, trying(*every_write(art)[1:]))

    art, by_script = await in_a_turn(conv, model_then_script)

    spent = TOOL_FAILED.format(error=ARTIFACT_WRITE_BUDGET.format(limit=two_a_turn))
    # The model wrote one version of it and the script the second: no tool writes a third.
    assert [(call.name, call.ok) for call in by_script.calls] == [
        ("artifact_edit", True),
        ("artifact_rewrite", False),
        ("artifact_import", False),
    ]
    assert by_script.output.splitlines()[-2:] == [spent, spent]
    head = store.artifacts.head(art)
    assert (head.version, head.content) == (3, "# Tuần sau\n- chạy 8 km\n")


# --- where the turn came from ---


@pytest.mark.parametrize(
    ("came_from", "began_at"),
    # Nothing carries a canvas back through the inbound API, to a child of such a turn either.
    [(API, ""), (f"{DELEGATE}:cha", API)],
)
async def test_a_turn_that_may_write_no_canvas_writes_none_from_a_script(
    writer, store, came_from, began_at
):
    deps = writer()
    conv = deps.store.create(autonomous=True, root_source=began_at)
    art = await made_directly(deps, deps.store.create(autonomous=True))

    result = await a_turn(deps, conv, trying(*every_write(art)), came_from)

    closed = TOOL_FAILED.format(error=ARTIFACT_CHANNEL_CLOSED)
    assert (result.ok, result.output) == (True, "\n".join([closed] * 4))
    assert [(call.name, call.ok, call.output) for call in result.calls] == [
        (name, False, preview(closed)) for name in CANVAS_WRITE_TOOLS
    ]
    assert [(canvas.id, canvas.head_version) for canvas in store.artifacts.list()] == [(art, 1)]
    assert store.artifact_links.links_for(conv.id) == []


@pytest.mark.parametrize(
    ("came_from", "began_at"), [(TELEGRAM, ""), (JOB, ""), (f"{DELEGATE}:cha", TELEGRAM)]
)
async def test_a_script_writing_for_a_reader_away_from_the_web_is_told_how_to_send_the_canvas(
    writer, store, came_from, began_at
):
    deps = writer()
    conv = deps.store.create(autonomous=True, root_source=began_at)

    result = await a_turn(deps, conv, f"print(tools.{MAKE})", came_from)

    assert result.ok
    made = named(result.output)
    assert result.output.splitlines()[-1] == ARTIFACT_SEND_LINE.format(id=made.id)
    assert store.artifacts.head(made.id).conversation_id == conv.id


# --- what is kept of a write ---


def test_a_preview_keeps_the_tag_a_result_opens_with_whatever_follows_it():
    """A tag is far shorter than a preview, and a preview only ever cuts the end."""
    art = "0123456789ab"
    tag = artifact_tag(art, 123_456)

    for rest in ("", "\n" + "x" * 1000, "\n\n  nhiều\tkhoảng   trắng\n" * 40):
        assert parse_artifact_tag(preview(tag + rest)) == Tag(art, 123_456)
    same = artifact_tag(art, 7, unchanged=True)
    assert parse_artifact_tag(preview(same + "\n" + "x" * 1000)) == Tag(art, 7, True)


async def test_what_is_kept_of_a_write_opens_with_its_tag_whole_however_long_the_rest(
    writer, store
):
    deps = writer()
    # A hook of the agent's leaves a note after the write, as it may after any call.
    deps.tools.hooks = Hooks(noted=("artifact_create",))
    conv = conversation(deps)
    source = "\n".join(
        [
            f"made = tools.artifact_create(title={LONG!r}, kind='markdown', content='x\\n')",
            "print(made)",
            "art = made.split()[1]",
            "tools.artifact_rewrite(id=art, content='x\\n')",
            "try:",
            "    tools.artifact_edit(id=art, old='không có', new='y')",
            "except Exception:",
            "    pass",
        ]
    )

    result = await a_turn(deps, conv, source)

    [canvas] = store.artifacts.list(conv.id)
    made, same, failed = result.calls
    # What the tool answered is longer than a preview and ends on the hook's note...
    whole = result.output
    assert result.ok and whole.endswith("[đã ghi sổ]") and len(whole) > len(made.output)
    # ...and what is kept of it is cut at its end alone.
    assert made.output == preview(whole) and made.output.endswith("…")
    assert named(made.output) == Tag(canvas.id, 1)
    # A write that changed nothing says so in its tag, and one that failed has none.
    assert named(same.output) == Tag(canvas.id, 1, True)
    assert not failed.ok and parse_artifact_tag(failed.output) is None


async def test_a_canvas_a_script_made_in_a_turn_is_named_wherever_its_calls_are_listed(
    served, store, settings
):
    asks = ToolCall("p1", SCRIPT_TOOL, {"script": f"print(tools.{MAKE})"})
    app = served(
        [completion(tool_calls=[asks]), completion("Xong.")],
        extra_tools=canvas_tools(store, settings),
    )
    changing(app)

    events = await say(app)

    kinds = [event["type"] for event in events]
    # The conversation is a supervised one, and nobody was asked.
    assert "approval_required" not in kinds and kinds[-1] == "done"
    [canvas] = store.artifacts.list(app.conv.id)
    result = the_result(events)
    [call] = result["calls"]
    assert call == {
        "name": "artifact_create",
        "arguments": argument_preview(MAKING),
        "ok": True,
        "output": preview(result["output"]),
        "ms": call["ms"],
        "cost_usd": None,
        "metered": False,
        "gated": True,
    }
    assert set(call) == KEPT | {"gated"}
    assert named(call["output"]) == Tag(canvas.id, 1)
    # As the call ended, on the run, and beside the result the conversation keeps.
    assert [event["call"] for event in events if event["type"] == "nested_call"] == [call]
    assert the_step(app)["calls"] == [call]
    assert stored_calls(app) == [call]
    # So a chat is told of it as of a canvas the model made: from the turn as it passes, and
    # from what the run stored (`channels/telegram_canvas_notice.py`).
    assert tags_of(result["name"], result["output"], result["calls"]) == [Tag(canvas.id, 1)]
    assert written_by(store, app.conv.id, stored_run(app)) == [Tag(canvas.id, 1)]
    head = store.artifacts.head(canvas.id)
    assert (head.author, head.conversation_id, head.content) == (AUTHOR, app.conv.id, NOTE)


# --- an agent left as it was ---


@pytest.mark.parametrize("name", CANVAS_WRITE_TOOLS)
async def test_a_script_of_an_agent_left_as_it_was_writes_no_canvas_and_is_told_who_does(
    writer, store, name
):
    deps = writer("read_only")
    conv = conversation(deps)
    art = await made_directly(deps, conv)
    call = every_write(art)[CANVAS_WRITE_TOOLS.index(name)]

    result = await a_turn(deps, conv, trying(call) + '\nprint("sau")')

    # Not a mistake the script catches and carries on from: it ends where it asked.
    reason = t.SCRIPT_ASKS_FIRST.format(name=name, instead=t.SCRIPT_CALL_DIRECTLY)
    assert (result.ok, result.output) == (False, unfinished(halted(2, reason)))
    assert result.calls == ()
    assert [(canvas.id, canvas.head_version) for canvas in store.artifacts.list()] == [(art, 1)]


# --- the script of a schedule ---


async def test_a_schedules_script_has_no_conversation_to_write_a_canvas_in(writer, store):
    deps = writer()
    earlier = conversation(deps)

    async def after_the_turn_of_another_job():
        # Jobs run one after another in one task: the turn before left its conversation there.
        art = named((await directly(deps, "artifact_create", **MAKING)).output).id
        sched = scheduled(deps, trying(*every_write(art)))
        return art, await sched.run_job(DUE)

    art, run = await in_a_turn(earlier, after_the_turn_of_another_job, JOB)

    nowhere = TOOL_FAILED.format(error=ARTIFACT_NO_CONVERSATION)
    # Each write failed as a mistake the script caught, in words that say what a canvas needs.
    assert run.status == DONE and run.summary.endswith(nowhere)
    kept = [(call["name"], call["ok"], call["output"]) for call in run.steps[0]["calls"]]
    assert kept == [(name, False, preview(nowhere)) for name in CANVAS_WRITE_TOOLS]
    # Nothing was written, least of all into the conversation the task was last in.
    assert [(canvas.id, canvas.head_version) for canvas in store.artifacts.list()] == [(art, 1)]
    assert [written.version for written in store.artifacts.written_in(earlier.id)] == [1]
    assert run.conversation_id is None
    assert [conv.id for conv in deps.store.list()] == [earlier.id]


async def test_a_canvas_write_a_schedules_script_did_not_catch_fails_its_run_and_no_more(
    writer, store
):
    deps = writer()
    sched = scheduled(deps, f"tools.{MAKE}\nprint('đã tạo')")

    run = await sched.run_job(DUE)

    nowhere = TOOL_FAILED.format(error=ARTIFACT_NO_CONVERSATION)
    said = unfinished(erred(1, nowhere))
    assert (run.status, run.steps[0]["output"]) == (FAILED, preview(said))
    assert store.artifacts.list() == [] and deps.store.list() == []
