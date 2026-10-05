"""Which canvases a turn wrote, and the words the chat is told it in.

A chat shows no canvas: what an agent writes is read on the web. So the chat is told what a
turn wrote, and that is read from the results of the turn's own tools, never from its reply. A
write's result opens with the tag; a delegated task's result lists what the child wrote
between its second line and the blank line under it. The notice names only what the agent
still reaches, by the rule a canvas is sent to the chat by. When it goes out is in
`test_telegram_canvas_notice_sent.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.events import AssistantMessageEvent, DoneEvent, ToolResultEvent
from my_agent_crew.agent.turn_context import API, CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.artifacts.tag import TAG_RE, Tag, artifact_tag, parse_artifact_tag
from my_agent_crew.channels.telegram_canvas_notice import (
    WrittenCanvases,
    merged,
    notice_text,
    tags_of,
    written_by,
)
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.approvals import EXPIRED
from my_agent_crew.store.runs import DONE, RunRecord
from my_agent_crew.tools.ask_user import unanswered_result
from my_agent_crew.tools.delegate_outcome import result_text, timed_out
from tests.canvas_helpers import PLAN, SWIM, agents_canvas, call, persons_canvas, put, tagged, turn
from tests.conftest import collect
from tests.lapse_helpers import (
    ASK,
    ASK_WITH_DEFAULT,
    WRITE,
    answered,
    nobody_answered,
    refused,
    sent_again,
    waits_on,
)

A, B, C = "0123456789ab", "ba9876543210", "00ff00ff00ff"
WEB = "http://127.0.0.1:8765"
STAMP = "2026-10-01T03:00:00+00:00"
COVERED = texts.TRAJECTORY_REDACTED
HEADER = "conversation=c9 status=done spent=$0.0100 steps=2"


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def line(tag: Tag, title: str) -> str:
    return texts.TELEGRAM_CANVAS_LINE.format(title=title, version=tag.version)


def link(artifact_id: str, web_url: str = WEB) -> str:
    return texts.TELEGRAM_CANVAS_LINK_LINE.format(link=f"{web_url}/#/manage/canvas/{artifact_id}")


def began(store, conv_id: str, run_id: str = "r1") -> RunRecord:
    """A run that begins where the conversation stands now."""
    after = store.messages.max_seq(conv_id)
    run = RunRecord(run_id, "default", conv_id, "job:default/x", "t", DONE, STAMP, after_seq=after)
    store.runs.save(run)
    return run


def tool_said(store, conv_id: str, name: str, content: str, call_id: str = "c1") -> None:
    store.append(conv_id, Message(role="tool", content=content, tool_call_id=call_id, name=name))


@pytest.mark.parametrize("unchanged", [False, True])
def test_a_tag_reads_back_as_what_it_was_built_from(unchanged):
    built = artifact_tag(A, 12, unchanged)
    assert parse_artifact_tag(built) == Tag(A, 12, unchanged)
    assert parse_artifact_tag(f"{built} Dàn ý\nphần còn lại") == Tag(A, 12, unchanged)


def test_a_line_that_does_not_open_with_a_tag_reads_as_none():
    assert parse_artifact_tag(f"Canvas {artifact_tag(A, 1)}") is None
    assert parse_artifact_tag("[artifact xyz v1]") is None
    assert parse_artifact_tag("") is None
    assert Tag(A, 3) == Tag(A, 3, False)


def test_the_web_reads_a_tag_by_the_pattern_the_server_writes_it_to():
    """`web/src/lib/artifact-tag.ts` holds the pattern a second time. Changed on one side
    alone, the web would draw a write the chat never names, or the other way round."""
    source = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "artifact-tag.ts"
    found = re.search(r"^const TAG_RE = /(.+)/;$", source.read_text("utf-8"), re.MULTILINE)
    assert found is not None, "TAG_RE is no longer a one-line regex constant in artifact-tag.ts"
    assert found.group(1) == TAG_RE.pattern


async def test_each_tool_that_writes_a_canvas_names_the_version_it_left(store, tmp_path):
    turn(store)
    root = tmp_path / "ws"
    put(root, "notes/thuc-don.md", "# Thực đơn\nphở\n")
    made = await call(store, "artifact_create", {"title": "x", "kind": "markdown", "content": PLAN})
    art, _, _ = tagged(made)
    edit = {"id": art, "old": "chạy 5 km", "new": "chạy 8 km"}
    results = {
        "artifact_create": made,
        "artifact_edit": await call(store, "artifact_edit", edit),
        "artifact_rewrite": await call(store, "artifact_rewrite", {"id": art, "content": SWIM}),
        "artifact_import": await call(
            store, "artifact_import", {"path": "notes/thuc-don.md"}, root=root
        ),
    }
    named = {name: tags_of(name, result.output) for name, result in results.items()}
    other, _, _ = tagged(results["artifact_import"])
    assert named == {
        "artifact_create": [Tag(art, 1)],
        "artifact_edit": [Tag(art, 2)],
        "artifact_rewrite": [Tag(art, 3)],
        "artifact_import": [Tag(other, 1)],
    }


@pytest.mark.parametrize("name", ["artifact_read", "artifact_export", "artifact_list", "shell", ""])
def test_a_tool_that_writes_no_canvas_names_none_whatever_its_result_says(name):
    assert tags_of(name, f"{artifact_tag(A, 3)} Dàn ý") == []
    assert (
        tags_of(name, result_text(HEADER, "outcome=done", [f"{artifact_tag(A, 3)} x"], "", ""))
        == []
    )


async def test_a_write_that_was_refused_names_nothing(store):
    """A turn a platform relays through the API may not write a canvas, and what the tool
    answers opens with no tag: nothing was written, so nothing is named."""
    turn(store, source=API)
    refused = await call(
        store, "artifact_create", {"title": "x", "kind": "markdown", "content": PLAN}
    )
    assert not refused.ok and store.artifacts.list() == []
    assert tags_of("artifact_create", refused.output) == []
    assert tags_of("artifact_edit", "Không tìm thấy canvas 0123456789ab.") == []


async def test_a_write_that_changed_nothing_names_nothing(store):
    turn(store)
    made = await call(store, "artifact_create", {"title": "x", "kind": "markdown", "content": PLAN})
    art, _, _ = tagged(made)
    same = await call(store, "artifact_rewrite", {"id": art, "content": PLAN})
    assert tagged(same) == (art, 1, True)
    assert tags_of("artifact_rewrite", same.output) == []


def test_a_delegated_task_names_what_its_child_wrote_even_when_the_wait_ran_out():
    block = [f"{artifact_tag(A, 2)} Dàn ý", f"{artifact_tag(B, 1)} Số liệu"]
    done = result_text(HEADER, "outcome=done", block, "", "Xong.")
    assert tags_of("delegate", done) == [Tag(A, 2), Tag(B, 1)]
    late = timed_out("c9", None, block[:1], "")
    assert not late.ok and tags_of("delegate", late.output) == [Tag(A, 2)]
    assert tags_of("delegate", "Không có agent nào tên x.") == []


def test_a_canvas_written_twice_is_named_once_at_its_newest_version_where_it_first_stood():
    assert merged([Tag(A, 1), Tag(B, 1), Tag(A, 3), Tag(C, 4), Tag(A, 2)]) == [
        Tag(A, 3),
        Tag(B, 1),
        Tag(C, 4),
    ]
    assert merged([]) == []


def spoke(content: str) -> AssistantMessageEvent:
    return AssistantMessageEvent(1, content, [], "scripted", "m", 0.0)


async def test_a_live_turn_is_watched_without_changing_what_passes():
    stream = [
        ToolResultEvent("c1", "artifact_create", True, f"{artifact_tag(A, 1)} Đã tạo."),
        spoke("Đang sửa."),
        ToolResultEvent("c2", "artifact_edit", True, f"{artifact_tag(A, 2)} Đã sửa."),
        ToolResultEvent("c3", "artifact_read", True, f"{artifact_tag(B, 1)} nội dung"),
        ToolResultEvent("c4", "artifact_edit", False, "Không tìm thấy canvas."),
        ToolResultEvent("c5", "artifact_create", True, f"{artifact_tag(C, 1)} Đã tạo."),
        DoneEvent(0.0, 0),
    ]

    async def events():
        for event in stream:
            yield event

    seen = WrittenCanvases()
    assert seen.tags == []
    assert await collect(seen.watch(events())) == stream
    assert seen.tags == [Tag(A, 2), Tag(C, 1)]


async def test_a_live_turn_keeps_what_a_child_wrote_before_its_wait_ran_out():
    """That result is a failure, and the message it is stored as keeps no such mark: read
    live or read back from the run, a turn names the same canvases."""
    late = timed_out("c9", None, [f"{artifact_tag(A, 2)} Dàn ý"], "")

    async def events():
        yield ToolResultEvent("d1", "delegate", late.ok, late.output)
        yield DoneEvent(0.0, 0)

    seen = WrittenCanvases()
    await collect(seen.watch(events()))
    assert not late.ok and seen.tags == [Tag(A, 2)]


async def test_a_turn_that_breaks_is_still_broken_and_keeps_what_it_wrote_by_then():
    async def events():
        yield ToolResultEvent("c1", "artifact_create", True, f"{artifact_tag(A, 1)} Đã tạo.")
        raise RuntimeError("model down")

    seen = WrittenCanvases()
    with pytest.raises(RuntimeError, match="model down"):
        await collect(seen.watch(events()))
    assert seen.tags == [Tag(A, 1)]


def test_a_run_with_no_lapsed_approval_names_everything_it_wrote(store):
    conv = store.create()
    store.append(conv.id, Message(role="user", content="lập kế hoạch"))
    run = began(store, conv.id)
    childs = result_text(HEADER, "outcome=done", [f"{artifact_tag(B, 2)} Số liệu"], "", "Xong.")
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.")
    tool_said(store, conv.id, "delegate", childs)
    tool_said(store, conv.id, "artifact_edit", f"{artifact_tag(A, 2)} Đã sửa.")
    tool_said(store, conv.id, "artifact_read", f"{artifact_tag(C, 1)} nội dung")
    store.append(conv.id, Message(role="assistant", content=f"{artifact_tag(C, 5)} tôi đã ghi"))
    assert written_by(store, conv.id, run) == [Tag(A, 2), Tag(B, 2)]


def test_a_run_whose_approval_lapsed_names_only_what_it_wrote_after_the_last_one(store):
    """What the run wrote before it stopped was named when it stopped. The result closing a
    request nobody answered marks where that reading ended."""
    conv = store.create()
    run = began(store, conv.id)
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.")
    nobody_answered(store, conv.id, waits_on(store, conv.id, WRITE))
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(B, 1)} Đã tạo.")
    assert written_by(store, conv.id, run) == [Tag(B, 1)]
    nobody_answered(store, conv.id, waits_on(store, conv.id, ToolCall("s1", "shell", {})))
    assert written_by(store, conv.id, run) == []
    tool_said(store, conv.id, "artifact_edit", f"{artifact_tag(A, 2)} Đã sửa.")
    again = ToolCall("w2", "workspace_write", {"path": "out.txt", "content": "ok"})
    refused(store, conv.id, waits_on(store, conv.id, again))  # refused, not lapsed
    tool_said(store, conv.id, "artifact_edit", f"{artifact_tag(B, 2)} Đã sửa.")
    assert written_by(store, conv.id, run) == [Tag(A, 2), Tag(B, 2)]


@pytest.mark.parametrize("ask", [ASK, ASK_WITH_DEFAULT])
def test_a_question_nobody_answered_marks_the_run_like_an_approval_that_lapsed(store, ask):
    """The turn goes on with the question's default, or with none, and is told so in other
    words than a tool refused for want of an answer; what it wrote before it asked was named
    when it stopped all the same."""
    conv = store.create()
    run = began(store, conv.id)
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.")
    nobody_answered(store, conv.id, waits_on(store, conv.id, ask))
    assert written_by(store, conv.id, run) == []
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(B, 1)} Đã tạo.")
    assert written_by(store, conv.id, run) == [Tag(B, 1)]


def test_only_a_request_nobody_answered_is_a_mark_whatever_a_result_says(store):
    """A mark is found by the request its call opened, never by its words. A tool may print
    the sentence a lapse is told in, or answer with nothing else; a person may answer the
    question or refuse the tool; and a call id may come round again under another tool."""
    conv = store.create()
    run = began(store, conv.id)
    silence = unanswered_result(ASK.arguments)
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.")
    tool_said(store, conv.id, "shell", f"$ tail agent.log\n{texts.EXPIRED_TOOL}\n{silence}")
    tool_said(store, conv.id, "shell", texts.EXPIRED_TOOL, "c2")
    tool_said(store, conv.id, "ask_user", silence, "c3")
    answered(store, conv.id, waits_on(store, conv.id, ASK), "bơi")
    refused(store, conv.id, waits_on(store, conv.id, WRITE))
    assert written_by(store, conv.id, run) == [Tag(A, 1)]
    nobody_answered(store, conv.id, waits_on(store, conv.id, ToolCall("s1", "shell", {})))
    assert written_by(store, conv.id, run) == []
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(B, 1)} Đã tạo.", "s1")
    tool_said(store, conv.id, "artifact_edit", f"{artifact_tag(A, 2)} Đã sửa.")
    assert written_by(store, conv.id, run) == [Tag(B, 1), Tag(A, 2)]


@pytest.mark.parametrize("asks_again", [True, False])
@pytest.mark.parametrize(
    ("call", "result"),
    [
        (WRITE, "ok"),
        (WRITE, texts.EXPIRED_TOOL),
        (WRITE, texts.APPROVAL_CALL_MISMATCH),
        (ASK, unanswered_result(ASK.arguments)),
    ],
    ids=["ran", "refused again", "id taken", "asked again"],
)
def test_a_request_is_closed_once_whatever_comes_under_its_call_id_afterwards(
    store, call, result, asks_again
):
    """A model may send a call id it has used before, and the loop answers the new call under
    it: the tool runs, it is refused as the first was, it is told the id is taken, or the
    question is answered once more with what nobody said. None of those is the request running
    out a second time, with the model's call stored in front of the result or without, so
    what the run wrote since the lapse is still to be named. A message's id is the store's
    own, not its place in the conversation: an earlier conversation keeps the two apart."""
    elsewhere = store.create()
    store.append(elsewhere.id, Message(role="user", content="chuyện khác"))
    conv = store.create()
    run = began(store, conv.id)
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.")
    nobody_answered(store, conv.id, waits_on(store, conv.id, call))
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(B, 1)} Đã tạo.")
    assert written_by(store, conv.id, run) == [Tag(B, 1)]
    if asks_again:
        sent_again(store, conv.id, call, result)
    else:
        tool_said(store, conv.id, call.name, result, call.id)
    assert written_by(store, conv.id, run) == [Tag(B, 1)]
    tool_said(store, conv.id, "artifact_edit", f"{artifact_tag(A, 2)} Đã sửa.")
    assert written_by(store, conv.id, run) == [Tag(B, 1), Tag(A, 2)]


def test_a_result_under_another_tools_name_closes_no_request(store):
    """A request is its call: the message that asked, the id it asked under and the tool it
    asked for. The loop stores no result under another tool's name; one that stands first
    under the id of a lapsed call all the same is read as that tool's own."""
    conv = store.create()
    run = began(store, conv.id)
    request = waits_on(store, conv.id, ToolCall("s1", "shell", {}))
    store.approvals.resolve(request.id, approve=False, status=EXPIRED)
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.", "s1")
    assert written_by(store, conv.id, run) == [Tag(A, 1)]


@pytest.mark.parametrize("place", [0, 1, 2], ids=["first", "between", "last"])
def test_a_request_is_closed_by_its_own_call_wherever_that_stands_in_the_message(store, place):
    """A model may ask for several tools in one message, and the loop answers them in the
    order asked: those in front of the call that waits ran before the turn stopped, those
    behind it once the request had run out. The waiting call's result is where the reading
    ended, wherever among them it stands."""
    conv = store.create()
    run = began(store, conv.id)
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(C, 1)} Đã tạo.", "c0")
    writes = [
        (ToolCall("a1", "artifact_create", {}), A),
        (ToolCall("b1", "artifact_create", {}), B),
    ]
    before, after = writes[:place], writes[place:]

    def ran(some: list[tuple[ToolCall, str]]) -> list[Tag]:
        for asked, canvas in some:
            tool_said(store, conv.id, asked.name, f"{artifact_tag(canvas, 1)} Đã tạo.", asked.id)
        return [Tag(canvas, 1) for _, canvas in some]

    every = [*(asked for asked, _ in before), WRITE, *(asked for asked, _ in after)]
    request = waits_on(store, conv.id, WRITE, every)
    named_at_the_stop = ran(before)
    assert written_by(store, conv.id, run) == [Tag(C, 1), *named_at_the_stop]
    store.approvals.resolve(request.id, approve=False, status=EXPIRED)
    tool_said(store, conv.id, WRITE.name, texts.EXPIRED_TOOL, WRITE.id)
    assert written_by(store, conv.id, run) == []
    still_to_name = ran(after)
    assert written_by(store, conv.id, run) == still_to_name


def test_a_person_who_quotes_the_lapsed_sentence_marks_nothing(store):
    conv = store.create()
    run = began(store, conv.id)
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.")
    store.append(conv.id, Message(role="user", content=texts.EXPIRED_TOOL))
    store.append(conv.id, Message(role="assistant", content=texts.EXPIRED_TOOL))
    assert written_by(store, conv.id, run) == [Tag(A, 1)]


def test_what_another_run_of_the_conversation_wrote_is_not_this_runs(store):
    conv = store.create()
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(C, 1)} Đã tạo.")
    first = began(store, conv.id, "r1")
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.")
    second = began(store, conv.id, "r2")
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(B, 1)} Đã tạo.")
    assert written_by(store, conv.id, first) == [Tag(A, 1)]
    assert written_by(store, conv.id, second) == [Tag(B, 1)]


def test_no_run_and_a_run_that_does_not_know_where_it_began_name_nothing(store):
    conv = store.create()
    tool_said(store, conv.id, "artifact_create", f"{artifact_tag(A, 1)} Đã tạo.")
    old = RunRecord("r0", "default", conv.id, "job:default/x", "t", DONE, STAMP)
    store.runs.save(old)
    assert written_by(store, conv.id, None) == []
    assert written_by(store, conv.id, old) == []


def test_the_notice_names_each_canvas_with_the_version_written_and_its_page(deps_factory):
    deps = deps_factory(web_url=WEB)
    store = deps.store
    plan, notes = agents_canvas(store, "coach"), persons_canvas(store, PLAN)
    store.artifacts.write(plan, SWIM, "agent:coach", "")
    store.artifacts.write(plan, PLAN, "agent:coach", "")
    tags = [Tag(plan, 2), Tag(notes, 1)]
    assert notice_text(deps, tags, None) == "\n".join(
        [
            texts.TELEGRAM_CANVAS_HEADER,
            line(tags[0], "Kế hoạch"),
            link(plan),
            line(tags[1], "Ghi chú của người"),
            link(notes),
        ]
    )
    assert line(tags[0], "Kế hoạch") == '• "Kế hoạch" v2'  # the version written, in plain quotes


def test_without_an_address_the_notice_says_where_to_look(deps_factory):
    deps = deps_factory()
    plan = agents_canvas(deps.store, "coach")
    assert notice_text(deps, [Tag(plan, 1)], None) == "\n".join(
        [texts.TELEGRAM_CANVAS_HEADER, '• "Kế hoạch" v1', texts.TELEGRAM_CANVAS_OPEN_WEB]
    )


def test_the_notice_names_only_what_the_agent_still_reaches(deps_factory, tmp_path):
    """The rule a canvas is sent to the chat by. The master reaches every canvas that is
    there; anyone else its own, and what its conversation holds."""
    master = deps_factory(web_url=WEB)
    coach = deps_factory(web_url=WEB, home=tmp_path / "coach-home")
    coach.profile = replace(coach.agent, id="coach", name="HLV")
    store = master.store
    conv, other = store.create(agent_id="coach"), store.create(agent_id="coach")
    mine, theirs = agents_canvas(store, "coach"), agents_canvas(store, "ledger")
    linked, gone = persons_canvas(store, PLAN, conv.id), agents_canvas(store, "coach")
    store.artifacts.delete(gone)
    tags = [Tag(gone, 1), Tag(theirs, 1), Tag(linked, 1), Tag(mine, 1)]

    def named(deps, conv_id) -> list[str]:
        return [row for row in notice_text(deps, tags, conv_id).split("\n") if WEB in row]

    assert named(coach, conv.id) == [link(linked), link(mine)]
    assert named(coach, other.id) == named(coach, None) == [link(mine)]
    assert named(master, None) == [link(theirs), link(linked), link(mine)]
    assert notice_text(coach, tags[:2], conv.id) == ""
    assert notice_text(master, [Tag(gone, 1), Tag(A, 1)], None) == ""
    assert notice_text(master, [], None) == ""


@pytest.mark.parametrize(("count", "more"), [(10, 0), (11, 1), (12, 2)])
def test_a_long_list_is_cut_at_ten_and_the_rest_counted(deps_factory, count, more):
    deps = deps_factory(web_url=WEB)
    made = [agents_canvas(deps.store, "coach") for _ in range(count)]
    gone = agents_canvas(deps.store, "coach")
    deps.store.artifacts.delete(gone)  # one that is not there is not counted either
    rows = notice_text(deps, [Tag(gone, 1), *(Tag(art, 1) for art in made)], None).split("\n")
    assert [row for row in rows if WEB in row] == [link(art) for art in made[:10]]
    tail = [texts.TELEGRAM_CANVAS_MORE.format(n=more)] if more else []
    assert rows[21:] == tail and len(rows) == 21 + len(tail)


def test_a_canvas_renamed_since_is_named_by_its_new_title(deps_factory):
    deps = deps_factory(web_url=WEB)
    plan = agents_canvas(deps.store, "coach")
    deps.store.artifacts.rename(plan, "Kế hoạch tuần 40")
    assert '• "Kế hoạch tuần 40" v1' in notice_text(deps, [Tag(plan, 1)], None).split("\n")


def test_a_secret_in_a_title_is_covered(deps_factory, monkeypatch):
    monkeypatch.setenv("CANVAS_TEST_PASSWORD", "hunter2-hunter2")
    deps = deps_factory()
    art = deps.store.artifacts.create(
        "Khoá hunter2-hunter2 của tôi", "markdown", "coach", "agent:coach", "", PLAN
    ).id
    rows = notice_text(deps, [Tag(art, 1)], None).split("\n")
    assert rows[1] == f'• "Khoá {COVERED} của tôi" v1'
