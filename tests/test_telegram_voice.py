"""A Telegram voice note becomes a chat turn: it is transcribed by an audio route, the
sender hears "Đã nghe: …" to catch a mishearing, and the transcript then joins the master's
turn like any other message — never as a slash command or a steer, however it reads."""

import asyncio
import base64
import logging

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.channels.voice import (
    MAX_VOICE_BYTES,
    MAX_VOICE_SECONDS,
    NOT_HEARD,
    find_voice,
)
from my_agent_crew.config import Route
from my_agent_crew.inbound_queue import QueueDrain
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import AudioPart, ToolCall
from my_agent_crew.store.queue import FOLLOW_UP
from tests.queue_helpers import GatedProvider, SlowTool
from tests.telegram_fake import audio, document, message, photo, settle, voice

STT_ROUTE = (Route("stt", "listener"),)


def make_voice_channel(make_channel, deps_factory, script, audio_routes=STT_ROUTE):
    """The master on `fake:echo`, a separate `stt` provider for transcription — the same
    split a real deployment has between the chat model and the audio route."""
    provider = ScriptedProvider(list(script), name="stt")
    deps = deps_factory(
        routes=(Route("fake", "echo"),), providers={"stt": provider}, audio_routes=audio_routes
    )
    return make_channel(deps), provider, deps


async def test_find_voice_reads_a_voice_note_and_an_audio_file_and_skips_the_rest():
    assert find_voice(voice(1, "v1", duration=4)["message"]).format == "ogg"
    mp3 = find_voice(audio(1, "a1", mime_type="audio/mpeg")["message"])
    assert mp3 is not None and mp3.format == "mp3"
    m4a_by_mime = find_voice(audio(1, "a2", mime_type="audio/mp4")["message"])
    assert m4a_by_mime is not None and m4a_by_mime.format == "m4a"
    m4a_by_suffix = find_voice(audio(1, "a3", file_name="ghi_am.m4a")["message"])
    assert m4a_by_suffix is not None and m4a_by_suffix.format == "m4a"
    unknown = find_voice(audio(1, "a4", file_name="clip.xyz")["message"])
    assert unknown is not None and unknown.format is None
    assert find_voice(photo(1, "p1")["message"]) is None
    assert find_voice({"chat": {"id": 42}}) is None
    assert find_voice({"voice": {"duration": 3}}) is None  # no file_id


async def test_a_voice_note_is_heard_transcribed_and_handed_to_the_master_as_one_turn(
    make_channel, deps_factory, fake
):
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [completion("bật đèn")])
    fake.files = {"v1": "voice/note_1.oga"}
    fake.updates = [voice(1, "v1", duration=5)]

    await channel.poll_once()
    await settle(channel)

    [saved] = list((deps.agent.workspace / "inbox").iterdir())
    assert saved.read_bytes() == b"BYTES:voice/note_1.oga"
    expected = base64.b64encode(b"BYTES:voice/note_1.oga").decode("ascii")
    [request] = stt.requests
    assert request.messages[-1].audio == (AudioPart(data=expected, format="ogg"),)
    assert fake.sent[0] == texts.TELEGRAM_VOICE_HEARD.format(text="bật đèn")
    file_line = texts.TELEGRAM_ATTACHMENT_LINE.format(path=saved)
    turn = texts.TELEGRAM_VOICE_TURN.format(file=file_line, text="bật đèn", caption="").rstrip()
    assert fake.sent[1] == f"(echo) {turn}"
    conv = deps.store.list()[0]
    [call] = deps.store.side_calls.for_conversation(conv.id)
    assert call.purpose == "transcribe" and call.provider == "stt"


async def test_no_audio_route_reports_how_to_enable_it_without_downloading(
    make_channel, deps_factory, fake
):
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [], audio_routes=())
    fake.files = {"v1": "voice/note_1.oga"}
    fake.updates = [voice(1, "v1")]

    await channel.poll_once()
    await settle(channel)

    assert fake.sent == [texts.TELEGRAM_VOICE_NO_ROUTE]
    assert "download" not in fake.calls and stt.requests == []
    assert deps.store.list() == []


async def test_a_voice_note_over_the_duration_limit_is_refused_without_downloading(
    make_channel, deps_factory, fake
):
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [])
    fake.files = {"v1": "voice/note_1.oga"}
    fake.updates = [voice(1, "v1", duration=MAX_VOICE_SECONDS + 1)]

    await channel.poll_once()
    await settle(channel)

    assert fake.sent == [
        texts.TELEGRAM_VOICE_TOO_LONG.format(seconds=MAX_VOICE_SECONDS + 1, limit=MAX_VOICE_SECONDS)
    ]
    assert "download" not in fake.calls and stt.requests == []
    assert deps.store.list() == []  # refused before any conversation opens


async def test_an_audio_file_whose_format_cannot_be_told_is_refused_without_downloading(
    make_channel, deps_factory, fake
):
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [])
    fake.files = {"a1": "audio/clip.xyz"}
    fake.updates = [audio(1, "a1", file_name="clip.xyz")]

    await channel.poll_once()
    await settle(channel)

    assert fake.sent == [texts.TELEGRAM_VOICE_FORMAT]
    assert "download" not in fake.calls and stt.requests == []


async def test_a_file_oversized_only_after_download_is_refused_before_transcription(
    make_channel, deps_factory, fake
):
    """Telegram does not always send `file_size`; a clip whose metadata under-reports its
    size still gets caught once the real bytes are on disk, before the paid call happens."""
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [])
    big = b"x" * (MAX_VOICE_BYTES + 1)
    fake.files = {"v1": "voice/note_1.oga"}

    async def big_download(remote, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(big)
        return path

    channel.api.download_file = big_download  # type: ignore[method-assign]
    fake.updates = [voice(1, "v1", duration=5)]

    await channel.poll_once()
    await settle(channel)

    mb = 1024 * 1024
    assert fake.sent == [
        texts.TELEGRAM_VOICE_TOO_BIG.format(size=len(big) / mb, limit=MAX_VOICE_BYTES / mb)
    ]
    assert stt.requests == []


async def test_a_failed_download_is_reported_and_opens_a_conversation_with_no_turn(
    make_channel, deps_factory, fake
):
    """Unlike a photo (whose caption-carrying turn is built only once every file is saved),
    a voice note's conversation opens before the download so the reply lands in the right
    place; a failed download still leaves that conversation with nothing in its history."""
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [])
    fake.updates = [voice(1, "missing", duration=5)]  # not registered in fake.files

    await channel.poll_once()
    await settle(channel)

    assert fake.sent[0].startswith("Không tải được tệp đính kèm")
    assert stt.requests == []
    [conv] = deps.store.list()
    assert deps.store.history(conv.id) == []


async def test_a_route_failure_is_reported_without_leaking_its_own_text(
    make_channel, deps_factory, fake, caplog
):
    channel, stt, deps = make_voice_channel(
        make_channel, deps_factory, [ProviderError("upstream quoting sk-secret-token")]
    )
    fake.files = {"v1": "voice/note_1.oga"}
    fake.updates = [voice(1, "v1", duration=5)]

    with caplog.at_level(logging.WARNING):
        await channel.poll_once()
        await settle(channel)

    assert fake.sent == [texts.TELEGRAM_VOICE_FAILED.format(reason="tuyến chép lời lỗi")]
    # The chat reply and this feature's own log line never quote the provider's text; the
    # provider chain's own route-failure log (unrelated to this feature) still does, by an
    # existing, unrelated design that lets an operator see which route broke and why.
    assert "sk-secret-token" not in fake.sent[0]
    assert "voice transcription route failed: AllRoutesFailed" in caplog.text
    assert "sk-secret-token" not in caplog.text.split("voice transcription route failed")[-1]
    conv = deps.store.list()[0]
    assert deps.store.side_calls.for_conversation(conv.id) == []  # never billed: it never answered


async def test_an_empty_or_unclear_transcript_still_bills_the_call_it_made(
    make_channel, deps_factory, fake
):
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [completion(NOT_HEARD)])
    fake.files = {"v1": "voice/note_1.oga"}
    fake.updates = [voice(1, "v1", duration=5)]

    await channel.poll_once()
    await settle(channel)

    assert fake.sent == [texts.TELEGRAM_VOICE_FAILED.format(reason="không nghe rõ tiếng nói")]
    conv = deps.store.list()[0]
    [call] = deps.store.side_calls.for_conversation(conv.id)
    assert call.purpose == "transcribe"  # the model answered; the call still cost something


async def test_a_transcription_that_times_out_is_reported_and_opens_no_turn(
    make_channel, deps_factory, fake, monkeypatch
):
    from my_agent_crew.channels import voice as voice_module

    monkeypatch.setattr(voice_module, "TRANSCRIBE_TIMEOUT_SECONDS", 0.05)

    class Sleepy:
        name = "stt"

        async def stream(self, messages, tools, model, reasoning=""):
            await asyncio.sleep(1)
            yield completion("quá trễ")

    deps = deps_factory(
        routes=(Route("fake", "echo"),), providers={"stt": Sleepy()}, audio_routes=STT_ROUTE
    )
    channel = make_channel(deps)
    fake.files = {"v1": "voice/note_1.oga"}
    fake.updates = [voice(1, "v1", duration=5)]

    await channel.poll_once()
    await settle(channel)

    assert fake.sent == [texts.TELEGRAM_VOICE_FAILED.format(reason="hết giờ chờ")]
    [conv] = deps.store.list()
    assert deps.store.history(conv.id) == []


async def test_a_voice_note_arriving_while_the_agent_is_busy_queues_and_never_steers(
    make_channel, deps_factory, fake
):
    """The transcript reads `/steer …`, which would steer a running turn if it were typed
    in the chat — but a voice turn is never handed to the parser that recognises `/steer`,
    only to `channel.chat`, and the text it sends never starts with `/`."""
    slow = SlowTool()
    master = GatedProvider(
        [completion(tool_calls=[ToolCall("c1", "slow", {})]), completion("xong")]
    )
    stt = ScriptedProvider([completion("/steer đổi hướng")], name="stt")
    deps = deps_factory(
        routes=(Route("scripted", "m"),),
        providers={"scripted": master, "stt": stt},
        extra_tools=[slow.tool],
        audio_routes=STT_ROUTE,
    )
    channel = make_channel(deps)
    drain = QueueDrain(deps.store, channel.hub, channel.inbound)
    channel.set_drain(drain)
    drain.register(TELEGRAM, channel.run_delivered)  # what the channel's start does
    fake.updates = [message(1, "việc dài")]
    await channel.poll_once()
    await asyncio.wait_for(slow.started.wait(), 2)
    running_conv = channel.conversation().id

    fake.files = {"v1": "voice/note_1.oga"}
    fake.updates = [voice(2, "v1", duration=5)]
    await channel.poll_once()

    assert channel.conversation().id == running_conv  # stayed in the busy conversation
    # The clip is still heard and transcribed while the agent is busy — transcription never
    # waits on the running turn — and only the resulting turn joins the queue behind it.
    assert fake.sent[-2] == texts.TELEGRAM_VOICE_HEARD.format(text="/steer đổi hướng")
    [item] = deps.store.queue.peek_all(running_conv)
    assert item.kind == FOLLOW_UP  # queued as a follow-up, never taken as a steer
    assert not item.text.startswith("/")
    assert "/steer đổi hướng" in item.text

    slow.release.set()
    await settle(channel, drain)
    assert deps.store.queue.count(running_conv) == 0
    history = deps.store.history(running_conv)
    assert any(
        m.message.role == "user" and "/steer đổi hướng" in m.message.content for m in history
    )


async def test_two_voice_notes_in_one_group_each_get_their_own_hearing_and_turn(
    make_channel, deps_factory, fake
):
    channel, stt, deps = make_voice_channel(
        make_channel, deps_factory, [completion("một"), completion("hai")]
    )
    fake.files = {"v1": "voice/note_1.oga", "v2": "voice/note_2.oga"}
    fake.updates = [voice(1, "v1", duration=3, caption="ghi chú"), voice(2, "v2", duration=3)]

    assert await channel.poll_once() == 2
    await settle(channel)

    heard = [s for s in fake.sent if s.startswith("Đã nghe: ")]
    assert heard == [
        texts.TELEGRAM_VOICE_HEARD.format(text="một"),
        texts.TELEGRAM_VOICE_HEARD.format(text="hai"),
    ]
    saved = list((deps.agent.workspace / "inbox").iterdir())
    assert len(saved) == 2 and len(stt.requests) == 2


async def test_a_document_alongside_no_voice_still_uses_the_attachment_path(
    make_channel, deps_factory, fake
):
    """A message with only a document runs the ordinary attachment flow, untouched by this
    feature — voice's precedence over an attachment in the same batch is its own test."""
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [])
    fake.files = {"doc": "documents/file_1.pdf"}
    fake.updates = [document(1, "doc", "hop_dong.pdf")]

    await channel.poll_once()
    await settle(channel)

    assert stt.requests == []
    [saved] = list((deps.agent.workspace / "inbox").iterdir())
    assert fake.sent == [f"(echo) [Tệp đính kèm đã lưu: {saved}]"]


async def test_a_message_carrying_both_a_voice_and_a_document_takes_the_voice_path(
    make_channel, deps_factory, fake
):
    """Telegram never actually sends one message with both `voice` and `document` set, but
    `handle_updates` still has to pick one path for whatever it is handed: voice must win,
    so a note is never silently swapped for the attachment flow's own, different reply."""
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [completion("giữ chỗ")])
    both = voice(1, "v1", duration=3)
    both["message"]["document"] = {"file_id": "doc", "file_name": "hop_dong.pdf"}
    fake.files = {"v1": "voice/note_1.oga", "doc": "documents/file_1.pdf"}
    fake.updates = [both]

    await channel.poll_once()
    await settle(channel)

    assert len(stt.requests) == 1
    assert fake.sent[0] == texts.TELEGRAM_VOICE_HEARD.format(text="giữ chỗ")
    saved = list((deps.agent.workspace / "inbox").iterdir())
    assert len(saved) == 1 and saved[0].name.endswith("note_1.oga")


async def test_audio_route_reaches_the_channel_straight_off_deps_with_no_extra_wiring(
    make_channel, deps_factory, fake
):
    """`audio_chain` reads `channel.deps.settings.audio_routes` and
    `channel.deps.chain.providers` directly, with no wiring beyond `deps_factory` — the
    same access pattern the plan calls for, proven here against the real property chain."""
    channel, stt, deps = make_voice_channel(make_channel, deps_factory, [completion("ok")])
    assert deps.settings.audio_routes == STT_ROUTE
    assert "stt" in deps.chain.providers
    fake.files = {"v1": "voice/note_1.oga"}
    fake.updates = [voice(1, "v1", duration=2)]

    await channel.poll_once()
    await settle(channel)

    assert fake.sent[0] == texts.TELEGRAM_VOICE_HEARD.format(text="ok")
