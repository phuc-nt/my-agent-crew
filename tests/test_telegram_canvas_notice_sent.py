"""When the chat is told which canvases a turn wrote.

The list goes out after the turn's words and the files they attach, and before the line saying
a run was cut short. A turn that only wrote canvases is answered by the list, in place of the
sentence for a turn with nothing to say. It is said as it stands and never read for attachment
lines, so a canvas titled like one attaches nothing, and a list that cannot be sent costs the
turn one line. What the list says is in `test_telegram_canvas_notice.py`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.agent.events import AssistantMessageEvent, DoneEvent, ToolResultEvent
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.artifacts.tag import Tag, artifact_tag
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.store.runs import AWAITING, DONE, HALTED, RunRecord
from my_agent_crew.tools.delegate_outcome import result_text
from my_agent_crew.tools.registry import Tool, ToolResult
from tests.canvas_helpers import PLAN, persons_canvas
from tests.lapse_helpers import ASK, WRITE, nobody_answered, waits_on
from tests.queue_helpers import until
from tests.telegram_fake import message, poll_each
from tests.test_scheduler import with_schedules

STAMP = "2026-10-01T03:00:00+00:00"
OUT_OF_STEPS = texts.HALT_REASONS["max_steps"]


def canvas(store, title: str, agent_id: str = "coach") -> str:
    return store.artifacts.create(title, "markdown", agent_id, f"agent:{agent_id}", "", PLAN).id


def listed(*written: tuple[str, int], prefix: str = "") -> str:
    """The message naming canvases by title and version, as it reads when the web has no
    address; under `prefix` when a crew member's sender says it."""
    rows = [texts.TELEGRAM_CANVAS_LINE.format(title=title, version=v) for title, v in written]
    said = "\n".join([texts.TELEGRAM_CANVAS_HEADER, *rows, texts.TELEGRAM_CANVAS_OPEN_WEB])
    return f"{prefix}\n{said}" if prefix else said


def asked(store, agent_id: str = "default"):
    """A conversation of the agent, as far as the person's message."""
    conv = store.create(agent_id=agent_id)
    store.append(conv.id, Message(role="user", content="lập kế hoạch"))
    return conv


def began(store, conv_id: str, status: str = DONE, run_id: str = "r1", **more) -> RunRecord:
    """A run that begins where the conversation stands now."""
    agent_id, after = store.get(conv_id).agent_id, store.messages.max_seq(conv_id)
    run = RunRecord(
        run_id, agent_id, conv_id, "job:default/x", "t", status, STAMP, after_seq=after, **more
    )
    store.runs.save(run)
    return run


def wrote(store, conv_id: str, art: str, version: int = 1) -> None:
    """What a tool of the turn answered when it left `art` at `version`."""
    content = f"{artifact_tag(art, version)} Đã ghi."
    stored = Message(role="tool", content=content, tool_call_id="c1", name="artifact_edit")
    store.append(conv_id, stored)


def said(store, conv_id: str, content: str) -> None:
    store.append(conv_id, Message(role="assistant", content=content))


def result(art: str, version: int = 1) -> ToolResultEvent:
    return ToolResultEvent("c1", "artifact_edit", True, f"{artifact_tag(art, version)} Đã ghi.")


def spoke(content: str) -> AssistantMessageEvent:
    return AssistantMessageEvent(1, content, [], "scripted", "m", 0.0)


async def stream(*events, fails: Exception | None = None):
    """A turn's events, built by hand; one that `fails` breaks after the last of them."""
    for event in events:
        yield event
    if fails is not None:
        raise fails


def messages_and_files(fake) -> list[str]:
    return [call for call in fake.calls if call != "sendChatAction"]


def refuse(fake, monkeypatch, *openings: str) -> None:
    """Telegram refuses every message that opens with one of `openings`."""
    answer = fake.answer

    def picky(request: httpx.Request, method: str) -> httpx.Response:
        if method == "sendMessage":
            text = dict(parse_qsl(request.content.decode()))["text"]
            if text.startswith(openings):
                return httpx.Response(500, json={"ok": False, "description": "refused"})
        return answer(request, method)

    monkeypatch.setattr(fake, "answer", picky)


class Delegated:
    """Stands in for the tool that hands work on. Each call answers as a child that wrote the
    next of `written` would: the result is built by the function the real tool builds it with."""

    def __init__(self) -> None:
        self.written: list[tuple[str, int]] = []
        schema = {"type": "object", "properties": {}}
        self.tool = Tool("delegate", "Giao việc.", schema, self._run)

    async def _run(self, args: dict[str, Any]) -> ToolResult:
        art, version = self.written.pop(0)
        header = "conversation=c9 status=done spent=$0.0100 steps=2"
        block = [f"{artifact_tag(art, version)} tên do agent con đặt"]
        return ToolResult(ok=True, output=result_text(header, "outcome=done", block, "", "Xong."))


def hands_on(call_id: str):
    return completion(tool_calls=(ToolCall(call_id, "delegate", {}),))


async def test_a_brief_is_followed_by_its_files_then_its_canvases_then_why_it_stopped(
    make_channel, fake
):
    channel = make_channel()
    store = channel.store
    (channel.deps.agent.workspace / "brief.pdf").write_bytes(b"%PDF-1.4\n")
    plan = canvas(store, "Dàn ý")
    conv = asked(store)
    began(store, conv.id, HALTED, summary="max_steps", spent_usd=0.0123)
    wrote(store, conv.id, plan)
    said(store, conv.id, f"Mới được nửa chừng.\nFILE: brief.pdf\nFILE: artifact:{plan}")
    assert await channel.deliver(conv.id) is True
    assert fake.calls == [
        "sendMessage",
        "sendDocument",
        "sendDocument",
        "sendMessage",
        "sendMessage",
    ]
    assert [upload.name for upload in fake.uploads] == ["brief.pdf", "Dàn ý.md"]
    assert fake.sent == [
        "Mới được nửa chừng.",
        listed(("Dàn ý", 1)),
        texts.TELEGRAM_RUN_CUT_SHORT.format(reason=OUT_OF_STEPS, spent=0.0123),
    ]


async def test_a_run_that_only_wrote_canvases_is_answered_by_their_list(make_channel, fake):
    """It did what it was asked. The sentence for a run with nothing to say ends by asking
    the person to send the question again."""
    channel = make_channel()
    store = channel.store
    plan = canvas(store, "Dàn ý")
    conv = asked(store)
    began(store, conv.id)
    wrote(store, conv.id, plan, 2)
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [listed(("Dàn ý", 2))]
    fake.sent.clear()
    store.artifacts.delete(plan)  # nothing left to name, so the run reads as empty again
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [texts.REPLY_EMPTY.format(steps=0)]


async def test_a_run_that_stopped_without_a_word_names_what_it_wrote_before_saying_so(
    make_channel, fake
):
    channel = make_channel()
    store = channel.store
    plan = canvas(store, "Dàn ý")
    conv = asked(store)
    began(store, conv.id, HALTED, summary="max_steps")
    wrote(store, conv.id, plan)
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [
        listed(("Dàn ý", 1)),
        texts.TELEGRAM_RUN_UNFINISHED.format(reason=OUT_OF_STEPS),
    ]


async def test_a_run_that_wrote_no_canvas_gets_no_list(make_channel, fake):
    """Reading a canvas answers with its tag too, and a reply may quote one."""
    channel = make_channel()
    store = channel.store
    plan = canvas(store, "Dàn ý")
    conv = asked(store)
    began(store, conv.id)
    read = f"{artifact_tag(plan, 1)} nội dung"
    store.append(
        conv.id, Message(role="tool", content=read, tool_call_id="c1", name="artifact_read")
    )
    said(store, conv.id, f"{artifact_tag(plan, 1)} là bản mới nhất.")
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [f"{artifact_tag(plan, 1)} là bản mới nhất."]


async def test_what_no_run_is_known_to_have_written_is_not_named(make_channel, fake):
    channel = make_channel()
    store = channel.store
    plan = canvas(store, "Dàn ý")
    conv = asked(store)
    wrote(store, conv.id, plan)
    assert await channel.deliver(conv.id) is False and fake.calls == []
    said(store, conv.id, "Xong.")
    assert await channel.deliver(conv.id) is True
    assert fake.sent == ["Xong."]


async def test_a_crew_members_list_goes_out_under_its_name(crew, fake):
    store = crew.store
    plan = canvas(store, "Dàn ý")
    conv = asked(store, "coach")
    began(store, conv.id)
    wrote(store, conv.id, plan)
    said(store, conv.id, "Xong.")
    assert await crew.deliver(conv.id) is True
    assert fake.sent == ["[HLV]\nXong.", listed(("Dàn ý", 1), prefix="[HLV]")]


async def test_a_brief_sends_and_names_what_its_own_conversation_holds(crew, fake):
    """An agent other than the master reaches a person's canvas through the conversation it
    is linked to and no other way, so the file and the list both hang on which conversation
    the brief is delivered for."""
    store = crew.store
    conv = asked(store, "coach")
    notes = persons_canvas(store, PLAN, conv.id)
    began(store, conv.id)
    wrote(store, conv.id, notes)
    said(store, conv.id, f"Đây.\nFILE: artifact:{notes}")
    assert await crew.deliver(conv.id) is True
    assert [upload.data for upload in fake.uploads] == [PLAN.encode()]
    assert fake.sent == ["[HLV]\nĐây.", listed(("Ghi chú của người", 1), prefix="[HLV]")]


@pytest.mark.parametrize("status", [DONE, HALTED])
async def test_a_wordless_brief_names_what_its_own_conversation_holds(crew, fake, status):
    store = crew.store
    conv = asked(store, "coach")
    notes = persons_canvas(store, PLAN, conv.id)
    began(store, conv.id, status, summary="max_steps")
    wrote(store, conv.id, notes)
    assert await crew.deliver(conv.id) is True
    stopped = texts.TELEGRAM_RUN_UNFINISHED.format(reason=OUT_OF_STEPS)
    assert fake.sent == [
        listed(("Ghi chú của người", 1), prefix="[HLV]"),
        *([f"[HLV]\n{stopped}"] if status == HALTED else []),
    ]


async def test_a_run_delivered_twice_names_each_canvas_once(make_channel, fake):
    """A job that stops for an approval is delivered while it waits, and once more when
    nobody answered and it went on. The second time repeats the words, as it always has, and
    names only what was written since."""
    channel = make_channel()
    store = channel.store
    canvas_a, canvas_b = canvas(store, "Dàn ý"), canvas(store, "Số liệu")
    conv = asked(store)
    run = began(store, conv.id, AWAITING)
    wrote(store, conv.id, canvas_a)
    request = waits_on(store, conv.id, WRITE)
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [
        listed(("Dàn ý", 1)),
        texts.TELEGRAM_RUN_UNFINISHED.format(reason=AWAITING),
    ]
    fake.sent.clear()
    nobody_answered(store, conv.id, request)
    wrote(store, conv.id, canvas_b)
    said(store, conv.id, "Xong.")
    store.runs.save(replace(run, status=DONE))
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [
        texts.TELEGRAM_APPROVAL_EXPIRED.format(name="workspace_write"),
        "Xong.",
        listed(("Số liệu", 1)),
    ]


async def test_a_run_whose_question_lapsed_between_two_deliveries_names_each_canvas_once(
    make_channel, fake
):
    """A job that stops to ask is delivered while it waits too, and goes on by itself when
    nobody answers. Nothing was refused, so no line says a guard timed out; the first
    canvas was named by the first delivery and is not named again."""
    channel = make_channel()
    store = channel.store
    canvas_a, canvas_b = canvas(store, "Dàn ý"), canvas(store, "Số liệu")
    conv = asked(store)
    run = began(store, conv.id, AWAITING)
    wrote(store, conv.id, canvas_a)
    request = waits_on(store, conv.id, ASK)
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [
        listed(("Dàn ý", 1)),
        texts.TELEGRAM_RUN_UNFINISHED.format(reason=AWAITING),
    ]
    fake.sent.clear()
    nobody_answered(store, conv.id, request)
    wrote(store, conv.id, canvas_b)
    said(store, conv.id, "Xong.")
    store.runs.save(replace(run, status=DONE))
    assert await channel.deliver(conv.id) is True
    assert fake.sent == ["Xong.", listed(("Số liệu", 1))]


async def test_a_job_that_asked_and_went_on_unanswered_names_each_canvas_once(
    make_channel, deps_factory, fake
):
    """The same through a real job and the sweep that closes what nobody answered: the run
    is one run across both stretches, and its two deliveries name one canvas each."""
    child = Delegated()
    check = Schedule("deadline-check", "Nhắc hạn", cron="30 7 * * *", prompt="Có hạn nào không?")
    script = [hands_on("d1"), completion(tool_calls=(ASK,)), hands_on("d2"), completion("Xong.")]
    deps = with_schedules(deps_factory(script=script, extra_tools=[child.tool]), check)
    channel = make_channel(deps)
    child.written = [(canvas(deps.store, "Dàn ý"), 1), (canvas(deps.store, "Số liệu"), 1)]

    async def deliver(agent_id: str, conv_id: str) -> bool:
        return await channel.deliver(conv_id)

    run = await Scheduler({"default": deps}, channel.hub, deliver=deliver).run_job(
        "default/deadline-check"
    )
    assert run.status == AWAITING
    assert fake.sent == [
        listed(("Dàn ý", 1)),
        texts.TELEGRAM_RUN_UNFINISHED.format(reason=ASK.arguments["question"]),
    ]
    fake.sent.clear()
    later = datetime.now(UTC) + timedelta(seconds=deps.settings.approval_ttl_seconds + 1)
    assert len(await expire_overdue({"default": deps}, channel.hub, deliver, now=later)) == 1
    assert fake.sent == ["Xong.", listed(("Số liệu", 1))]


async def test_the_list_is_of_what_the_run_had_written_when_delivery_began(make_channel, fake):
    """Sending takes a while and the conversation goes on meanwhile. What is written while
    the words are on their way belongs to a delivery of its own, whether the same run wrote
    it or the next one."""
    channel = make_channel()
    store = channel.store
    plan, later, next_runs = canvas(store, "Dàn ý"), canvas(store, "Số liệu"), canvas(store, "Lịch")
    conv = asked(store)
    began(store, conv.id)
    wrote(store, conv.id, plan)
    said(store, conv.id, "Xong.")
    gate = fake.hold("sendMessage")
    delivery = asyncio.create_task(channel.deliver(conv.id))
    await until(lambda: "sendMessage" in fake.calls)
    wrote(store, conv.id, later)
    began(store, conv.id, run_id="r2")
    wrote(store, conv.id, next_runs)
    gate.set()
    assert await delivery is True
    assert fake.sent == ["Xong.", listed(("Dàn ý", 1))]


async def test_a_turn_names_its_canvases_after_its_reply_and_the_files_it_attached(
    make_channel, fake
):
    channel = make_channel()
    plan = canvas(channel.store, "Dàn ý")
    conv = channel.conversation()
    turn = (result(plan), spoke(f"Đã lập dàn ý.\nFILE: artifact:{plan}"), DoneEvent(0.0, 0))
    await channel.reply_to(stream(*turn), conv.id)
    assert messages_and_files(fake) == ["sendMessage", "sendDocument", "sendMessage"]
    assert fake.sent == ["Đã lập dàn ý.", listed(("Dàn ý", 1))]


async def test_a_turn_that_only_wrote_canvases_is_answered_by_their_list(make_channel, fake):
    channel = make_channel()
    store = channel.store
    plan = canvas(store, "Dàn ý")
    conv = channel.conversation()
    wordless = (result(plan, 2), spoke(""), DoneEvent(0.0, 0))
    await channel.reply_to(stream(*wordless), conv.id)
    assert fake.sent == [listed(("Dàn ý", 2))]
    fake.sent.clear()
    store.artifacts.delete(plan)  # gone by the end of the turn: silence would read as a dead bot
    await channel.reply_to(stream(*wordless), conv.id)
    await channel.reply_to(stream(spoke(""), DoneEvent(0.0, 0)), conv.id)
    assert fake.sent == [texts.REPLY_EMPTY.format(steps=1)] * 2


async def test_a_wordless_turn_that_wrote_nothing_is_answered_as_it_always_was(
    make_channel, fake, monkeypatch
):
    """Its one sentence is the turn's answer, sent where a failure to send it is caught and
    said: only a turn that wrote canvases has that sentence held back for the list."""
    channel = make_channel()
    conv = channel.conversation()
    empty = texts.REPLY_EMPTY.format(steps=1)
    refuse(fake, monkeypatch, empty)
    await channel.reply_to(stream(spoke(""), DoneEvent(0.0, 0)), conv.id)
    assert fake.sent == [texts.TELEGRAM_TURN_FAILED.format(error="TelegramError")]


async def test_a_closing_line_that_cannot_be_sent_is_a_failure_the_chat_hears_of(
    make_channel, fake, monkeypatch, caplog
):
    """The turn wrote a canvas and said nothing, the canvas is gone by its end, and so its
    one sentence goes out after all, where the list would have. Telegram refusing it there is
    what it is anywhere else: logged, and said to the chat by the error's kind."""
    channel = make_channel()
    plan = canvas(channel.store, "Dàn ý")
    conv = channel.conversation()

    async def turn():
        yield result(plan)
        channel.store.artifacts.delete(plan)
        yield DoneEvent(0.0, 0)

    refuse(fake, monkeypatch, texts.REPLY_EMPTY.format(steps=0))
    with caplog.at_level(logging.ERROR):
        await channel.reply_to(turn(), conv.id)
    assert fake.sent == [texts.TELEGRAM_TURN_FAILED.format(error="TelegramError")]
    assert "a turn failed" in caplog.text and "refused" in caplog.text


async def test_a_turn_that_breaks_still_names_what_it_wrote(make_channel, fake):
    channel = make_channel()
    plan = canvas(channel.store, "Dàn ý")
    conv = channel.conversation()
    await channel.reply_to(stream(result(plan), fails=RuntimeError("model down")), conv.id)
    assert fake.sent == [
        texts.TELEGRAM_TURN_FAILED.format(error="RuntimeError"),
        listed(("Dàn ý", 1)),
    ]


async def test_a_turn_sends_and_names_what_its_own_conversation_holds(
    make_channel, deps_factory, fake
):
    """The chat of an agent that is not the master: a person's canvas is within its reach in
    the conversation it is linked to, and in no other."""
    deps = deps_factory(routes=(Route("fake", "echo"),))
    deps.profile = replace(deps.agent, id="coach", name="HLV")
    channel = make_channel(deps)
    store = channel.store
    conv, other = channel.conversation(), store.create(agent_id="coach")
    notes = persons_canvas(store, PLAN, conv.id)
    turn = (result(notes), spoke(f"Đây.\nFILE: artifact:{notes}"), DoneEvent(0.0, 0))
    await channel.reply_to(stream(*turn), conv.id)
    assert [upload.data for upload in fake.uploads] == [PLAN.encode()]
    assert fake.sent == ["Đây.", listed(("Ghi chú của người", 1))]
    fake.sent.clear()
    await channel.reply_to(stream(*turn), other.id)
    assert fake.sent == ["Đây.", texts.TELEGRAM_CANVAS_MISSING.format(id=notes)]
    assert len(fake.uploads) == 1


async def test_each_leg_of_a_turn_that_waited_for_approval_names_its_own(
    make_channel, deps_factory, fake
):
    """The turn stops to ask and goes on once the person has answered: two replies, and each
    names what was written on its own stretch."""
    child = Delegated()
    script = [hands_on("d1"), completion(tool_calls=(WRITE,)), hands_on("d2"), completion("Xong.")]
    deps = deps_factory(script=script, extra_tools=[child.tool])
    channel = make_channel(deps)
    child.written = [(canvas(deps.store, "Dàn ý"), 1), (canvas(deps.store, "Số liệu"), 3)]
    await poll_each(channel, fake, message(1, "làm đi"), message(2, "/approve"))
    assert fake.sent == [
        texts.REPLY_APPROVAL.format(
            name="workspace_write", reason="", how=texts.TELEGRAM_APPROVAL_HOW
        ),
        listed(("Dàn ý", 1)),
        "Xong.",
        listed(("Số liệu", 3)),
    ]


@pytest.mark.parametrize(
    ("answer", "heard"),
    [("Đã cập nhật.", ["Đã cập nhật.", listed(("Dàn ý", 2))]), ("OK", [])],
)
async def test_a_job_names_what_it_wrote_unless_it_has_nothing_to_report(
    make_channel, deps_factory, fake, answer, heard
):
    """A check that answers `OK` is not pushed to the chat, and a canvas it wrote on the way
    does not change that: the list comes with a brief, it is not one."""
    child = Delegated()
    check = Schedule("deadline-check", "Nhắc hạn", cron="30 7 * * *", prompt="Có hạn nào không?")
    script = [hands_on("d1"), completion(answer)]
    deps = with_schedules(deps_factory(script=script, extra_tools=[child.tool]), check)
    channel = make_channel(deps)
    child.written = [(canvas(deps.store, "Dàn ý"), 2)]

    async def deliver(agent_id: str, conv_id: str) -> bool:
        return await channel.deliver(conv_id)

    run = await Scheduler({"default": deps}, channel.hub, deliver=deliver).run_job(
        "default/deadline-check"
    )
    assert run.status == DONE and fake.sent == heard


async def test_a_list_that_cannot_be_sent_costs_the_turn_one_line(
    make_channel, fake, monkeypatch, caplog
):
    channel = make_channel()
    plan = canvas(channel.store, "Dàn ý")
    conv = channel.conversation()
    turn = (result(plan), spoke("Xong."), DoneEvent(0.0, 0))
    refuse(fake, monkeypatch, texts.TELEGRAM_CANVAS_HEADER)
    with caplog.at_level(logging.WARNING):
        await channel.reply_to(stream(*turn), conv.id)
    assert fake.sent == ["Xong.", texts.TELEGRAM_CANVAS_NOTICE_FAILED]
    assert "canvas notice not sent" in caplog.text and "a turn failed" not in caplog.text
    fake.sent.clear()
    refuse(fake, monkeypatch, texts.TELEGRAM_CANVAS_NOTICE_FAILED)  # that line is refused too
    await channel.reply_to(stream(*turn), conv.id)
    assert fake.sent == ["Xong."]


async def test_a_wordless_run_whose_list_cannot_be_sent_is_not_called_empty(
    make_channel, fake, monkeypatch
):
    """The run did write, so the sentence for a run with nothing to say would be untrue."""
    channel = make_channel()
    store = channel.store
    plan = canvas(store, "Dàn ý")
    conv = asked(store)
    began(store, conv.id)
    wrote(store, conv.id, plan)
    refuse(fake, monkeypatch, texts.TELEGRAM_CANVAS_HEADER)
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [texts.TELEGRAM_CANVAS_NOTICE_FAILED]


async def test_with_nothing_to_name_nothing_is_sent_and_with_nothing_written_nothing_is_read(
    make_channel, fake, monkeypatch
):
    channel = make_channel()
    store = channel.store
    conv = store.create(agent_id="default")
    gone = canvas(store, "Dàn ý")
    store.artifacts.delete(gone)
    out = channel.outbound()
    assert await out.send_written([Tag(gone, 1)], conv.id) is False and fake.calls == []

    def read(*args, **kwargs):
        raise AssertionError("the store was read")

    monkeypatch.setattr(store, "get", read)
    monkeypatch.setattr(store.artifacts, "get", read)
    assert await out.send_written([], conv.id) is False and fake.calls == []


@pytest.mark.parametrize("bare", [False, True])
async def test_a_title_that_reads_like_an_attachment_line_attaches_nothing(
    make_channel, fake, monkeypatch, bare
):
    """A title is whatever the model chose. Read the way a reply is, a list naming a canvas
    titled `FILE: a.pdf` would send the file of that name. The bullet and the quotes a row
    opens with would hide that, so the second case takes them away."""
    if bare:
        monkeypatch.setattr(texts, "TELEGRAM_CANVAS_LINE", "{title}")
    channel = make_channel()
    (channel.deps.agent.workspace / "a.pdf").write_bytes(b"%PDF-1.4\n")
    art = canvas(channel.store, "FILE: a.pdf")
    conv = channel.conversation()
    await channel.reply_to(stream(result(art), spoke("Xong."), DoneEvent(0.0, 0)), conv.id)
    assert fake.uploads == []
    row = "FILE: a.pdf" if bare else '• "FILE: a.pdf" v1'
    assert fake.sent == [
        "Xong.",
        "\n".join([texts.TELEGRAM_CANVAS_HEADER, row, texts.TELEGRAM_CANVAS_OPEN_WEB]),
    ]
