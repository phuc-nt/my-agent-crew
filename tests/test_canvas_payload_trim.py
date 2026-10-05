"""The document text an earlier turn sent to a canvas stays out of the prompt: a create's or a
rewrite's `content` and an edit's `old` and `new` become a note of where that text went, or
that it went nowhere. The turn that wrote it keeps every word to its end, also after a steer,
a child's wrap-up note or a pause for approval, and the store keeps every call as made."""

from __future__ import annotations

from pathlib import Path

from my_agent_crew.agent.context_trim import MIN_TRIM_CHARS
from my_agent_crew.agent.events import ApprovalRequiredEvent, DoneEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.payload_trim import CANVAS_PAYLOADS, trim_canvas_payloads, turn_boundary
from my_agent_crew.agent.turn_context import API, CHAT
from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.config import DEFAULT_TOOL_OUTPUT_CHARS
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.db import Store
from my_agent_crew.store.runs import DONE, RUNNING, RunRecord
from my_agent_crew.store.stamps import new_id, now_iso
from my_agent_crew.texts import DELEGATE_WRAP_UP
from my_agent_crew.texts_canvas import (
    CANVAS_PAYLOAD_CUT_OFF,
    CANVAS_PAYLOAD_FAILED,
    CANVAS_PAYLOAD_SAVED,
)
from my_agent_crew.tools.artifact import build_artifact_tools
from my_agent_crew.tools.artifact_files import build_artifact_file_tools
from my_agent_crew.tools.registry import Tool
from tests.canvas_helpers import ZONE, lines_text
from tests.conftest import collect
from tests.queue_helpers import while_the_tool_runs

ART = "0123456789ab"
DOC = "# Kế hoạch tuần\n" + lines_text(12)
CREATE = ToolCall(
    "w1", "artifact_create", {"title": "Kế hoạch", "kind": "markdown", "content": DOC}
)
SLOW = ToolCall("c1", "slow", {})
GUARDED = ToolCall("g1", "guarded", {})


def canvas_tools(store: Store, root: Path | None = None) -> list[Tool]:
    """The canvas tools; over a workspace `root`, also the two that carry files, since an
    export writes a real file."""
    limit = DEFAULT_TOOL_OUTPUT_CHARS
    tools = build_artifact_tools(store, DEFAULT_AGENT_ID, False, limit, ZONE)
    if root is not None:
        tools += build_artifact_file_tools(store, DEFAULT_AGENT_ID, False, limit, root, ())
    return tools


def sent_calls(request) -> dict[str, ToolCall]:
    """The tool calls a request to the model carried, by id."""
    return {call.id: call for message in request.messages for call in message.tool_calls}


def saved(text: str, version: int, art: str = ART) -> str:
    return CANVAS_PAYLOAD_SAVED.format(chars=len(text), id=art, version=version)


async def test_a_steer_mid_turn_leaves_the_document_the_turn_wrote_whole(rigs, store: Store):
    """The steer is a person's message after the create, yet the same turn still reads on."""
    script = [completion(tool_calls=[CREATE, SLOW]), completion("đã tạo")]
    rig = rigs(script, extra_tools=canvas_tools(store))
    await while_the_tool_runs(rig, "/steer thêm mục ngân sách")
    second = rig.provider.requests[1]
    assert second.messages[-1].content == "thêm mục ngân sách"
    assert sent_calls(second)["w1"] == CREATE


async def test_a_child_told_to_conclude_still_sees_the_document_it_wrote(
    deps_factory, store: Store
):
    """The wrap-up note comes after the create, and the report is written from that text."""
    listing = ToolCall("l1", "artifact_list", {})
    script = [
        completion(tool_calls=[CREATE]),
        completion(tool_calls=[listing]),
        completion("Báo cáo nằm trong canvas."),
    ]
    deps = deps_factory(script=script, extra_tools=canvas_tools(store), max_steps=4)
    root = store.create()
    child = store.create(parent_call_id="call-1", root_id=root.id, root_source=CHAT)
    turn = run_turn(deps, child.id, "viết báo cáo", source=f"delegate:{root.id}", depth=1)
    events = await collect(turn)
    assert isinstance(events[-1], DoneEvent)
    last = deps.chain.providers["scripted"].requests[-1]
    assert last.messages[-1].content == DELEGATE_WRAP_UP
    assert sent_calls(last)["w1"] == CREATE


async def test_an_earlier_turns_frame_and_edits_leave_notes_of_where_their_text_went(
    deps_factory, store: Store, monkeypatch
):
    """Each note names the version its write made; ids, titles, kinds and a short `old` stay
    as they were, and the store still holds every word."""
    monkeypatch.setattr("my_agent_crew.store.artifacts.new_id", lambda: ART)
    body, part = lines_text(8), lines_text(10, width=30)
    frame = {"title": "Kế hoạch", "kind": "markdown", "content": f"# Kế hoạch\n{body}\n<!-- 2 -->"}
    create = ToolCall("w1", "artifact_create", frame)
    edit = ToolCall("w2", "artifact_edit", {"id": ART, "old": body, "new": body.upper()})
    fill = ToolCall(
        "w3", "artifact_edit", {"id": ART, "old": "<!-- 2 -->", "new": part, "title": "Tuần"}
    )
    script = [
        completion(tool_calls=[create]),
        completion(tool_calls=[edit]),
        completion(tool_calls=[fill]),
        completion("Đã điền kế hoạch."),
        completion("Không có gì."),
    ]
    deps = deps_factory(script=script, extra_tools=canvas_tools(store))
    conv = store.create()
    await collect(run_turn(deps, conv.id, "lập kế hoạch tuần"))
    assert store.artifacts.head(ART).version == 3
    await collect(run_turn(deps, conv.id, "cảm ơn"))
    calls = sent_calls(deps.chain.providers["scripted"].requests[-1])
    assert calls["w1"].arguments == {**frame, "content": saved(frame["content"], 1)}
    assert calls["w2"].arguments == {"id": ART, "old": saved(body, 2), "new": saved(body, 2)}
    assert calls["w3"].arguments == {**fill.arguments, "new": saved(part, 3)}
    stored = {c.id: c for m in store.history(conv.id) for c in m.message.tool_calls}
    assert stored == {"w1": create, "w2": edit, "w3": fill}


async def test_an_earlier_write_that_failed_leaves_a_note_that_nothing_was_saved(
    deps_factory, store: Store
):
    script = [completion(tool_calls=[CREATE]), completion("Gửi thẳng ở đây."), completion("Ừ.")]
    deps = deps_factory(script=script, extra_tools=canvas_tools(store))
    conv = store.create()
    await collect(run_turn(deps, conv.id, "lập kế hoạch tuần", source=API))
    await collect(run_turn(deps, conv.id, "được", source=API))
    calls = sent_calls(deps.chain.providers["scripted"].requests[-1])
    failed = CANVAS_PAYLOAD_FAILED.format(chars=len(DOC))
    assert calls["w1"].arguments == {**CREATE.arguments, "content": failed}
    assert store.artifacts.list(limit=10) == []


async def test_a_write_cut_off_mid_call_leaves_a_note_to_look_before_writing_again(
    deps_factory, store: Store
):
    """The earlier turn stopped between the call and its result, so the call is the last
    message before this turn. Whether its text reached the canvas is unknown."""
    deps = deps_factory(script=[completion("Để tôi xem lại.")], extra_tools=canvas_tools(store))
    conv = store.create()
    _append(
        store,
        conv.id,
        Message(role="user", content="lập kế hoạch tuần"),
        Message(role="assistant", tool_calls=(CREATE,)),
    )
    await collect(run_turn(deps, conv.id, "sao rồi?"))
    calls = sent_calls(deps.chain.providers["scripted"].requests[-1])
    cut_off = CANVAS_PAYLOAD_CUT_OFF.format(chars=len(DOC))
    assert calls["w1"].arguments == {**CREATE.arguments, "content": cut_off}


async def test_a_turn_resumed_after_an_approval_keeps_the_document_it_wrote_before(
    rigs, store: Store
):
    """The resumed turn goes on from the run that paused; only the turn after it trims."""
    script = [
        completion(tool_calls=[CREATE, GUARDED]),
        completion("đã tạo và chạy"),
        completion("không có gì"),
    ]
    rig = rigs(script, extra_tools=canvas_tools(store))
    *_, pause = await collect(rig.inbound.stream(rig.conv.id, "tạo rồi chạy"))
    assert isinstance(pause, ApprovalRequiredEvent)
    events = await collect(rig.inbound.decide(rig.conv.id, pause.approval_id, True))
    assert isinstance(events[-1], DoneEvent)
    assert sent_calls(rig.provider.requests[1])["w1"] == CREATE
    await collect(rig.inbound.stream(rig.conv.id, "cảm ơn"))
    [canvas] = store.artifacts.list(limit=10)
    content = saved(DOC, 1, canvas.id)
    assert sent_calls(rig.provider.requests[2])["w1"].arguments["content"] == content


def _append(store: Store, conv_id: str, *messages: Message) -> None:
    for message in messages:
        store.append(conv_id, message)


def test_a_write_with_no_result_and_every_other_message_pass_on_as_they_are(store: Store):
    """Only a long text whose call has a known result is trimmed; any message left unchanged
    is the very object the history held. A stray result and a `content` that is not text
    break nothing: a crash here would break every later turn of the conversation."""
    conv = store.create()
    short = ToolCall("w2", "artifact_create", {"title": "Ngắn", "kind": "markdown", "content": "a"})
    odd = ToolCall("w4", "artifact_create", {"title": "Lạ", "kind": "markdown", "content": 12345})
    rewrite = ToolCall("w3", "artifact_rewrite", {"id": ART, "content": DOC})
    _append(
        store,
        conv.id,
        Message(role="user", content="tạo hai bản"),
        Message(role="tool", content="kết quả lạc", tool_call_id="w9"),
        Message(role="assistant", tool_calls=(CREATE, short, odd)),
        Message(role="tool", content=f"[artifact {ART} v1]\nĐã tạo.", tool_call_id="w2"),
        Message(role="tool", content="Công cụ lỗi: content phải là chữ.", tool_call_id="w4"),
        Message(role="assistant", tool_calls=(rewrite,)),
        Message(role="tool", content=f"[artifact {ART} v2]\nĐã viết lại.", tool_call_id="w3"),
        Message(role="assistant", content="xong"),
        Message(role="user", content="tiếp"),
    )
    history = store.history(conv.id)
    trimmed = trim_canvas_payloads(history, history[-2].seq)
    unchanged = [index for index in range(len(history)) if index != 5]
    assert all(trimmed[index] is history[index].message for index in unchanged)
    [call] = trimmed[5].tool_calls
    assert call.arguments == {"id": ART, "content": saved(DOC, 2)}
    untouched = trim_canvas_payloads(history, None)
    assert all(new is old.message for new, old in zip(untouched, history, strict=True))


def test_the_last_message_before_the_turn_is_the_earlier_turns_and_the_next_is_this_ones(
    store: Store,
):
    """`turn_start` is the last message written before the turn began: a write made in it is
    trimmed, one made in the message after it is the turn's own and stays whole."""
    conv = store.create()
    _append(
        store,
        conv.id,
        Message(role="user", content="tạo"),
        Message(role="assistant", tool_calls=(CREATE,)),
        Message(role="tool", content=f"[artifact {ART} v1]\nĐã tạo.", tool_call_id="w1"),
    )
    history = store.history(conv.id)
    made_at = history[1].seq
    [own] = trim_canvas_payloads(history, made_at - 1)[1].tool_calls
    [earlier] = trim_canvas_payloads(history, made_at)[1].tool_calls
    assert (own, earlier.arguments["content"]) == (CREATE, saved(DOC, 1))


def test_a_reused_call_id_is_paired_with_the_result_that_follows_it(store: Store):
    """The first create failed and the second, under the same id, saved: each note says so."""
    conv = store.create()
    _append(
        store,
        conv.id,
        Message(role="user", content="tạo"),
        Message(role="assistant", tool_calls=(CREATE,)),
        Message(role="tool", content="Công cụ lỗi: không ghi được.", tool_call_id="w1"),
        Message(role="assistant", tool_calls=(CREATE,)),
        Message(role="tool", content=f"[artifact {ART} v1]\nĐã tạo.", tool_call_id="w1"),
        Message(role="assistant", content="xong"),
    )
    history = store.history(conv.id)
    trimmed = trim_canvas_payloads(history, history[-1].seq)
    contents = [trimmed[index].tool_calls[0].arguments["content"] for index in (1, 3)]
    assert contents == [CANVAS_PAYLOAD_FAILED.format(chars=len(DOC)), saved(DOC, 1)]


def test_a_call_this_turn_made_under_an_earlier_id_takes_none_of_its_result(store: Store):
    """An earlier create left without a result stays whole when this turn reuses its id."""
    conv = store.create()
    listing = ToolCall("w1", "artifact_list", {})
    _append(
        store,
        conv.id,
        Message(role="user", content="tạo"),
        Message(role="assistant", tool_calls=(CREATE,)),
        Message(role="user", content="thôi, liệt kê"),
        Message(role="assistant", tool_calls=(listing,)),
        Message(
            role="tool",
            content=f"[artifact {ART} v1]\nkhông phải kết quả của create",
            tool_call_id="w1",
        ),
    )
    history = store.history(conv.id)
    trimmed = trim_canvas_payloads(history, history[1].seq)
    assert trimmed[1] is history[1].message


def _run(store: Store, conv_id: str, status: str, after_seq: int | None) -> RunRecord:
    run = RunRecord(new_id(), DEFAULT_AGENT_ID, conv_id, CHAT, "", status, now_iso())
    run.after_seq = after_seq  # None: a run saved before runs recorded where they began
    store.runs.save(run)
    return run


def test_a_turn_starts_where_its_running_run_began_or_else_after_the_last_message(store: Store):
    conv, other = store.create(), store.create()
    _append(store, conv.id, *(Message(role="user", content=str(n)) for n in range(3)))
    last = store.history(conv.id)[-1].seq
    assert turn_boundary(store, conv.id) == last
    _run(store, other.id, RUNNING, 0)
    assert turn_boundary(store, conv.id) == last
    run = _run(store, conv.id, RUNNING, 1)
    assert turn_boundary(store, conv.id) == 1
    run.status = DONE
    store.runs.save(run)
    assert turn_boundary(store, conv.id) == last
    _run(store, conv.id, RUNNING, None)
    assert turn_boundary(store, conv.id) == last


def test_a_file_carried_in_or_out_by_an_earlier_turn_passes_on_as_the_call_was_made(store: Store):
    """Neither call holds document text, so nothing in it stands for a note: a path or a
    title, however long, is what the model must read back to know which file it was."""
    conv = store.create()
    path = "notes/" + "a" * (MIN_TRIM_CHARS + 1) + ".md"
    taking = ToolCall("f1", "artifact_import", {"path": path, "title": "T" * (MIN_TRIM_CHARS + 1)})
    giving = ToolCall("f2", "artifact_export", {"id": ART, "path": path})
    _append(
        store,
        conv.id,
        Message(role="user", content="đưa tệp vào canvas rồi xuất ra"),
        Message(role="assistant", tool_calls=(taking, giving)),
        Message(role="tool", content=f"[artifact {ART} v1]\nĐã nhập.", tool_call_id="f1"),
        Message(role="tool", content="Đã xuất.", tool_call_id="f2"),
        Message(role="assistant", content="xong"),
    )
    history = store.history(conv.id)
    trimmed = trim_canvas_payloads(history, history[-1].seq)
    assert all(new is old.message for new, old in zip(trimmed, history, strict=True))
    assert trimmed[1].tool_calls == (taking, giving)


def test_every_canvas_tool_argument_that_carries_document_text_is_trimmed(
    store: Store, tmp_path: Path
):
    """A canvas tool added later with a `content`, `old` or `new` is trimmed too, or fails
    here; every argument trimmed is text in that tool's schema."""
    tools = canvas_tools(store, tmp_path)
    assert len(tools) == 7
    for tool in tools:
        documents = {
            name
            for name, schema in tool.parameters["properties"].items()
            if name in {"content", "old", "new"} and schema["type"] == "string"
        }
        assert documents == set(CANVAS_PAYLOADS.get(tool.name, ())), tool.name
    assert set(CANVAS_PAYLOADS) <= {tool.name for tool in tools}


def test_a_note_is_always_shorter_than_the_text_it_stands_for():
    notes = [
        CANVAS_PAYLOAD_SAVED.format(chars=10**9, id="f" * 12, version=10**6),
        CANVAS_PAYLOAD_FAILED.format(chars=10**9),
        CANVAS_PAYLOAD_CUT_OFF.format(chars=10**9),
    ]
    assert max(len(note) for note in notes) < MIN_TRIM_CHARS
