"""A tool's answer too long for a script to hold. It is cut at `RAW_LIMIT`, and where the
agent can read a kept output back, all of it is kept first under an id of its own, which
the script is told with where to read on from (`script/nested.py` over
`tools/output_spill.py` and `tools/output_read.py`). Every script here runs in a real
child process."""

from __future__ import annotations

import re
from dataclasses import replace
from textwrap import dedent
from typing import Any

from my_agent_crew import texts
from my_agent_crew import texts_script as t
from my_agent_crew.agent.events import DoneEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.turn_context import set_tool_call_id, set_turn_conversation
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.script.limits import RAW_LIMIT
from my_agent_crew.script.scope import SCRIPT_TOOL
from my_agent_crew.script.tool import script_tool
from my_agent_crew.store import Store
from my_agent_crew.tools.output_read import build_output_read_tool
from my_agent_crew.tools.output_shaping import cut
from my_agent_crew.tools.output_spill import READ_TOOL, SPILL_DIR, Spill
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry
from my_agent_crew.tools.result import ToolResult
from tests.conftest import collect

SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
LONG = RAW_LIMIT + 50_000
KEPT_ID = re.compile(r'tool_output_read\(id="([^"]+)", offset=(\d+)\)')


def numbered(chars: int, mark: str = "") -> str:
    """Text whose every ten characters say where they stand, so a slice proves its place."""
    return "".join(f"{mark}{n:0{9 - len(mark)}d}\n" for n in range(chars // 10))


def told(left: int, kept_as: str) -> str:
    return t.SCRIPT_ANSWER_KEPT.format(left=left, id=kept_as, offset=RAW_LIMIT)


def reads(name: str, answer: Any) -> Tool:
    async def run(arguments: dict[str, Any]) -> Any:
        if isinstance(answer, Exception):
            raise answer
        return answer

    return Tool(name, f"Đọc {name}.", SCHEMA, run, replay_safe=True)


class Held:
    """An agent's tools the way the server hands them out: the store of long outputs is
    there exactly when the agent keeps the tool that reads one back."""

    def __init__(self, home, store: Store, *tools: Tool, reread: bool = True, cap: int = 8000):
        self.home, self.store = home, store
        self.spill = Spill(home)
        held = [*tools, *([build_output_read_tool(store, self.spill, cap)] if reread else [])]
        self.registry = ToolRegistry(held, cap, None, None, self.spill if reread else None)
        self.registry.register(script_tool(lambda: self.registry, []))
        self.conv = store.create()

    async def play(self, source: str, call_id: str = "p1") -> ToolResult:
        """The script as a turn runs it: in a conversation, under the id of the model's call."""
        set_turn_conversation(self.conv.id)
        set_tool_call_id(call_id)
        return await self.registry.execute(SCRIPT_TOOL, {"script": dedent(source)})

    def kept(self, kept_as: str) -> str | None:
        return self.spill.read(self.conv.id, kept_as)

    @property
    def nothing_kept(self) -> bool:
        return not (self.home / SPILL_DIR).exists()


TAIL = """
    got = tools.rows_read()
    print(len(got))
    print(got[-90:])
    """


def shown(handed: str) -> str:
    """What `TAIL` prints of the answer a script was handed."""
    return f"{len(handed)}\n{handed[-90:]}".rstrip("\n")  # a result ends unpadded


async def test_an_answer_too_long_is_handed_cut_and_told_where_the_whole_is_kept(tmp_path, store):
    text = numbered(LONG)
    held = Held(tmp_path, store, reads("rows_read", text))

    result = await held.play(TAIL)

    pointer = told(50_000, "p1.1")
    handed = text[:RAW_LIMIT] + pointer
    assert result.ok and result.output == shown(handed)
    assert pointer == (
        '\n[còn 50000 ký tự, đọc tiếp bằng tools.tool_output_read(id="p1.1", offset=200000)]'
    )
    assert held.kept("p1.1") == text
    # What the script was handed is what it is counted as having received.
    assert result.received_chars == len(handed)


async def test_the_script_reads_on_from_where_its_answer_was_cut(tmp_path, store):
    text = numbered(LONG)
    held = Held(tmp_path, store, reads("rows_read", text))

    result = await held.play(
        """
        tools.rows_read()
        print(tools.tool_output_read(id="p1.1", offset=200000, limit=30))
        """
    )

    source = texts.TOOL_OUTPUT_SOURCE_ORIGINAL
    assert result.ok and result.output == (
        texts.TOOL_OUTPUT_READ_HEADER.format(source=source, offset=200000, end=200030, total=LONG)
        + text[200000:200030]
        + texts.TOOL_OUTPUT_READ_MORE.format(remaining=49970, id="p1.1", next_offset=200030)
    )
    assert [call.name for call in result.calls] == ["rows_read", READ_TOOL]


async def test_an_answer_of_just_the_limit_is_handed_whole_and_not_kept(tmp_path, store):
    text = numbered(RAW_LIMIT)
    held = Held(tmp_path, store, reads("rows_read", text))

    result = await held.play(TAIL)

    assert result.output == shown(text)
    assert held.nothing_kept


async def test_each_long_answer_of_a_script_is_kept_under_a_number_of_its_own(tmp_path, store):
    rows, notes = numbered(LONG, "r"), numbered(LONG + 10_000, "n")
    held = Held(
        tmp_path,
        store,
        reads("rows_read", rows),
        reads("day_read", "hôm nay"),
        reads("notes_read", notes),
    )

    result = await held.play(
        """
        first = tools.rows_read()
        tools.day_read()
        second = tools.notes_read()
        print(first[-90:])
        print(second[-90:])
        """
    )

    assert (
        result.output
        == (rows[:RAW_LIMIT] + told(50_000, "p1.1"))[-90:]
        + "\n"
        + ((notes[:RAW_LIMIT] + told(60_000, "p1.3"))[-90:])
    )
    assert (held.kept("p1.1"), held.kept("p1.2"), held.kept("p1.3")) == (rows, None, notes)


async def test_the_long_answers_of_a_batch_are_each_kept_and_told_apart(tmp_path, store):
    rows, notes = numbered(LONG, "r"), numbered(LONG, "n")
    held = Held(tmp_path, store, reads("rows_read", rows), reads("notes_read", notes))

    result = await held.play(
        """
        answers = tools.batch([{"tool": "rows_read"}, {"tool": "notes_read"}])
        for answer in answers:
            print(answer["output"][:10] + answer["output"][-90:])
        """
    )

    assert result.ok, result.output
    first, second = KEPT_ID.findall(result.output)
    assert first != second and {first[1], second[1]} == {str(RAW_LIMIT)}
    # Each answer names the id its own text is under, whichever call ended first.
    assert result.output.startswith(rows[:10]) and held.kept(first[0]) == rows
    assert held.kept(second[0]) == notes


async def test_another_script_of_the_turn_keeps_its_answers_apart(tmp_path, store):
    rows, notes = numbered(LONG, "r"), numbered(LONG, "n")
    answers = [rows, notes]

    async def next_answer(arguments: dict[str, Any]) -> str:
        return answers.pop(0)

    held = Held(tmp_path, store, Tool("rows_read", "Đọc.", SCHEMA, next_answer, replay_safe=True))

    await held.play(TAIL, "p1")
    again = await held.play(TAIL, "p2")

    assert again.output.endswith(told(50_000, "p2.1"))
    assert (held.kept("p1.1"), held.kept("p2.1")) == (rows, notes)


async def test_an_agent_that_cannot_read_back_gets_the_answer_cut_and_nothing_kept(tmp_path, store):
    text = numbered(LONG)
    held = Held(tmp_path, store, reads("rows_read", text), reread=False)

    result = await held.play(TAIL)

    assert result.output == shown(cut(text, RAW_LIMIT)) and held.nothing_kept
    assert RAW_LIMIT - 10 < len(cut(text, RAW_LIMIT)) <= RAW_LIMIT


async def test_a_script_is_not_pointed_at_a_tool_it_cannot_call(tmp_path, store):
    """The store of long outputs without the tool that reads one back: not how the server
    hands tools out, and no reason to tell a script of an id it cannot use."""
    text, spill = numbered(LONG), Spill(tmp_path)
    registry = ToolRegistry([reads("rows_read", text)], 8000, None, None, spill)
    registry.register(script_tool(lambda: registry, []))
    conv = store.create()
    set_turn_conversation(conv.id)
    set_tool_call_id("p1")

    result = await registry.execute(SCRIPT_TOOL, {"script": dedent(TAIL)})

    assert result.output == shown(cut(text, RAW_LIMIT))
    assert not (tmp_path / SPILL_DIR).exists()


async def test_a_long_failure_is_cut_and_not_kept(tmp_path, store):
    held = Held(tmp_path, store, reads("rows_read", ToolError(numbered(LONG))))

    result = await held.play(
        """
        try:
            tools.rows_read()
        except Exception as error:
            said = str(error)
            print(len(said) <= 200000, "tool_output_read" in said)
        """
    )

    assert result.output == "True False" and held.nothing_kept


async def test_what_reading_back_answers_is_never_kept_again(tmp_path, store):
    """An agent whose own cap is past what a script holds: reading a kept answer back in
    one piece is cut like any long answer, and is not kept as another."""
    text = numbered(LONG)
    held = Held(tmp_path, store, reads("rows_read", text), cap=400_000)

    result = await held.play(
        """
        tools.rows_read()
        back = tools.tool_output_read(id="p1.1", offset=0, limit=260000)
        print(len(back), "p1.2" in back)
        """
    )

    source = texts.TOOL_OUTPUT_SOURCE_ORIGINAL
    whole = (
        texts.TOOL_OUTPUT_READ_HEADER.format(source=source, offset=0, end=LONG, total=LONG)
        + text
        + texts.TOOL_OUTPUT_READ_DONE
    )
    assert result.output == f"{len(cut(whole, RAW_LIMIT))} False"
    assert held.kept("p1.1") == text and held.kept("p1.2") is None


async def test_an_answer_that_could_not_be_kept_is_cut_and_points_nowhere(tmp_path, store):
    text = numbered(LONG)
    held = Held(tmp_path, store, reads("rows_read", text))
    (tmp_path / SPILL_DIR).write_text("một tệp chắn chỗ của thư mục")

    result = await held.play(TAIL)

    assert result.output == shown(cut(text, RAW_LIMIT)) and held.kept("p1.1") is None


async def test_outside_a_turn_no_answer_is_kept(tmp_path, store):
    text = numbered(LONG)
    held = Held(tmp_path, store, reads("rows_read", text))

    result = await held.play(TAIL, call_id="")

    assert result.output == shown(cut(text, RAW_LIMIT)) and held.nothing_kept


async def test_in_a_turn_the_answer_is_kept_under_the_models_own_call(deps_factory, tmp_path):
    """Through the loop: the id the script is told is one the model can read on with too."""
    text = numbered(LONG)
    script = ToolCall("c7", SCRIPT_TOOL, {"script": "print(tools.rows_read()[-90:])"})
    read_on = ToolCall("c8", READ_TOOL, {"id": "c7.1", "offset": 249_980})
    deps = deps_factory(
        script=[
            completion(tool_calls=[script]),
            completion(tool_calls=[read_on]),
            completion("Xong."),
        ]
    )
    spill = Spill(tmp_path)
    tools = ToolRegistry(
        [reads("rows_read", text), build_output_read_tool(deps.store, spill, 8000)],
        8000,
        None,
        None,
        spill,
    )
    tools.register(script_tool(lambda: tools, []))
    deps = replace(deps, tools=tools)
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc hết"))

    first, second = [event for event in events if isinstance(event, ToolResultEvent)]
    assert first.ok and first.output == (text[:RAW_LIMIT] + told(50_000, "c7.1"))[-90:]
    assert spill.read(conv.id, "c7.1") == text
    assert second.ok and text[249_980:] + texts.TOOL_OUTPUT_READ_DONE in second.output
    assert isinstance(events[-1], DoneEvent)


# --- an answer that is not whole, and a call that breaks ---

HALF = "\ud83d"  # half of an emoji, as a server that cut its text between two code units sends


async def test_a_long_answer_with_half_a_character_is_kept_and_read_with_the_half_marked(
    tmp_path, store
):
    """Half of an emoji has no bytes to keep: the whole script ended on it, its calls lost."""
    text = numbered(LONG) + HALF + "hết"
    held = Held(tmp_path, store, reads("rows_read", text), reads("note_read", f"ghi {HALF}"))

    result = await held.play(
        """
        note = tools.note_read()
        got = tools.rows_read()
        print(len(note), len(got))
        """
    )

    whole = numbered(LONG) + "\ufffdhết"
    handed = whole[:RAW_LIMIT] + told(len(whole) - RAW_LIMIT, "p1.2")
    assert (result.ok, result.output) == (True, f"5 {len(handed)}")
    assert [(call.name, call.ok) for call in result.calls] == [
        ("note_read", True),
        ("rows_read", True),
    ]
    assert result.calls[0].output == "ghi \ufffd" and held.kept("p1.2") == whole


async def test_a_call_that_breaks_outside_its_tool_fails_alone_and_the_script_goes_on(
    tmp_path, store, monkeypatch
):
    """Keeping the long answer raises what no tool raised. That call fails, in words the
    script can catch; the calls beside it are answered and every one of them is kept."""
    held = Held(tmp_path, store, reads("rows_read", numbered(LONG)), reads("note_read", "ghi"))

    def broken(conv_id: str, call_id: str, text: str) -> bool:
        raise RuntimeError("đĩa hỏng")

    monkeypatch.setattr(held.spill, "write", broken)

    result = await held.play(
        """
        answers = tools.batch([{"tool": "note_read"}, {"tool": "rows_read"}, {"tool": "note_read"}])
        print([answer["ok"] for answer in answers], answers[1]["error"])
        try:
            tools.rows_read()
        except Exception as error:
            print("bắt được:", error)
        print(tools.note_read())
        """
    )

    failed = texts.TOOL_FAILED.format(error="RuntimeError")
    assert result.ok and result.output == "\n".join(
        [f"[True, False, True] {failed}", f"bắt được: {failed}", "ghi"]
    )
    assert [(call.name, call.ok) for call in result.calls] == [
        ("note_read", True),
        ("rows_read", False),
        ("note_read", True),
        ("rows_read", False),
        ("note_read", True),
    ]
    assert result.calls[1].output == failed and result.received_chars == len(failed) * 2 + 9
