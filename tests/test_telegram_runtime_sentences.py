"""The sentences the runtime adds to a chat are said as they stand.

A reply is read line by line for `MEDIA:` and `FILE:` lines, because the reply is the agent's
and what to attach is the agent's to choose. The sentences the runtime says around it are not
the agent's: why a run stopped, that a guard timed out, that a run was empty, that the
provider failed, what a slash command is answered with. Several quote free text, a provider's
error, the question a job stopped at or the title of a conversation, and a line of that text
shaped like an attachment line would send a file nobody chose to send. So none of them is
read: such a line stays in the sentence, and nothing is uploaded.
"""

from __future__ import annotations

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.events import DoneEvent, ErrorEvent
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.channels.telegram_api import split_message
from my_agent_crew.channels.telegram_commands import status_text
from my_agent_crew.inbound import collect_reply
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.store.queue import FOLLOW_UP
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, HALTED
from tests.canvas_helpers import PNG
from tests.lapse_helpers import WRITE, nobody_answered, waits_on
from tests.telegram_fake import message, poll_each
from tests.test_scheduler import with_schedules
from tests.test_telegram_canvas_notice_sent import (
    asked,
    began,
    canvas,
    messages_and_files,
    said,
    spoke,
    stream,
)

OUT_OF_STEPS = texts.HALT_REASONS["max_steps"]


def attachable(channel) -> str:
    """Free text naming a canvas, a photo and a document that are all there to be sent, each
    on a line of its own: read the way a reply is, it would send all three."""
    workspace = channel.deps.agent.workspace
    (workspace / "brief.pdf").write_bytes(b"%PDF-1.4\n")
    (workspace / "chart.png").write_bytes(PNG)
    plan = canvas(channel.store, "Dàn ý", channel.deps.agent.id)
    return f"upstream said\nFILE: artifact:{plan}\nMEDIA: chart.png\nFILE: brief.pdf\nretry later"


@pytest.mark.parametrize(
    ("words", "sentence"),
    [("", "TELEGRAM_RUN_UNFINISHED"), ("Mới được nửa chừng.", "TELEGRAM_RUN_CUT_SHORT")],
)
async def test_why_a_failed_run_stopped_is_said_whole_and_attaches_nothing(
    make_channel, fake, words, sentence
):
    """A failed run's reason is the provider's error, word for word."""
    channel = make_channel()
    store = channel.store
    reason = attachable(channel)
    conv = asked(store)
    began(store, conv.id, FAILED, summary=reason, spent_usd=0.0123)
    said(store, conv.id, words)
    assert await channel.deliver(conv.id) is True
    assert fake.uploads == []
    stopped = getattr(texts, sentence).format(reason=reason, spent=0.0123)
    assert fake.sent == [*([words] if words else []), stopped]
    assert reason in fake.sent[-1]


async def test_the_question_a_job_waits_on_is_said_whole_and_attaches_nothing(
    make_channel, deps_factory, fake
):
    """A job delivered while it waits says what it asked, and the question is the model's
    text. The files it names go out when the reply names them, not when the wait is told."""
    check = Schedule("deadline-check", "Nhắc hạn", cron="30 7 * * *", prompt="Có hạn nào không?")
    question = "Gửi bản nào?\nFILE: brief.pdf\nMEDIA: chart.png"
    ask = ToolCall("q1", "ask_user", {"question": question})
    deps = with_schedules(deps_factory(script=[completion(tool_calls=(ask,))]), check)
    channel = make_channel(deps)
    attachable(channel)

    async def deliver(agent_id: str, conv_id: str) -> bool:
        return await channel.deliver(conv_id)

    run = await Scheduler({"default": deps}, channel.hub, deliver=deliver).run_job(
        "default/deadline-check"
    )
    assert run.status == AWAITING and fake.uploads == []
    assert fake.sent == [texts.TELEGRAM_RUN_UNFINISHED.format(reason=question)]


@pytest.mark.parametrize(
    ("sentence", "status", "words", "heard"),
    [
        ("TELEGRAM_APPROVAL_EXPIRED", DONE, "Xong.", ["FILE: brief.pdf", "Xong."]),
        ("TELEGRAM_RUN_CUT_SHORT", HALTED, "Dở dang.", ["Dở dang.", "FILE: brief.pdf"]),
        ("REPLY_EMPTY", DONE, "", ["FILE: brief.pdf"]),
        ("TELEGRAM_RUN_UNFINISHED", HALTED, "", ["FILE: brief.pdf"]),
    ],
)
async def test_no_sentence_of_a_delivery_is_read_for_attachment_lines_whatever_it_says(
    make_channel, fake, monkeypatch, sentence, status, words, heard
):
    """Each of the four, worded as an attachment line would be: it is said, not obeyed. The
    words around a reason would hide a reading of the other three, so the wording goes."""
    monkeypatch.setattr(texts, sentence, "FILE: brief.pdf")
    channel = make_channel()
    store = channel.store
    attachable(channel)
    conv = asked(store)
    began(store, conv.id, status, summary="max_steps")
    if sentence == "TELEGRAM_APPROVAL_EXPIRED":
        nobody_answered(store, conv.id, waits_on(store, conv.id, WRITE))
    said(store, conv.id, words)
    assert await channel.deliver(conv.id) is True
    assert fake.uploads == [] and fake.sent == heard


async def test_a_reason_longer_than_one_message_arrives_whole(make_channel, fake):
    channel = make_channel()
    store = channel.store
    reason = "\n".join(f"dòng {number}: {'x' * 60}" for number in range(100))
    conv = asked(store)
    began(store, conv.id, FAILED, summary=reason)
    assert await channel.deliver(conv.id) is True
    stopped = texts.TELEGRAM_RUN_UNFINISHED.format(reason=reason)
    assert len(fake.sent) == 2 and fake.sent == split_message(stopped)
    assert "\n".join(fake.sent) == stopped


async def test_a_live_turn_that_broke_says_the_error_whole_and_attaches_nothing(
    make_channel, deps_factory, fake
):
    """The turn of a message typed in the chat, through the real loop: what the provider
    said is quoted in the reply, and is not the agent's to attach files with."""
    reason = "upstream said\nFILE: brief.pdf\nMEDIA: chart.png\nretry later"
    channel = make_channel(deps_factory(script=[ProviderError(reason)]))
    attachable(channel)
    await poll_each(channel, fake, message(1, "làm đi"))
    [notice] = fake.sent
    assert fake.uploads == []
    assert notice.startswith(texts.REPLY_ERROR.format(message="")) and reason in notice


async def test_a_turn_that_spoke_before_it_broke_attaches_what_it_named_and_no_more(
    make_channel, fake
):
    """What the agent said is still read for the files it named; the error under it, in the
    same message as ever, is not."""
    channel = make_channel()
    error = attachable(channel)
    conv = channel.conversation()
    turn = (spoke("Đây.\nFILE: brief.pdf"), ErrorEvent(message=error))
    await channel.reply_to(stream(*turn), conv.id)
    assert messages_and_files(fake) == ["sendMessage", "sendDocument"]
    assert [upload.name for upload in fake.uploads] == ["brief.pdf"]
    assert fake.sent == [f"Đây.\n\n{texts.REPLY_ERROR.format(message=error)}"]


async def test_a_status_is_said_whole_whatever_the_conversation_is_titled(make_channel, fake):
    """`/status` opens with the conversation's title, and a title is free text: whoever
    renames the conversation on the web words it."""
    channel = make_channel()
    titles = attachable(channel).splitlines()[1:4]  # the canvas, the photo, the document
    conv = channel.conversation()
    for number, title in enumerate(titles, start=1):
        channel.store.update(conv.id, title=title)
        await poll_each(channel, fake, message(number, "/status"))
        assert fake.sent[-1] == status_text(channel)
        assert fake.sent[-1].splitlines()[0] == title
    assert fake.uploads == [] and len(fake.sent) == len(titles) == 3


@pytest.mark.parametrize(
    ("typed", "sentence"),
    [
        ("/tools", "TELEGRAM_TOOLS"),
        ("/new", "TELEGRAM_NEW_CONVERSATION"),
        ("/new", "TELEGRAM_NEW_BUSY"),
        ("/loop 5m", "TELEGRAM_UNKNOWN_COMMAND"),
        ("/approve", "TELEGRAM_NO_APPROVAL"),
        ("/deny", "TELEGRAM_NO_APPROVAL"),
    ],
)
async def test_no_answer_to_a_command_is_read_for_attachment_lines_whatever_it_says(
    make_channel, fake, monkeypatch, typed, sentence
):
    """Each answer the runtime words itself, worded as an attachment line would be: it is
    said, not obeyed."""
    monkeypatch.setattr(texts, sentence, "FILE: brief.pdf")
    channel = make_channel()
    attachable(channel)
    if sentence == "TELEGRAM_NEW_BUSY":  # a message waits in line, so the chat stays put
        channel.store.queue.add(channel.conversation().id, FOLLOW_UP, "tin đang chờ", TELEGRAM)
    await poll_each(channel, fake, message(1, typed))
    assert fake.uploads == [] and fake.sent == ["FILE: brief.pdf"]


async def test_a_command_is_answered_under_no_name_in_a_chat_a_crew_shares(crew, fake):
    """The agent the chat talks to answers, by the sender its replies go out by: a crew
    member's name opens only what that member delivers."""
    await poll_each(crew, fake, message(1, "/tools"), message(2, "/loop 5m"), message(3, "/new"))
    names = crew.deps.tools.names()
    assert fake.sent == [
        texts.TELEGRAM_TOOLS.format(count=len(names), names="\n".join(names)),
        texts.TELEGRAM_UNKNOWN_COMMAND.format(command="loop"),
        texts.TELEGRAM_NEW_CONVERSATION,
    ]


@pytest.mark.parametrize("decision", ["/approve", "/deny"])
async def test_a_decision_says_nothing_itself_and_the_reply_it_resumes_is_the_agents(
    make_channel, deps_factory, fake, decision
):
    """`/approve` and `/deny` hand the turn on and leave the talking to it. The reply that
    follows is the agent's own, so the file it names is still sent."""
    script = [completion(tool_calls=(WRITE,)), completion("Đây.\nFILE: brief.pdf")]
    channel = make_channel(deps_factory(script=script))
    attachable(channel)
    await poll_each(channel, fake, message(1, "ghi file"), message(2, decision))
    waiting = texts.REPLY_APPROVAL.format(
        name=WRITE.name, reason="", how=texts.TELEGRAM_APPROVAL_HOW
    )
    assert fake.sent == [waiting, "Đây."]
    assert [upload.name for upload in fake.uploads] == ["brief.pdf"]
    written = channel.deps.agent.workspace / WRITE.arguments["path"]
    assert written.exists() is (decision == "/approve")


async def test_a_reply_keeps_its_error_apart_and_reads_whole_as_it_always_did():
    """The relay behind the API takes the reply as one text and gets what it always got."""
    notice = texts.REPLY_ERROR.format(message="model down")
    broke = await collect_reply(stream(spoke("Đây."), ErrorEvent(message="model down")))
    assert (broke.said, broke.error) == ("Đây.", notice)
    assert broke.to_dict() == {"text": f"Đây.\n\n{notice}", "steps": 1, "status": "error"}
    wordless = await collect_reply(stream(ErrorEvent(message="model down")))
    assert (wordless.said, wordless.error, wordless.text) == ("", notice, notice)
    fine = await collect_reply(stream(spoke("Đây."), DoneEvent(0.0, 0)))
    assert (fine.said, fine.error, fine.text) == ("Đây.", "", "Đây.")
    empty = await collect_reply(stream(DoneEvent(0.0, 0)))
    assert empty.said == empty.text == texts.REPLY_EMPTY.format(steps=0) and empty.error == ""


async def test_only_the_error_a_reply_ends_with_is_kept_out_of_what_was_said():
    """An agent that quoted the same sentence in its own words keeps every one of them."""
    notice = texts.REPLY_ERROR.format(message="model down")
    words = f"Lần trước nó báo:\n{notice}\nGiờ thử lại."
    broke = await collect_reply(stream(spoke(words), ErrorEvent(message="model down")))
    assert (broke.said, broke.error) == (words, notice)
    assert broke.text == f"{words}\n\n{notice}"
