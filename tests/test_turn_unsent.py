"""What a chat is owed of a turn a restart cut (`turn_unsent.py`).

The bot reads a turn as it runs and answers once, when the turn ends or stops for a person.
A restart takes that reader with the turn, so the stretch it held was never sent: from where
the turn began, or from where it last stopped for a person, since the reply sent at a stop
said all the turn had written until then."""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew.agent.events import AssistantMessageEvent, ToolResultEvent
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.runs import RUNNING
from my_agent_crew.turn_unsent import after, unsent
from tests.conftest import collect
from tests.lapse_helpers import ASK, WRITE, answered, nobody_answered, refused, sent_again, waits_on
from tests.test_telegram_canvas_notice_sent import asked, began, said, spoke, stream

PEEK = ToolCall("p1", "peek", {})


def answers(store, conv_id: str, call: ToolCall, output: str) -> None:
    """The call ran, and the turn was handed what it gave."""
    store.append(
        conv_id, Message(role="tool", content=output, tool_call_id=call.id, name=call.name)
    )


def approved(store, conv_id: str, request) -> None:
    """The person said yes, and the call ran."""
    store.approvals.resolve(request.id, approve=True)
    answers(store, conv_id, WRITE, "Đã ghi out.txt")


def told(store, conv_id: str, request) -> None:
    answered(store, conv_id, request, "bơi")


def read(events) -> list[tuple[str, str]]:
    """Each event as who wrote it and what it says."""
    return [
        ("assistant", event.content)
        if isinstance(event, AssistantMessageEvent)
        else ("tool", event.output)
        for event in events
    ]


def test_what_the_turn_wrote_comes_back_as_its_reader_was_handed_it(store):
    asked(store)  # another conversation, so a message's id is not its place in its own
    conv = asked(store)
    said(store, conv.id, "Lượt trước.")
    run = began(store, conv.id, RUNNING)
    calling = Message(role="assistant", content="Đang tra.", tool_calls=(PEEK,))
    first = store.append(
        conv.id, calling, "scripted", "m", 0.002, prompt_tokens=120, cached_tokens=40
    )
    answers(store, conv.id, PEEK, "ba nguồn")

    assert first.id != first.seq
    assert unsent(store, run) == [
        AssistantMessageEvent(
            first.id, "Đang tra.", [PEEK.to_dict()], "scripted", "m", 0.002, 120, 40
        ),
        # Whether a call succeeded is not kept in the log; no reply reads it.
        ToolResultEvent("p1", "peek", True, "ba nguồn"),
    ]


def test_only_the_turn_that_was_cut_is_read(store):
    """Not the one before it, and not one that began after it."""
    conv = asked(store)
    said(store, conv.id, "Lượt trước.")
    run = began(store, conv.id, RUNNING)
    said(store, conv.id, "Của lượt này.")
    began(store, conv.id, run_id="r2")
    said(store, conv.id, "Lượt sau.")

    assert read(unsent(store, run)) == [("assistant", "Của lượt này.")]


def test_a_run_from_before_runs_knew_where_they_began_is_owed_nothing(store):
    conv = asked(store)
    run = began(store, conv.id, RUNNING)
    said(store, conv.id, "Đang tra.")

    assert unsent(store, replace(run, after_seq=None)) == []


def test_what_a_person_wrote_while_the_turn_ran_is_not_the_turns_to_say(store):
    conv = asked(store)
    run = began(store, conv.id, RUNNING)
    store.append(conv.id, Message(role="user", content="việc dài"))
    said(store, conv.id, "Đang tra.")
    store.append(conv.id, Message(role="user", content="nhanh lên nhé"))
    said(store, conv.id, "Sắp xong.")

    assert read(unsent(store, run)) == [("assistant", "Đang tra."), ("assistant", "Sắp xong.")]


@pytest.mark.parametrize(
    ("call", "closed"),
    [(WRITE, approved), (WRITE, refused), (WRITE, nobody_answered), (ASK, told)],
    ids=["approved", "refused", "lapsed", "answered"],
)
def test_what_was_written_before_the_turn_stopped_for_a_person_was_sent_then(store, call, closed):
    """The reply sent at the stop held it. The next reader began at what became of the call,
    whatever that was."""
    conv = asked(store)
    run = began(store, conv.id, RUNNING)
    said(store, conv.id, "Trước khi hỏi.")
    closed(store, conv.id, waits_on(store, conv.id, call))
    outcome = store.history(conv.id)[-1].message
    assert (outcome.role, outcome.tool_call_id) == ("tool", call.id)
    said(store, conv.id, "Sau đó.")

    assert read(unsent(store, run)) == [("tool", outcome.content), ("assistant", "Sau đó.")]


def test_a_turn_cut_while_the_call_it_asked_about_ran_has_sent_all_it_wrote(store):
    conv = asked(store)
    run = began(store, conv.id, RUNNING)
    said(store, conv.id, "Trước khi hỏi.")
    request = waits_on(store, conv.id, WRITE)
    store.approvals.resolve(request.id, approve=True)

    assert unsent(store, run) == []


def test_a_result_that_came_before_the_stop_in_the_same_message_was_sent_then(store):
    """The model asked for two things at once: the first ran, the second waited for a person."""
    conv = asked(store)
    run = began(store, conv.id, RUNNING)
    request = waits_on(store, conv.id, WRITE, asked=(PEEK, WRITE))
    answers(store, conv.id, PEEK, "ba nguồn")
    store.approvals.resolve(request.id, approve=True)
    assert unsent(store, run) == []  # cut while the call that waited ran

    answers(store, conv.id, WRITE, "Đã ghi out.txt")
    assert read(unsent(store, run)) == [("tool", "Đã ghi out.txt")]


def test_a_call_that_followed_the_stop_in_the_same_message_is_read_from_the_stop_on(store):
    conv = asked(store)
    run = began(store, conv.id, RUNNING)
    request = waits_on(store, conv.id, WRITE, asked=(WRITE, PEEK))
    store.approvals.resolve(request.id, approve=True)
    answers(store, conv.id, WRITE, "Đã ghi out.txt")

    # Cut while the second call ran: what the first one gave was never sent.
    assert read(unsent(store, run)) == [("tool", "Đã ghi out.txt")]


def test_a_call_id_the_model_uses_again_is_not_the_stop_it_once_was(store):
    conv = asked(store)
    run = began(store, conv.id, RUNNING)
    approved(store, conv.id, waits_on(store, conv.id, WRITE))
    said(store, conv.id, "Giữa chừng.")
    sent_again(store, conv.id, WRITE, "lần hai")
    since_the_stop = [
        ("tool", "Đã ghi out.txt"),
        ("assistant", "Giữa chừng."),
        ("assistant", ""),
        ("tool", "lần hai"),
    ]
    assert read(unsent(store, run)) == since_the_stop

    # Cut while a third call under that id ran, the turn is still owed all of it.
    store.append(conv.id, Message(role="assistant", content="Gọi lại.", tool_calls=(WRITE,)))
    assert read(unsent(store, run)) == [*since_the_stop, ("assistant", "Gọi lại.")]


async def test_what_was_never_sent_is_read_before_what_the_turn_writes_next():
    owed, live = [spoke("Trước chỗ cắt.")], [spoke("Sau chỗ cắt."), spoke("Hết.")]

    assert await collect(after(owed, stream(*live))) == [*owed, *live]


async def test_a_turn_that_breaks_after_what_it_was_owed_still_breaks():
    with pytest.raises(RuntimeError, match="gãy"):
        await collect(after([spoke("Trước chỗ cắt.")], stream(fails=RuntimeError("gãy"))))
