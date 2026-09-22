"""Answering the agent in the chat itself.

On the web a question has a card with buttons. In a chat there is no card: the question
arrives as an ordinary message and so does the reply, which means the channel has to know
that the next thing the person types is an answer and not a new request. These tests pin
that, and the numbered choices that stand in for buttons.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew import texts
from my_agent_crew.agents.kit_commands import Command
from my_agent_crew.channels.telegram_answers import answer_text
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.approvals import ANSWERED
from my_agent_crew.store.models import QUESTION, Approval
from tests.telegram_fake import message

ASK = ToolCall(
    "q1",
    "ask_user",
    {"question": "Dời hạn sang thứ sáu?", "options": ["có", "không"]},
)
OPEN = ToolCall("q2", "ask_user", {"question": "Đặt tên gì?"})
WRITE = ToolCall("c1", "workspace_write", {"path": "x.txt", "content": "1"})


def asking(call: ToolCall, then: str):
    """A script that calls `call`, then answers once the question comes back."""
    return [completion(tool_calls=(call,)), completion(then)]


def a_question(options: list[str]) -> Approval:
    return Approval(
        id="a1",
        conversation_id="c1",
        message_id=1,
        tool_call_id="t1",
        tool_name="ask_user",
        arguments={"question": "Chọn?"},
        status="pending",
        created_at="",
        kind=QUESTION,
        options=options,
    )


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("2", "không"),  # a bare number is the choice it points at
        (" 1 ", "có"),  # spaces around it change nothing
        ("có", "có"),  # the words themselves pass through
        ("3", "3"),  # out of range: they may have meant the number
        ("0", "0"),  # the list is 1-based, so 0 points at nothing
        ("2 nhưng dời sang thứ sáu", "2 nhưng dời sang thứ sáu"),  # a sentence stays whole
    ],
)
def test_a_number_becomes_the_choice_it_points_at(typed: str, expected: str):
    assert answer_text(typed, a_question(["có", "không"])) == expected


def test_without_choices_a_number_is_just_what_they_typed():
    assert answer_text("2", a_question([])) == "2"


async def test_the_question_reaches_the_chat_with_its_choices_numbered(
    make_channel, fake, deps_factory
):
    channel = make_channel(deps_factory(script=asking(ASK, "đã dời")))
    fake.updates = [message(1, "xem hạn")]
    await channel.poll_once()
    sent = fake.sent[-1]
    assert "Dời hạn sang thứ sáu?" in sent
    assert "1. có" in sent and "2. không" in sent


async def test_the_next_message_is_read_as_the_answer(make_channel, fake, deps_factory):
    """The failure this prevents: the person answers, the channel treats it as a new
    request, and gets told the conversation is busy — busy waiting on them."""
    channel = make_channel(deps_factory(script=asking(ASK, "đã dời")))
    fake.updates = [message(1, "xem hạn")]
    await channel.poll_once()
    conv = channel.conversation()
    question = channel.store.approvals.pending_question(conv.id)
    assert question is not None

    fake.updates = [message(2, "2")]
    await channel.poll_once()

    closed = channel.store.approvals.get(question.id)
    assert closed.status == ANSWERED and closed.answer == "không"
    # The turn carried on: the agent was handed the answer, not a busy notice.
    assert channel.store.get(conv.id).status == "idle"
    history = channel.store.history(conv.id)
    tool_results = [m.message.content for m in history if m.message.role == "tool"]
    assert any("không" in content for content in tool_results)


async def test_a_waiting_tool_approval_still_reports_busy(make_channel, fake, deps_factory):
    """Only a question turns the next message into an answer. A tool waiting to be
    authorised is not something a sentence can settle."""
    channel = make_channel(deps_factory(script=asking(WRITE, "đã ghi")))
    fake.updates = [message(1, "ghi file")]
    await channel.poll_once()
    fake.updates = [message(2, "ừ chạy đi")]
    await channel.poll_once()
    assert fake.sent[-1] == texts.TELEGRAM_BUSY
    assert not (channel.deps.settings.workspace_dir / "x.txt").exists()


async def test_a_slash_command_is_not_swallowed_as_the_answer(make_channel, fake, deps_factory):
    """A kit command reaches `chat` as an ordinary message. If an open question ate it, the
    person would lose the command and the agent would be handed a word it cannot use."""
    deps = deps_factory(script=asking(ASK, "đã dời"))
    brief = Command("brief", "Tóm tắt hôm nay", "Tóm tắt hôm nay.")
    channel = make_channel(replace(deps, profile=replace(deps.agent, commands=(brief,))))
    fake.updates = [message(1, "xem hạn")]
    await channel.poll_once()
    conv = channel.conversation()
    question = channel.store.approvals.pending_question(conv.id)

    fake.updates = [message(2, "/brief")]
    await channel.poll_once()

    assert channel.store.approvals.get(question.id).status == "pending"


async def test_a_question_with_no_choices_takes_the_sentence_as_written(
    make_channel, fake, deps_factory
):
    channel = make_channel(deps_factory(script=asking(OPEN, "đã đặt tên")))
    fake.updates = [message(1, "đặt tên hộ")]
    await channel.poll_once()
    conv = channel.conversation()
    question = channel.store.approvals.pending_question(conv.id)

    fake.updates = [message(2, "Sổ tay tháng chín")]
    await channel.poll_once()

    assert channel.store.approvals.get(question.id).answer == "Sổ tay tháng chín"
