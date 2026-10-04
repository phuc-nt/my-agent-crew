"""The canvases a delegated agent wrote, named in the result its delegator reads: one line
each right under the outcome line, a blank line that is always there, then the child's own
words. Those words alone are what gets handed to the person."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.artifacts.tag import TAG_RE
from my_agent_crew.config import DEFAULT_TOOL_OUTPUT_CHARS, Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Completion, ToolCall
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.models import Conversation
from my_agent_crew.store.runs import AWAITING, HALTED
from my_agent_crew.texts_canvas import ARTIFACT_REWRITE_UNSEEN, CANVAS_NOTE_NEW
from my_agent_crew.tools.artifact import build_artifact_tools
from my_agent_crew.tools.artifact_files import build_artifact_file_tools
from my_agent_crew.tools.delegate_report import FIELD_CHARS, MAX_LISTED, canvas_lines
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import (
    PLAN,
    SWIM,
    agents_canvas,
    call,
    framed,
    noted,
    persons_canvas,
    put,
    say,
    seen,
    turn,
)
from tests.test_tools_delegate import agent, delegation_result, wait_until_paused, web_pattern

ECHO = (Route("fake", "echo"),)
WORKER = "agent:worker"
FILE = "notes/plan.md"
# Canvas ids in the order the store hands them out here, so a scripted child can name the
# canvas an earlier step of its script made.
IDS = [f"{n:012x}" for n in range(1, 40)]
A, B = IDS[0], IDS[1]
_calls = itertools.count(1)


@pytest.fixture(autouse=True)
def known_ids(monkeypatch) -> Iterator[None]:
    ids = iter(IDS)
    monkeypatch.setattr("my_agent_crew.store.artifacts.new_id", lambda: next(ids))
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def crew(deps_factory, store: Store) -> Callable[..., Runtime]:
    """A boss over a `worker` that holds the canvas tools under its own id, the two that
    carry files among them. The worker says what its script says, and answers through the
    echo provider when it has none."""

    def build(*script: Completion, max_steps: int = 12) -> Runtime:
        base = deps_factory(routes=ECHO)
        limit, root = DEFAULT_TOOL_OUTPUT_CHARS, base.profile.workspace
        canvas = [
            *build_artifact_tools(store, "worker", False, limit),
            *build_artifact_file_tools(store, "worker", False, limit, root, ()),
        ]
        routes = (Route("scripted", "m"),) if script else ECHO
        worker = deps_factory(script=script, extra_tools=canvas, routes=routes, max_steps=max_steps)
        agents = {
            "boss": agent(base, "boss", delegates=("worker",)),
            "worker": agent(worker, "worker"),
        }
        rt = Runtime(base.settings, store, agents, ActivityHub(store))
        rt.wire_delegation()
        return rt

    return build


def wants(name: str, **args: object) -> ToolCall:
    return ToolCall(f"w{next(_calls)}", name, args)


def creates(title: str, content: str = PLAN) -> ToolCall:
    return wants("artifact_create", title=title, kind="markdown", content=content)


def step(*calls: ToolCall) -> Completion:
    """One step of a scripted child that asks for `calls` and says nothing."""
    return completion(tool_calls=calls)


async def handed(
    rt: Runtime, task: str = "viết dàn ý", *, autonomous: bool = True
) -> tuple[ToolResult, Conversation, Conversation]:
    """Delegates `task` to the worker from a new conversation of the boss: the result, the
    conversation that asked and the child's."""
    parent = rt.store.create(agent_id="boss", autonomous=autonomous)
    result = await delegation_result(rt, parent.id, "call-1", task=task, agent="worker")
    child = rt.store.for_parent_call("call-1")
    assert child is not None
    return result, parent, child


async def test_the_canvases_the_child_wrote_stand_right_under_the_outcome(crew):
    """Each at the newest version the child wrote, in the order it first wrote them, then the
    blank line, then the answer. The tag is the one a canvas tool's own result opens with, and
    the whole line is the one the web card reads, so server, turn note and web share a form."""
    said = "Đã viết dàn ý 6 mục vào canvas."
    rt = crew(
        step(creates("Dàn ý pha cà phê phin"), creates("Nguồn tham khảo")),
        step(wants("artifact_rewrite", id=A, content=SWIM)),
        completion(said),
    )
    result, _, child = await handed(rt)

    _, outcome, *rest = result.output.split("\n")
    assert outcome == "outcome=done"
    assert rest == [
        f"[artifact {A} v2] Dàn ý pha cà phê phin",
        f"[artifact {B} v1] Nguồn tham khảo",
        "",
        said,
    ]
    for line, written in zip(rest[:2], rt.store.artifacts.written_in(child.id), strict=True):
        named = (written.id, str(written.version))
        assert TAG_RE.match(line).groups() == (*named, None)
        assert web_pattern("CANVAS").fullmatch(line).groups() == (*named, written.title)
    assert result.ok and result.reply == said


async def test_a_child_that_wrote_no_canvas_leaves_only_the_blank_line(crew):
    result, _, _ = await handed(crew(), "đếm tệp")

    assert result.output.split("\n")[1:] == ["outcome=done", "", "(echo) đếm tệp"]
    assert result.reply == "(echo) đếm tệp"


async def test_an_answer_that_opens_like_a_canvas_line_stays_below_the_blank_line(crew):
    """Only the runtime names canvases. What the child writes is its answer, tag or not, and
    the blank line above it is what lets the card tell the two apart."""
    said = f"[artifact {'c' * 12} v3] Canvas không có thật\nĐã xong."
    rt = crew(completion(said))
    result, _, child = await handed(rt)

    assert rt.store.artifacts.written_in(child.id) == []
    assert result.output.split("\n")[1:] == ["outcome=done", "", *said.split("\n")]
    assert result.reply == said


async def test_a_long_title_is_cut_like_any_field_quoted_in_a_result(crew):
    title = "tiêu đề " * 22 + "hết"
    assert len(title) > FIELD_CHARS
    result, _, _ = await handed(crew(step(creates(title)), completion("Xong.")))

    line = f"[artifact {A} v1] {title[:FIELD_CHARS]}…"
    assert result.output.split("\n")[2:] == [line, "", "Xong."]
    assert web_pattern("CANVAS").fullmatch(line).group(3) == f"{title[:FIELD_CHARS]}…"


async def test_canvases_past_the_twelfth_are_counted_in_the_first_line_of_the_body(crew):
    """The count is for the delegator and shows on the card as part of the result; the person
    is still handed the child's words alone."""
    said = "Đã viết 14 canvas."
    titles = [f"Mục {n}" for n in range(1, MAX_LISTED + 3)]
    result, _, _ = await handed(crew(step(*(creates(t) for t in titles)), completion(said)))

    lines = result.output.split("\n")
    named = zip(IDS, titles[:MAX_LISTED], strict=False)
    assert lines[2 : 2 + MAX_LISTED] == [f"[artifact {art} v1] {title}" for art, title in named]
    assert lines[2 + MAX_LISTED :] == ["", texts.DELEGATE_CANVAS_MORE.format(n=2), "", said]
    assert result.reply == said


async def test_a_canvas_deleted_while_the_parent_waited_is_not_named(crew, monkeypatch):
    rt = crew(step(creates("Bỏ"), creates("Giữ")), completion("Xong."))
    finished = rt.hub.wait_finished

    async def deleted_meanwhile(conv_id: str, timeout: float):
        run = await finished(conv_id, timeout)
        rt.store.artifacts.delete(A)
        return run

    monkeypatch.setattr(rt.hub, "wait_finished", deleted_meanwhile)
    result, _, _ = await handed(rt)

    assert result.output.split("\n")[2:] == [f"[artifact {B} v1] Giữ", "", "Xong."]


async def test_a_task_that_is_not_done_still_names_what_was_written(crew):
    """A canvas left half written is still something the person needs to know of."""
    said = "Mới viết được dàn ý.\nStatus: BLOCKED — cần bạn duyệt nguồn"
    result, _, _ = await handed(crew(step(creates("Dàn ý")), completion(said)))

    assert result.output.split("\n")[1:] == [
        "outcome=blocked reason=cần bạn duyệt nguồn",
        f"[artifact {A} v1] Dàn ý",
        "",
        *said.split("\n"),
    ]
    assert result.ok and result.reply is None


async def test_a_child_stopped_short_names_its_canvases_above_the_unfinished_note(crew):
    rt = crew(*(step(creates(f"Mục {n}")) for n in (1, 2, 3)), max_steps=3)
    result, _, child = await handed(rt)

    lines = result.output.split("\n")
    wrote = [f"[artifact {w.id} v1] {w.title}" for w in rt.store.artifacts.written_in(child.id)]
    assert f" status={HALTED} " in lines[0] and lines[1] == "outcome=failed reason=max_steps"
    assert wrote and wrote[0] == f"[artifact {A} v1] Mục 1"
    assert lines[2 : 3 + len(wrote)] == [*wrote, ""]
    unfinished = texts.DELEGATE_UNFINISHED.format(status=HALTED, reason="max_steps")
    assert lines[3 + len(wrote)] == unfinished
    assert result.reply is None


async def test_a_wait_that_runs_out_still_names_what_the_child_had_written(crew, monkeypatch):
    """As in any other result: the first twelve, and the count of the rest under the blank
    line. The child is still going, so what it writes after this the result does not name."""
    write = wants("workspace_write", path="x.txt", content="1")
    titles = [f"Mục {n}" for n in range(1, MAX_LISTED + 2)]
    rt = crew(step(*(creates(t) for t in titles)), step(write))
    real_wait = rt.hub.wait_finished

    async def runs_out(conv_id: str, timeout: float):
        await wait_until_paused(rt)
        return await real_wait(conv_id, 0.01)

    monkeypatch.setattr(rt.hub, "wait_finished", runs_out)
    result, _, child = await handed(rt, autonomous=False)

    lines = result.output.split("\n")
    assert not result.ok and result.reply is None
    assert web_pattern("HEADER").fullmatch(lines[0]).groups()[:2] == (child.id, AWAITING)
    named = zip(IDS, titles[:MAX_LISTED], strict=False)
    assert lines[1:] == [
        "outcome=failed reason=timeout",
        *(f"[artifact {art} v1] {title}" for art, title in named),
        "",
        texts.DELEGATE_CANVAS_MORE.format(n=1),
        "",
        texts.DELEGATE_TIMEOUT.format(conv_id=child.id),
    ]


async def test_carrying_a_canvas_to_or_from_a_file_unchanged_names_nothing(crew, store: Store):
    """An export and an import that finds file and canvas alike add no version, so the child
    wrote nothing; and a canvas it only carried is not shared with the conversation that
    asked."""
    kept = agents_canvas(store, "worker", PLAN)
    rt = crew(
        step(wants("artifact_import", id=kept, path=FILE)),
        step(wants("artifact_export", id=kept, path="out/plan.md")),
        completion("Đã chép ra tệp."),
    )
    workspace = rt.deps_for("worker").profile.workspace
    put(workspace, FILE, PLAN)
    result, parent, child = await handed(rt)

    assert (workspace / "out/plan.md").read_text(encoding="utf-8") == PLAN
    canvas = store.artifacts.get(kept)
    assert (canvas.head_version, canvas.source) == (1, f"workspace:worker/{FILE}")
    assert result.output.split("\n")[1:] == ["outcome=done", "", "Đã chép ra tệp."]
    assert store.artifact_links.get(child.id, kept) is not None
    assert store.artifact_links.get(parent.id, kept) is None


async def test_naming_a_canvas_to_the_master_is_not_the_master_having_read_it(crew, store: Store):
    """The canvas is shared with the conversation that asked, so the person's next message
    there carries one line naming it, once. The result told the master that the canvas is
    there, not what it holds: rewriting it stays refused until the master reads it."""
    task = '/tool artifact_create {"title": "Dàn ý", "kind": "markdown", "content": "# Dàn ý"}'
    result, parent, _ = await handed(crew(), task)

    assert result.output.split("\n")[2:4] == [f"[artifact {A} v1] Dàn ý", ""]
    assert say(store, parent) == framed(CANVAS_NOTE_NEW.format(title="Dàn ý", id=A, head=1))
    assert (seen(store, parent, A), noted(store, parent, A)) == (0, 1)
    assert say(store, parent) == ""
    turn(store, parent)
    rewrite = {"id": A, "content": "# Khác\n"}
    refused = await call(store, "artifact_rewrite", rewrite, agent_id="boss", is_master=True)
    assert refused.output == texts.TOOL_FAILED.format(error=ARTIFACT_REWRITE_UNSEEN.format(id=A))
    assert store.artifacts.get(A).head_version == 1


def test_a_conversation_nobody_wrote_a_canvas_in_has_no_line_and_no_count(store: Store):
    assert canvas_lines(store.artifacts, store.create().id) == ([], "")


@pytest.mark.parametrize("extra", [0, 1, 3])
def test_the_first_twelve_canvases_are_named_and_the_rest_counted(store: Store, extra: int):
    """The canvases a delegator has to tell the person about are the ones the child began
    with, so the first written are the ones named. Exactly twelve leaves nothing to count."""
    child = store.create()
    for n in range(MAX_LISTED + extra):
        store.artifacts.create(f"Mục {n}", "markdown", "worker", WORKER, child.id, PLAN)

    lines, more = canvas_lines(store.artifacts, child.id)

    assert lines == [f"[artifact {IDS[n]} v1] Mục {n}" for n in range(MAX_LISTED)]
    assert more == (texts.DELEGATE_CANVAS_MORE.format(n=extra) if extra else "")
    assert "\n" not in more


def test_the_count_of_the_rest_says_how_many_and_which_tool_lists_them(store: Store):
    """The delegator cannot name a canvas the result left out; it can list them, with a tool
    that is really in the toolbox under the name the sentence gives."""
    more = texts.DELEGATE_CANVAS_MORE.format(n=7)
    tools = {tool.name for tool in build_artifact_tools(store, "boss", True, 4000)}

    assert more.startswith("(+7 canvas")
    assert "artifact_list" in tools and "artifact_list" in more
    assert web_pattern("CANVAS").fullmatch(more) is None


def test_only_what_an_agent_wrote_in_that_conversation_is_named(store: Store):
    """At the newest version the agent wrote there, which a person's later save does not
    move; a canvas written elsewhere and a person's own are left out."""
    child, other = store.create(), store.create()
    store.artifacts.create("Chỗ khác", "markdown", "worker", WORKER, other.id, PLAN)
    persons_canvas(store, PLAN, child.id)
    mine = store.artifacts.create("Dàn ý", "markdown", "worker", WORKER, child.id, PLAN).id
    store.artifacts.write(mine, SWIM, WORKER, child.id)
    store.artifacts.write(mine, PLAN, USER, child.id)

    assert canvas_lines(store.artifacts, child.id) == ([f"[artifact {mine} v2] Dàn ý"], "")
