"""What the tail of the system prompt says about canvases, by where the turn's reader is.

A turn that cannot write a canvas is told so before the model puts a whole document into a
call only to have it refused. A turn whose reader is away from the web chat, a Telegram turn
or a job, is told when a canvas is worth making and how one is sent along. A turn of the web
chat is told neither. Every turn of an agent keeps the same tools and the same prompt up to
that tail, so the cached prefix is shared."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.prompt import system_prompt_for
from my_agent_crew.agent.prompt_frame import today_line
from my_agent_crew.agent.turn_context import API, CHAT, JOB, TELEGRAM, set_turn_source
from my_agent_crew.agents.context import daily_note_path
from my_agent_crew.channels.telegram_attachments import split_reply
from my_agent_crew.llm.fake import completion
from my_agent_crew.reply_attachments import artifact_ref
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_CHANNEL_CLOSED,
    CANVAS_AWAY_BODY,
    CANVAS_CLOSED_BODY,
    CANVAS_CLOSED_TITLE,
)
from my_agent_crew.tools.artifact_scope import CANVAS_WRITE_TOOLS
from tests.canvas_helpers import call, persons_canvas, put, turn
from tests.conftest import collect
from tests.test_canvas_payload_trim import canvas_tools

ALL_WRITES = "artifact_create, artifact_edit, artifact_rewrite, artifact_import"
AWAY = f"\n## {CANVAS_CLOSED_TITLE}\n{CANVAS_AWAY_BODY}\n"


def note(tools: str = ALL_WRITES) -> str:
    return f"\n## {CANVAS_CLOSED_TITLE}\n{CANVAS_CLOSED_BODY.format(tools=tools)}\n"


async def _first_request(deps, conv_id: str, source: str, depth: int = 0):
    await collect(run_turn(deps, conv_id, "viết kế hoạch tuần", source=source, depth=depth))
    return deps.chain.providers["scripted"].requests[-1]


async def _child_prompt(deps, store: Store, root_source: str) -> str:
    """The system prompt of a child's turn, in a chain that began in `root_source`."""
    root = store.create()
    child = store.create(parent_call_id="call-1", root_id=root.id, root_source=root_source)
    request = await _first_request(deps, child.id, f"delegate:{root.id}", depth=1)
    return request.messages[0].content


async def test_a_turn_that_cannot_write_a_canvas_is_told_so_with_the_same_tools(
    deps_factory, store: Store, tmp_path: Path
):
    """The inbound API and a child whose chain began there hear it, after the day's notes
    and right before the date, so a turn on any channel shares the prefix up to there; the
    web chat and a child of it do not."""
    tools = canvas_tools(store, tmp_path)
    deps = deps_factory(script=[completion("được")] * 5, extra_tools=tools)
    note_path = daily_note_path(deps.agent.memory_dir, deps.settings.today())
    note_path.write_text("- đã chốt lịch chạy sáng thứ bảy\n")
    chat = await _first_request(deps, store.create().id, CHAT)
    system = chat.messages[0].content
    date = today_line(deps.settings, deps.settings.today().isoformat())
    assert system.endswith(date) and CANVAS_CLOSED_TITLE not in system
    assert "lịch chạy sáng thứ bảy" in system
    request = await _first_request(deps, store.create().id, API)
    head, tail = request.messages[0].content.split(note())
    assert (head + tail, tail, request.tools) == (system, date, chat.tools)
    for root_source, closed in ((API, True), ("", True), (CHAT, False)):
        prompt = await _child_prompt(deps, store, root_source)
        assert (note() in prompt) is closed, root_source


async def test_a_turn_whose_reader_is_away_from_the_web_chat_is_told_how_a_canvas_reaches_them(
    deps_factory, store: Store, tmp_path: Path
):
    """A Telegram turn, a job and a child whose chain began in either hear it in the same
    place, after the day's notes and right before the date, as the only thing said about
    canvases. The web chat's prompt is theirs without it, to the character, so it is what
    it was before Telegram could write a canvas. A job hears what a Telegram turn hears, word
    for word: nothing in it can say which of the two its reader is."""
    tools = canvas_tools(store, tmp_path)
    deps = deps_factory(script=[completion("được")] * 8, extra_tools=tools)
    note_path = daily_note_path(deps.agent.memory_dir, deps.settings.today())
    note_path.write_text("- đã chốt lịch chạy sáng thứ bảy\n")
    chat = await _first_request(deps, store.create().id, CHAT)
    system = chat.messages[0].content
    date = today_line(deps.settings, deps.settings.today().isoformat())
    assert system.endswith(date) and "lịch chạy sáng thứ bảy" in system
    assert CANVAS_CLOSED_TITLE not in system and CANVAS_AWAY_BODY not in system
    heard = []
    for source in (TELEGRAM, "job:default/brief"):
        request = await _first_request(deps, store.create().id, source)
        head, tail = request.messages[0].content.split(AWAY)
        assert (head + tail, tail, request.tools) == (system, date, chat.tools), source
        heard.append(request.messages[0].content)
    assert heard[0] == heard[1]
    for root_source, away in ((TELEGRAM, True), (JOB, True), (CHAT, False)):
        prompt = await _child_prompt(deps, store, root_source)
        assert prompt.count(f"## {CANVAS_CLOSED_TITLE}\n") == int(away), root_source
        assert (AWAY in prompt) is away, root_source
    for root_source in (API, ""):  # told the channel is closed, and nothing about sending
        assert CANVAS_AWAY_BODY not in await _child_prompt(deps, store, root_source)


async def test_the_note_names_only_the_canvas_writes_the_agent_holds(
    deps_factory, store: Store, tmp_path: Path
):
    """An agent that only reads canvases, or only carries them out to a file, has nothing to
    be warned off."""
    for held, expected in (
        ({"artifact_edit", "artifact_read"}, "artifact_edit"),
        ({"artifact_import", "artifact_export"}, "artifact_import"),
        ({"artifact_export", "artifact_read"}, None),
        ({"artifact_list"}, None),
    ):
        tools = [tool for tool in canvas_tools(store, tmp_path) if tool.name in held]
        deps = deps_factory(script=[completion("được")], extra_tools=tools)
        request = await _first_request(deps, store.create().id, API)
        system = request.messages[0].content
        if expected is None:
            assert CANVAS_CLOSED_TITLE not in system
        else:
            assert note(expected) in system


@pytest.mark.parametrize("source", [TELEGRAM, "job:default/brief"])
async def test_an_agent_that_writes_no_canvas_is_told_nothing_about_making_one(
    deps_factory, store: Store, tmp_path: Path, source: str
):
    """Advice on when to make a canvas is for an agent that can make or change one."""
    for held, told in (
        ({"artifact_edit", "artifact_read"}, True),
        ({"artifact_import", "artifact_export"}, True),
        ({"artifact_export", "artifact_read"}, False),
        ({"artifact_list"}, False),
        (set(), False),
    ):
        tools = [tool for tool in canvas_tools(store, tmp_path) if tool.name in held]
        deps = deps_factory(script=[completion("được")], extra_tools=tools)
        system = (await _first_request(deps, store.create().id, source)).messages[0].content
        assert (AWAY in system, CANVAS_CLOSED_TITLE in system) == (told, told), held


@pytest.mark.parametrize("source", [TELEGRAM, API])
def test_the_standing_prompt_has_no_canvas_note(deps_factory, store: Store, source: str):
    """With no conversation there is no turn whose channel or reader a note could speak of."""
    deps = deps_factory(extra_tools=canvas_tools(store))
    set_turn_source(source)
    try:
        assert CANVAS_CLOSED_TITLE not in system_prompt_for(deps)
    finally:
        set_turn_source(CHAT)


def test_the_line_a_telegram_turn_is_taught_is_one_the_chat_sends_a_canvas_for():
    """The note spells the line with `<id>` where the canvas's id goes; with an id there, the
    reply's reader takes it for a canvas to send as a file."""
    taught = "FILE: artifact:<id>"
    assert taught in CANVAS_AWAY_BODY
    prose, media, files = split_reply(f"Xong.\n{taught.replace('<id>', '0123456789ab')}")
    assert (prose, media) == ("Xong.", [])
    assert [artifact_ref(path) for path in files] == ["0123456789ab"]


def test_the_note_says_who_reads_then_when_a_canvas_is_worth_making_then_how_one_is_sent():
    """Three things, in this order. Without who reads the turn the advice has no reason;
    without when to write one, every long answer becomes a canvas nobody sees open; and the
    line that sends one along comes last, for the canvas that was worth making."""
    said = (
        "không ngồi ở web chat",
        "không thấy canvas",
        "khi được dặn",
        "dài và sẽ còn sửa tiếp",
        "trả lời thẳng trong tin nhắn",
        "FILE: artifact:<id>",
        "gửi canvas kèm tin nhắn",
    )
    found = [CANVAS_AWAY_BODY.find(words) for words in said]
    assert -1 not in found and found == sorted(found), dict(zip(said, found, strict=True))


def test_the_note_never_says_its_reader_is_on_telegram():
    """A job hears it too, on a machine with no bot or when its brief is never pushed, and
    its reader then has the web alone. So the reader is said to be away from the web chat,
    and Telegram is named twice and no more: as one of two ways the turn gets read, and as
    the condition the line sends a canvas under."""
    who_reads = CANVAS_AWAY_BODY.partition(". ")[0]
    assert "qua Telegram hoặc xem lại sau" in who_reads
    assert "khi lượt được gửi qua Telegram" in CANVAS_AWAY_BODY
    assert CANVAS_AWAY_BODY.count("Telegram") == 2
    assert "đọc trên Telegram" not in CANVAS_AWAY_BODY


def test_the_refusal_names_no_channel_as_the_only_one_that_opens_a_canvas():
    """It is said to a turn from the inbound API, and the web chat is no longer the only
    place a canvas is written from."""
    assert "web" not in ARTIFACT_CHANNEL_CLOSED


async def test_the_note_lists_exactly_the_tools_a_closed_channel_refuses(
    store: Store, tmp_path: Path
):
    """A canvas tool added later is either refused on a closed channel and named in the
    note, or allowed there and left out of it; a tool with no arguments here fails the test.
    A file comes in as a canvas only where a canvas can be written; one goes out anywhere."""
    conv = turn(store, source=API)
    art = persons_canvas(store, "một\nhai", conv.id)
    put(tmp_path, "notes/a.md", "# Tuần\n")
    arguments = {
        "artifact_create": {"title": "Kế hoạch", "kind": "markdown", "content": "# Tuần"},
        "artifact_list": {},
        "artifact_read": {"id": art},
        "artifact_edit": {"id": art, "old": "một", "new": "ba"},
        "artifact_rewrite": {"id": art, "content": "mới"},
        "artifact_import": {"path": "notes/a.md"},
        "artifact_export": {"id": art, "path": "out/a.md"},
    }
    assert set(arguments) == {tool.name for tool in canvas_tools(store, tmp_path)}
    refused = set()
    for name, args in arguments.items():
        result = await call(store, name, args, root=tmp_path)
        if result.output == TOOL_FAILED.format(error=ARTIFACT_CHANNEL_CLOSED):
            refused.add(name)
        else:
            assert result.ok, (name, result.output)
    assert refused == set(CANVAS_WRITE_TOOLS)
    assert ", ".join(CANVAS_WRITE_TOOLS) == ALL_WRITES
    assert (tmp_path / "out" / "a.md").read_text(encoding="utf-8") == "một\nhai"
    assert [canvas.id for canvas in store.artifacts.list(limit=10)] == [art]
