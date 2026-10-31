"""Deciding from the chat with a press: the buttons under a request, what a press settles,
and the requests of a delegated child told to the chat and settled from it."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import parse_qsl

import httpx

from my_agent_crew import texts
from my_agent_crew.agent.events import ApprovalRequiredEvent
from my_agent_crew.channels.telegram_api import ALLOWED_UPDATES, TelegramApi
from my_agent_crew.channels.telegram_approvals import (
    APPROVAL_REQUIRED,
    child_request,
    watch_children,
)
from my_agent_crew.channels.telegram_buttons import Press, buttons_for, call_line, read_press
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.approvals import PENDING
from tests.lapse_helpers import WRITE
from tests.telegram_fake import CHAT, TOKEN, asks_for, message, poll_each, press, settle

ASK = ToolCall("a1", "ask_user", {"question": "Uống gì?", "options": ["Trà", "Cà phê"]})


def tool_request(rid: str = "abc123def456") -> ApprovalRequiredEvent:
    return ApprovalRequiredEvent(rid, "c1", WRITE.name, WRITE.arguments)


def test_a_request_words_its_buttons_and_reads_them_back():
    allow, deny = buttons_for(tool_request())["inline_keyboard"][0]
    assert (allow["text"], deny["text"]) == (
        texts.TELEGRAM_BUTTON_APPROVE,
        texts.TELEGRAM_BUTTON_DENY,
    )
    assert read_press(allow["callback_data"]) == Press("abc123def456", True)
    assert read_press(deny["callback_data"]) == Press("abc123def456", False)
    asked = ApprovalRequiredEvent("ab12", "c1", "ask_user", {}, kind="question", options=["A", "B"])
    rows = buttons_for(asked)["inline_keyboard"]
    assert [row[0]["text"] for row in rows] == ["1. A", "2. B"]
    assert read_press(rows[1][0]["callback_data"]) == Press("ab12", False, 2)
    assert buttons_for(ApprovalRequiredEvent("ab12", "c1", "ask_user", {}, kind="question")) is None
    for junk in ("", "y:", "x:ab12", "q0:ab12", "y:AB12", "y:ab12;drop"):
        assert read_press(junk) is None, junk


def test_the_call_line_shows_what_would_run_cut_short():
    assert call_line(tool_request()) == f"workspace_write {json.dumps(WRITE.arguments)}"
    huge = ApprovalRequiredEvent("ab12", "c1", "shell_run", {"command": "x" * 900})
    assert len(call_line(huge)) < 450 and call_line(huge).endswith("…")
    assert call_line(None) == ""


async def test_a_press_under_the_chats_request_approves_and_the_agent_answers(
    make_channel, deps_factory, fake
):
    channel = make_channel(
        deps_factory(script=[completion(tool_calls=(WRITE,)), completion("Đây.")])
    )
    await poll_each(channel, fake, message(1, "ghi file"))
    [keyboard] = fake.buttons
    allow = keyboard["inline_keyboard"][0][0]["callback_data"]
    await poll_each(channel, fake, press(2, allow, text=fake.sent[0]))
    assert fake.answered == [texts.TELEGRAM_PRESS_APPROVED]
    assert fake.edits[0]["text"] == f"{asks_for(WRITE)}\n\n{texts.TELEGRAM_PRESS_APPROVED}"
    assert fake.sent == [asks_for(WRITE), "Đây."]
    assert (channel.deps.agent.workspace / WRITE.arguments["path"]).exists()
    await poll_each(channel, fake, press(3, allow))  # pressed again, on the old message
    assert fake.answered[-1] == texts.TELEGRAM_PRESS_SETTLED and len(fake.sent) == 2


async def test_a_deny_press_refuses_and_a_foreign_or_garbled_press_settles_nothing(
    make_channel, deps_factory, fake
):
    channel = make_channel(
        deps_factory(script=[completion(tool_calls=(WRITE,)), completion("Thôi.")])
    )
    await poll_each(channel, fake, message(1, "ghi file"))
    rid = channel.store.approvals.pending(channel.conversation().id).id
    await poll_each(channel, fake, press(2, f"y:{rid}", chat=CHAT + 1), press(3, f"q1:{rid}"))
    assert fake.answered == [texts.TELEGRAM_PRESS_SETTLED], "the foreign chat is not answered"
    assert channel.store.approvals.get(rid).status == PENDING
    await poll_each(channel, fake, press(4, f"n:{rid}"))
    assert fake.answered[-1] == texts.TELEGRAM_PRESS_DENIED
    assert fake.sent[-1] == "Thôi."
    assert not (channel.deps.agent.workspace / WRITE.arguments["path"]).exists()


async def test_a_choice_pressed_is_the_answer(make_channel, deps_factory, fake):
    channel = make_channel(
        deps_factory(script=[completion(tool_calls=(ASK,)), completion("Có ngay.")])
    )
    await poll_each(channel, fake, message(1, "pha gì đó"))
    rows = fake.buttons[0]["inline_keyboard"]
    await poll_each(channel, fake, press(2, rows[1][0]["callback_data"]))
    assert fake.answered == [texts.TELEGRAM_PRESS_ANSWERED.format(answer="Cà phê")]
    assert fake.sent[-1] == "Có ngay."


async def delegated_pause(channel):
    """A child of the chat's conversation, as a delegation opens it, run until it asks."""
    root = channel.conversation()
    child = channel.store.create(agent_id=channel.agent_id, root_id=root.id, parent_call_id="d1")
    async for _ in channel.inbound.stream(child.id, "làm hộ"):
        pass
    return root, child, channel.store.approvals.pending(child.id)


async def test_a_childs_request_is_told_to_the_chat_and_a_press_settles_it_in_silence(
    make_channel, deps_factory, fake
):
    channel = make_channel(
        deps_factory(script=[completion(tool_calls=(WRITE,)), completion("Xong.")])
    )
    watching = asyncio.create_task(watch_children(channel))
    await asyncio.sleep(0)
    root, child, asked = await delegated_pause(channel)
    for _ in range(100):
        if fake.sent:
            break
        await asyncio.sleep(0.01)
    await settle(channel)
    watching.cancel()
    assert fake.sent == [asks_for(WRITE)]
    assert (
        read_press(fake.buttons[0]["inline_keyboard"][0][0]["callback_data"]).approval_id
        == asked.id
    )
    root_said = {"type": "event", "conversation_id": root.id, "event": {"type": APPROVAL_REQUIRED}}
    assert child_request(channel, root_said) is None, "the chat's own says it in its reply"
    await poll_each(channel, fake, press(1, f"y:{asked.id}"))
    assert fake.answered == [texts.TELEGRAM_PRESS_APPROVED]
    assert fake.sent == [asks_for(WRITE)], "the child's answer goes to its parent, not the chat"
    assert (channel.deps.agent.workspace / WRITE.arguments["path"]).exists()


async def test_approve_reaches_a_child_and_says_so(make_channel, deps_factory, fake):
    channel = make_channel(
        deps_factory(script=[completion(tool_calls=(WRITE,)), completion("Xong.")])
    )
    _, _, asked = await delegated_pause(channel)
    await poll_each(channel, fake, message(1, "/approve"))
    assert fake.sent == [texts.TELEGRAM_PRESS_APPROVED]
    assert channel.store.approvals.get(asked.id).status != PENDING


async def test_a_typed_answer_reaches_a_childs_question(make_channel, deps_factory, fake):
    channel = make_channel(
        deps_factory(script=[completion(tool_calls=(ASK,)), completion("Đã pha.")])
    )
    _, child, asked = await delegated_pause(channel)
    await poll_each(channel, fake, message(1, "2"))
    assert fake.sent == []
    assert channel.store.approvals.get(asked.id).status != PENDING
    assert channel.store.history(child.id)[-1].message.content == "Đã pha."


async def test_polling_asks_for_presses_too():
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(parse_qsl(request.content.decode())))
        return httpx.Response(200, json={"ok": True, "result": []})

    api = TelegramApi(TOKEN, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await api.get_updates(0, timeout=0)
    assert json.loads(seen[0]["allowed_updates"]) == ALLOWED_UPDATES
    assert "callback_query" in ALLOWED_UPDATES
