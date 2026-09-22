"""The Telegram channel against a fake Bot API: inbound messages become tracked turns of
a per-day conversation, replies and `MEDIA:` photos go back to the one allowed chat, and
scheduled results are delivered through the same path."""

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.channels import TelegramApi
from my_agent_crew.channels.telegram_api import (
    TelegramError,
    plain_text,
    split_message,
    split_reply,
)
from my_agent_crew.channels.telegram_commands import MENU, local_clock, parse_command
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.store.runs import DONE, HALTED, RunRecord
from tests.telegram_fake import CHAT, TOKEN, document, message, photo


async def test_inbound_message_runs_a_tracked_turn_and_replies(make_channel, fake, tmp_path):
    channel = make_channel()
    fake.updates = [message(7, "xin chào")]
    assert await channel.poll_once() == 1
    assert fake.sent == ["(echo) xin chào"]
    [conv] = channel.deps.store.list()
    assert conv.channel == f"telegram:{CHAT}" and conv.agent_id == "default"
    assert conv.title == texts.TELEGRAM_CONVERSATION_TITLE.format(date=datetime.now().date())
    [run] = channel.hub.recent()
    assert run.source == "telegram" and run.conversation_id == conv.id and run.status == "done"
    assert (tmp_path / "telegram.offset").read_text() == "8"
    assert await channel.poll_once() == 0  # offset moved past the handled update
    assert fake.calls.index("sendChatAction") < fake.calls.index("sendMessage")


async def test_typing_indicator_is_kept_alive_and_never_breaks_the_turn(make_channel, fake, caplog):
    channel = make_channel()
    async with channel.outbound().typing(interval=0.01):
        await asyncio.sleep(0.05)
    assert fake.calls.count("sendChatAction") >= 3
    assert "sendMessage" not in fake.calls
    fake.calls.clear()
    fake.reject_actions = True
    fake.updates = [message(1, "a")]
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.channels"):
        await channel.poll_once()
    assert fake.sent == ["(echo) a"]
    assert "typing indicator" in caplog.text and "sendChatAction" in caplog.text


async def test_messages_from_other_chats_are_ignored(make_channel, fake):
    channel = make_channel()
    fake.updates = [message(1, "hi", chat=99), {"update_id": 2, "message": {"chat": {"id": CHAT}}}]
    assert await channel.poll_once() == 2
    assert fake.sent == [] and channel.deps.store.list() == []


async def test_a_photo_is_saved_to_the_inbox_and_the_agent_reads_its_path_with_the_caption(
    make_channel, fake
):
    clock = datetime(2026, 9, 21, 14, 5, 9)
    channel = make_channel(clock=lambda: clock)
    fake.files = {"big": "photos/file_7.jpg"}
    fake.updates = [photo(1, "big", caption="sổ đỏ lô B")]
    await channel.poll_once()
    saved = channel.deps.agent.workspace / "inbox" / "20260921-140509-file_7.jpg"
    assert saved.read_bytes() == b"BYTES:photos/file_7.jpg"
    assert fake.sent == [f"(echo) [Tệp đính kèm đã lưu: {saved}]\nsổ đỏ lô B"]
    assert fake.calls.count("getFile") == 1 and "small" not in fake.files.values()


def album(update_id: int, file_id: str, group: str, caption: str = "") -> dict:
    update = photo(update_id, file_id, caption=caption)
    update["message"]["media_group_id"] = group
    return update


async def test_an_album_is_one_message_with_every_photo_and_the_caption(make_channel, fake):
    """Telegram sends an album as one update per photo, the caption on the first only;
    the agent reads all the saved paths together, in one turn."""
    channel = make_channel(clock=lambda: datetime(2026, 9, 21, 14, 5, 9))
    fake.files = {"p1": "photos/file_1.jpg", "p2": "photos/file_2.jpg", "p3": "photos/file_3.jpg"}
    fake.updates = [
        album(1, "p1", "g1", caption="hai mặt giấy tờ"),
        album(2, "p2", "g1"),
        album(3, "p3", "g1"),
        message(4, "xong"),
    ]
    assert await channel.poll_once() == 4
    inbox = channel.deps.agent.workspace / "inbox"
    lines = "\n".join(
        f"[Tệp đính kèm đã lưu: {inbox / f'20260921-140509-file_{n}.jpg'}]" for n in (1, 2, 3)
    )
    assert fake.sent == [f"(echo) {lines}\nhai mặt giấy tờ", "(echo) xong"]
    assert len(list(inbox.iterdir())) == 3 and fake.calls.count("getFile") == 3
    assert len(channel.hub.recent()) == 2  # one turn for the album, one for the text


async def test_an_album_still_arriving_is_waited_for(make_channel, fake, monkeypatch):
    """A poll may end in the middle of an album; the channel asks again, briefly, before
    handing the agent half the photos."""
    from my_agent_crew.channels import telegram_albums

    naps: list[float] = []

    async def nap(seconds: float) -> None:
        naps.append(seconds)
        fake.updates.append(album(2, "p2", "g1"))  # the second photo lands during the wait

    monkeypatch.setattr(telegram_albums.asyncio, "sleep", nap)
    channel = make_channel()
    fake.files = {"p1": "photos/file_1.jpg", "p2": "photos/file_2.jpg"}
    fake.updates = [album(1, "p1", "g1", caption="cả hai")]
    assert await channel.poll_once() == 2
    [sent] = fake.sent
    assert "file_1.jpg" in sent and "file_2.jpg" in sent and sent.endswith("cả hai")
    assert naps == [telegram_albums.ALBUM_SETTLE_SECONDS] * telegram_albums.ALBUM_SETTLE_ROUNDS
    assert fake.calls.count("getUpdates") == 1 + telegram_albums.ALBUM_SETTLE_ROUNDS
    assert await channel.poll_once() == 0  # the offset moved past the whole album


def test_updates_of_one_album_are_grouped_and_everything_else_stands_alone():
    from my_agent_crew.channels.telegram_albums import group_updates

    updates = [message(1, "a"), album(2, "x", "g1"), album(3, "y", "g1"), album(4, "z", "g2")]
    groups = group_updates(updates)
    assert [[u["update_id"] for u in group] for group in groups] == [[1], [2, 3], [4]]
    assert group_updates([]) == []


async def test_a_document_keeps_the_senders_file_name_reduced_to_a_plain_name(make_channel, fake):
    channel = make_channel(clock=lambda: datetime(2026, 9, 21, 8, 0, 0))
    fake.files = {"doc": "documents/file_3.pdf"}
    fake.updates = [document(1, "doc", "../../hợp đồng (bản 2).pdf")]
    await channel.poll_once()
    inbox = channel.deps.agent.workspace / "inbox"
    [saved] = list(inbox.iterdir())
    assert saved.name == "20260921-080000-hợp_đồng_bản_2_.pdf"
    # No caption: the agent reads just the saved path, without a dangling blank line.
    assert fake.sent == [f"(echo) [Tệp đính kèm đã lưu: {saved}]"]


async def test_a_failed_download_is_reported_without_a_model_turn(make_channel, fake, caplog):
    channel = make_channel()
    fake.updates = [photo(1, "gone")]
    with caplog.at_level(logging.WARNING, logger="my_agent_crew.channels"):
        await channel.poll_once()
    assert len(fake.sent) == 1 and fake.sent[0].startswith("Không tải được tệp đính kèm")
    assert channel.deps.store.list() == [] and TOKEN not in caplog.text
    assert not (channel.deps.agent.workspace / "inbox").exists()


async def test_same_day_messages_share_one_conversation_and_a_new_day_opens_another(
    make_channel, fake
):
    clock = [datetime.now()]
    channel = make_channel(clock=lambda: clock[0])
    fake.updates = [message(1, "a"), message(2, "b")]
    await channel.poll_once()
    assert len(channel.deps.store.list()) == 1
    clock[0] += timedelta(days=1)
    fake.updates = [message(3, "c")]
    await channel.poll_once()
    assert len(channel.deps.store.list()) == 2


async def test_new_and_reset_commands_open_a_fresh_conversation(make_channel, fake):
    channel = make_channel()
    fake.updates = [message(1, "a"), message(2, "/new"), message(3, "b"), message(4, "/reset")]
    await channel.poll_once()
    assert fake.sent == [
        "(echo) a",
        texts.TELEGRAM_NEW_CONVERSATION,
        "(echo) b",
        texts.TELEGRAM_NEW_CONVERSATION,
    ]
    assert len(channel.deps.store.list()) == 3
    [run] = channel.hub.recent(1)  # commands never reach the model
    assert run.status == "done" and len(channel.hub.recent()) == 2


async def test_help_status_tools_and_unknown_commands_are_answered_locally(make_channel, fake):
    channel = make_channel()
    fake.updates = [message(1, "xin chào"), message(2, "/help"), message(3, "/status@mybot")]
    await channel.poll_once()
    fake.updates = [message(4, "/tools"), message(5, "/loop 5m"), message(6, "/usr/bin/x")]
    await channel.poll_once()
    reply, help_text, status, tools, unknown, path = fake.sent
    assert reply == "(echo) xin chào"
    assert help_text.splitlines()[0] == "/new — " + texts.TELEGRAM_COMMANDS["new"]
    assert all(f"/{name}" in help_text for name, _ in MENU)
    conv = channel.conversation()
    assert status.startswith(conv.title) and "Lượt: 1" in status and "fake:echo" in status
    assert texts.TELEGRAM_STATE_IDLE in status and "done, " in status
    [run] = channel.hub.recent(1)  # stamped in UTC, shown in the reader's zone
    assert status.endswith(datetime.fromisoformat(run.started_at).astimezone().strftime("%H:%M"))
    assert local_clock("2026-09-21T10:26:32+00:00", ZoneInfo("Asia/Ho_Chi_Minh")) == "17:26"
    assert tools.startswith("Công cụ (") and "workspace_read" in tools
    assert unknown == texts.TELEGRAM_UNKNOWN_COMMAND.format(command="loop")
    assert path == "(echo) /usr/bin/x"  # a path is not a command
    assert parse_command("/status extra") == "status" and parse_command("hi /x") is None


async def test_command_menu_is_registered_once_when_polling_starts(make_channel, fake):
    channel = make_channel()
    fake.status = 409  # getUpdates fails, so the loop backs off instead of spinning
    channel.start()
    await asyncio.sleep(0.02)
    await channel.stop()
    assert fake.calls.index("setMyCommands") < fake.calls.index("getUpdates")
    assert fake.calls.count("setMyCommands") == 1
    assert [(m["command"], m["description"]) for m in fake.menu] == list(MENU)
    assert ("reset", texts.TELEGRAM_COMMANDS["reset"]) in MENU


WRITE = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "ok"})


async def test_approve_and_deny_commands_resolve_the_pending_tool(make_channel, fake, deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("đã ghi")])
    channel = make_channel(deps)
    fake.updates = [message(1, "/approve"), message(2, "ghi file"), message(3, "/approve")]
    await channel.poll_once()
    assert fake.sent == [
        texts.TELEGRAM_NO_APPROVAL,
        texts.REPLY_APPROVAL.format(
            name="workspace_write", reason="", how=texts.TELEGRAM_APPROVAL_HOW
        ),
        "đã ghi",
    ]
    assert (deps.settings.workspace_dir / "out.txt").read_text() == "ok"
    assert channel.conversation().status != AWAITING_APPROVAL
    again = ToolCall("c2", "workspace_write", {"path": "second.txt", "content": "no"})
    deps = deps_factory(script=[completion(tool_calls=(again,)), completion("thôi vậy")])
    channel = make_channel(deps)  # same store, same day: continues the conversation above
    fake.sent.clear()
    fake.updates = [message(4, "ghi file"), message(5, "/status"), message(6, "/deny")]
    await channel.poll_once()
    assert texts.TELEGRAM_STATE_AWAITING.format(name="workspace_write") in fake.sent[1]
    assert fake.sent[2] == "thôi vậy"
    assert not (deps.settings.workspace_dir / "second.txt").exists()


async def test_text_written_next_to_a_tool_call_is_not_lost(make_channel, fake, deps_factory):
    look = ToolCall("c1", "workspace_list", {"path": "."})
    deps = deps_factory(
        script=[completion("Phân tích dài.", tool_calls=(look,)), completion("MEDIA: x.png")]
    )
    channel = make_channel(deps)
    fake.updates = [message(1, "hỏi")]
    await channel.poll_once()
    assert fake.sent == ["Phân tích dài.", texts.TELEGRAM_MEDIA_MISSING.format(path="x.png")]


async def test_provider_failure_and_pending_approval_become_notices(
    make_channel, fake, deps_factory
):
    channel = make_channel(deps_factory(script=[ProviderError("model down")]))
    fake.updates = [message(1, "a")]
    await channel.poll_once()
    [notice] = fake.sent
    assert notice.startswith(texts.REPLY_ERROR.format(message="")) and "model down" in notice
    conv = channel.conversation()
    channel.deps.store.update(conv.id, status=AWAITING_APPROVAL)
    fake.updates = [message(2, "b")]
    await channel.poll_once()
    assert fake.sent[-1] == texts.TELEGRAM_BUSY


async def test_deliver_announces_an_approval_that_expired_before_the_answer(make_channel, fake):
    channel = make_channel()
    store = channel.deps.store
    conv = store.create(agent_id="default")
    call = ToolCall("c1", "workspace_write", {"path": "x", "content": "y"})
    store.append(conv.id, Message(role="user", content="ghi đi"))
    store.append(conv.id, Message(role="assistant", content="", tool_calls=(call,)))
    store.append(
        conv.id,
        Message(role="tool", content=texts.EXPIRED_TOOL, tool_call_id="c1", name=call.name),
    )
    store.append(conv.id, Message(role="assistant", content="Thôi, không ghi."))
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [
        texts.TELEGRAM_APPROVAL_EXPIRED.format(name="workspace_write"),
        "Thôi, không ghi.",
    ]


async def test_deliver_sends_prose_and_media_lines_as_photos(make_channel, fake):
    channel = make_channel()
    workspace = channel.deps.agent.workspace
    (workspace / "charts").mkdir()
    (workspace / "charts" / "sleep.png").write_bytes(b"PNGDATA")
    conv = channel.deps.store.create(agent_id="default")
    assert await channel.deliver(conv.id) is False
    channel.deps.store.append(
        conv.id,
        Message(
            role="assistant",
            content="**Ngủ** 5.5h\nMEDIA: charts/sleep.png\nMEDIA: charts/missing.png",
        ),
    )
    assert await channel.deliver(conv.id) is True
    assert fake.sent == ["Ngủ 5.5h", texts.TELEGRAM_MEDIA_MISSING.format(path="charts/missing.png")]
    assert len(fake.photos) == 1 and b"PNGDATA" in fake.photos[0]


async def test_a_crew_members_brief_is_delivered_under_its_name_from_its_own_workspace(
    make_channel, fake, deps_factory, tmp_path
):
    """The chat talks to the master, but a member's scheduled brief still arrives there:
    prefixed with the member's name, its `MEDIA:` charts read from the member's workspace."""
    master = deps_factory(routes=(Route("fake", "echo"),))
    coach = deps_factory(routes=(Route("fake", "echo"),), home=tmp_path / "coach-home")
    coach.profile = replace(coach.agent, id="coach", name="HLV")
    channel = make_channel(master)
    channel.agents["coach"] = coach
    (coach.agent.workspace / "charts").mkdir(parents=True)
    (coach.agent.workspace / "charts" / "sleep.png").write_bytes(b"PNGDATA")
    conv = master.store.create(agent_id="coach")
    master.store.append(
        conv.id, Message(role="assistant", content="Ngủ 6h.\nMEDIA: charts/sleep.png")
    )
    assert await channel.deliver(conv.id) is True
    assert fake.sent == ["[HLV]\nNgủ 6h."] and len(fake.photos) == 1
    assert channel.outbound("coach") is not channel.outbound()
    stranger = master.store.create(agent_id="nobody")
    master.store.append(stranger.id, Message(role="assistant", content="x"))
    assert await channel.deliver(stranger.id) is False
    fake.updates = [message(1, "hi")]
    await channel.poll_once()  # the chat itself still goes to the master, unprefixed
    assert fake.sent[-1] == "(echo) hi" and master.store.list(agent_id="default")


async def test_deliver_joins_every_assistant_text_of_the_last_turn(make_channel, fake):
    channel = make_channel()
    store = channel.deps.store
    conv = store.create(agent_id="default")
    look = ToolCall("c1", "workspace_list", {"path": "."})
    store.append(conv.id, Message(role="assistant", content="Bản tin cũ"))
    store.append(conv.id, Message(role="user", content="hỏi"))
    store.append(conv.id, Message(role="assistant", content="Kiểm tra đã.", tool_calls=(look,)))
    store.append(conv.id, Message(role="tool", content="[]", tool_call_id="c1", name=look.name))
    store.append(conv.id, Message(role="assistant", content="Kết luận."))
    assert await channel.deliver(conv.id) is True
    assert fake.sent == ["Kiểm tra đã.\n\nKết luận."]


async def test_api_errors_and_httpx_request_logs_never_carry_the_token(fake, caplog):
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    api = TelegramApi(TOKEN, client)
    with caplog.at_level(logging.INFO, logger="httpx"):
        await api.send_message(CHAT, "hello")
    assert "sendMessage" in caplog.text and "<token>" in caplog.text
    assert TOKEN not in caplog.text
    fake.status = 409
    with pytest.raises(TelegramError) as conflict:
        await api.get_updates(0)
    assert conflict.value.status == 409 and TOKEN not in str(conflict.value)
    fake.status, fake.raise_connect = None, True
    with pytest.raises(TelegramError) as unreachable:
        await api.send_message(CHAT, "x")
    assert TOKEN not in str(unreachable.value) and "<token>" in str(unreachable.value)


def test_message_helpers_split_media_chunk_long_text_and_strip_markdown():
    assert split_reply("a\nMEDIA: x.png\n b \nMEDIA:y.png") == ("a\n b", ["x.png", "y.png"])
    assert split_message("l1\n" + "x" * 4096) == ["l1", "x" * 4096]
    assert split_message("l1\n" + "x" * 4094 + "\nl3") == ["l1", "x" * 4094, "l3"]
    assert split_message("y" * 5000, limit=4096) == ["y" * 4096, "y" * 904]
    assert split_message("") == [""]
    assert plain_text("## Tiêu đề\n**đậm** thường") == "Tiêu đề\nđậm thường"


async def test_deliver_reports_a_run_that_stopped_without_a_reply(make_channel, fake):
    """A scheduled job that hits max_steps leaves only tool calls behind; the chat must
    still hear that it stopped instead of silence."""
    channel = make_channel()
    store = channel.deps.store
    conv = store.create(agent_id="default")
    store.append(conv.id, Message(role="user", content="tổng kết tuần"))
    look = ToolCall("c1", "workspace_list", {"path": "."})
    store.append(conv.id, Message(role="assistant", content="", tool_calls=(look,)))
    store.append(conv.id, Message(role="tool", content="[]", tool_call_id="c1", name=look.name))
    stamp = "2026-09-20T01:00:00"
    store.runs.save(RunRecord("r1", "default", conv.id, "job:default/x", "t", DONE, stamp))
    # A finished run with nothing to say still reaches the chat: a brief that never arrives
    # is indistinguishable from a broken schedule.
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [texts.REPLY_EMPTY.format(steps=0)]
    fake.sent.clear()
    store.runs.save(
        RunRecord(
            "r2", "default", conv.id, "job:default/x", "t", HALTED, stamp, summary="max_steps"
        )
    )
    assert store.runs.latest_for_conversation(conv.id).id == "r2"
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [texts.TELEGRAM_RUN_UNFINISHED.format(reason="max_steps")]


async def test_a_turn_that_produces_no_text_says_so_instead_of_staying_silent(
    make_channel, fake, deps_factory
):
    """A model that finishes with nothing to say must not read like a dead bot. The loop
    retries a blank once, so it takes two to reach the end of a turn."""
    deps = deps_factory(script=[completion("   "), completion("   ")])
    channel = make_channel(deps)
    fake.updates = [message(1, "tuần này sao rồi")]
    await channel.poll_once()
    blank = texts.BLANK_COMPLETION.format(provider="scripted", model="m")
    assert fake.sent == [texts.REPLY_ERROR.format(message=blank)]


async def test_an_approval_forced_by_the_ask_list_says_which_pattern_matched(
    make_channel, fake, deps_factory
):
    danger = ToolCall("c9", "shell_run", {"command": "sudo rm -rf /tmp/x"})
    deps = deps_factory(script=[completion(tool_calls=(danger,))], autonomous_default=True)
    channel = make_channel(deps)
    channel.deps.store.update(channel.conversation().id, autonomous=True)
    fake.updates = [message(1, "dọn tmp")]
    await channel.poll_once()
    reason = texts.SHELL_ASK_REASON.format(pattern="rm -rf")  # first match in list order
    how = texts.TELEGRAM_APPROVAL_HOW
    notice = texts.REPLY_APPROVAL.format(name="shell_run", reason=f" ({reason})", how=how)
    assert fake.sent == [notice]


async def test_an_error_without_a_description_still_names_the_method_and_status():
    """A gateway error answers with an empty body; the status has to survive into the log
    or the failure reads as a bare method name."""

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, content=b"")

    api = TelegramApi(TOKEN, httpx.AsyncClient(transport=httpx.MockTransport(empty)))
    with pytest.raises(TelegramError) as failure:
        await api.send_message(CHAT, "x")
    assert str(failure.value) == "sendMessage: HTTP 502"


async def test_a_reply_from_a_run_that_stopped_early_carries_a_notice(make_channel, fake):
    channel = make_channel()
    store = channel.deps.store
    conv = store.create(agent_id="default")
    store.append(conv.id, Message(role="user", content="tổng kết tuần"))
    store.append(conv.id, Message(role="assistant", content="Mới được nửa chừng."))
    stamp = "2026-09-20T01:00:00"
    store.runs.save(RunRecord("r1", "default", conv.id, "job:default/x", "t", DONE, stamp))
    assert await channel.deliver(conv.id) is True
    assert fake.sent == ["Mới được nửa chừng."]

    fake.sent.clear()
    store.runs.save(
        RunRecord(
            "r2",
            "default",
            conv.id,
            "job:default/x",
            "t",
            HALTED,
            stamp,
            summary="max_steps",
            spent_usd=0.0123,
        )
    )
    assert await channel.deliver(conv.id) is True
    assert fake.sent == [
        "Mới được nửa chừng.",
        texts.TELEGRAM_RUN_CUT_SHORT.format(reason="max_steps", spent=0.0123),
    ]


async def test_opening_a_new_conversation_hands_the_replaced_one_to_the_runtime(make_channel, fake):
    channel = make_channel()
    replaced: list[str] = []
    channel.set_on_replaced(lambda deps, conv_id: replaced.append(conv_id))
    fake.updates = [message(1, "xin chào")]
    await channel.poll_once()
    first = channel.conversation()

    fake.updates = [message(2, "/new")]
    await channel.poll_once()

    assert replaced == [first.id]
    assert channel.conversation().id != first.id


async def test_the_first_conversation_on_a_channel_replaces_nothing(make_channel, fake):
    channel = make_channel()
    replaced: list[str] = []
    channel.set_on_replaced(lambda deps, conv_id: replaced.append(conv_id))
    fake.updates = [message(1, "/new")]

    await channel.poll_once()

    assert replaced == []


async def test_a_new_day_replaces_yesterdays_conversation(make_channel, fake):
    clock = [datetime.now()]
    channel = make_channel(clock=lambda: clock[0])
    replaced: list[str] = []
    channel.set_on_replaced(lambda deps, conv_id: replaced.append(conv_id))
    fake.updates = [message(1, "xin chào")]
    await channel.poll_once()
    yesterday = channel.conversation()

    clock[0] += timedelta(days=1)
    fake.updates = [message(2, "chào buổi sáng")]
    await channel.poll_once()

    assert replaced == [yesterday.id] and channel.conversation().id != yesterday.id
