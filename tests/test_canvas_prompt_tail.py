"""A turn that cannot write a canvas is told so in the tail of its system prompt, before the
model puts a whole document into a call only to have it refused. Every turn of an agent keeps
the same tools and the same prompt up to that tail, so the cached prefix is shared."""

from __future__ import annotations

from pathlib import Path

from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.prompt import system_prompt_for
from my_agent_crew.agent.prompt_frame import today_line
from my_agent_crew.agent.turn_context import API, CHAT, JOB, TELEGRAM, set_turn_source
from my_agent_crew.agents.context import daily_note_path
from my_agent_crew.llm.fake import completion
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_CHANNEL_CLOSED,
    CANVAS_CLOSED_BODY,
    CANVAS_CLOSED_TITLE,
)
from my_agent_crew.tools.artifact_scope import CANVAS_WRITE_TOOLS
from tests.canvas_helpers import call, persons_canvas, put, turn
from tests.conftest import collect
from tests.test_canvas_payload_trim import canvas_tools

ALL_WRITES = "artifact_create, artifact_edit, artifact_rewrite, artifact_import"


def note(tools: str = ALL_WRITES) -> str:
    return f"\n## {CANVAS_CLOSED_TITLE}\n{CANVAS_CLOSED_BODY.format(tools=tools)}\n"


async def _first_request(deps, conv_id: str, source: str, depth: int = 0):
    await collect(run_turn(deps, conv_id, "viết kế hoạch tuần", source=source, depth=depth))
    return deps.chain.providers["scripted"].requests[-1]


async def test_a_turn_that_cannot_write_a_canvas_is_told_so_with_the_same_tools(
    deps_factory, store: Store, tmp_path: Path
):
    """Telegram, a job, the inbound API and a child whose chain began on Telegram hear it,
    after the day's notes and right before the date, so a turn on any channel shares the
    prefix up to there; the web chat and a child of it do not."""
    tools = canvas_tools(store, tmp_path)
    deps = deps_factory(script=[completion("được")] * 6, extra_tools=tools)
    note_path = daily_note_path(deps.agent.memory_dir, deps.settings.today())
    note_path.write_text("- đã chốt lịch chạy sáng thứ bảy\n")
    chat = await _first_request(deps, store.create().id, CHAT)
    system = chat.messages[0].content
    date = today_line(deps.settings, deps.settings.today().isoformat())
    assert system.endswith(date) and CANVAS_CLOSED_TITLE not in system
    assert "lịch chạy sáng thứ bảy" in system
    for source in (TELEGRAM, JOB, API):
        request = await _first_request(deps, store.create().id, source)
        head, tail = request.messages[0].content.split(note())
        assert (head + tail, tail, request.tools) == (system, date, chat.tools), source
    for root_source, closed in ((TELEGRAM, True), (CHAT, False)):
        root = store.create()
        child = store.create(parent_call_id="call-1", root_id=root.id, root_source=root_source)
        request = await _first_request(deps, child.id, f"delegate:{root.id}", depth=1)
        assert (note() in request.messages[0].content) is closed, root_source


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
        request = await _first_request(deps, store.create().id, TELEGRAM)
        system = request.messages[0].content
        if expected is None:
            assert CANVAS_CLOSED_TITLE not in system
        else:
            assert note(expected) in system


def test_the_standing_prompt_has_no_canvas_note(deps_factory, store: Store):
    """With no conversation there is no turn whose channel the note could speak of."""
    deps = deps_factory(extra_tools=canvas_tools(store))
    set_turn_source(TELEGRAM)
    try:
        assert CANVAS_CLOSED_TITLE not in system_prompt_for(deps)
    finally:
        set_turn_source(CHAT)


async def test_the_note_lists_exactly_the_tools_a_closed_channel_refuses(
    store: Store, tmp_path: Path
):
    """A canvas tool added later is either refused on Telegram and named in the note, or
    allowed there and left out of it; a tool with no arguments here fails the test. A file
    comes in as a canvas only where a canvas can be written; one goes out on any channel."""
    conv = turn(store, source=TELEGRAM)
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
