"""`tool_output_read`: hands back a tool result that the model only saw shortened, by the id
of the call that produced it. Scope is the running conversation alone, and an id that more
than one result shares is refused rather than guessed at."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import set_tool_call_id, set_turn_conversation
from my_agent_crew.llm.types import Message
from my_agent_crew.store import Store
from my_agent_crew.tools.output_read import build_output_read_tool
from my_agent_crew.tools.output_spill import Spill
from my_agent_crew.tools.registry import ToolError, ToolRegistry

CAP = 4000


@pytest.fixture(autouse=True)
def no_leftover_context() -> Iterator[None]:
    yield
    set_turn_conversation("", 0)
    set_tool_call_id("")


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


@pytest.fixture
def spill(tmp_path: Path) -> Spill:
    return Spill(tmp_path)


def _result(call_id: str, content: str) -> Message:
    return Message(role="tool", content=content, tool_call_id=call_id, name="shell_run")


def _read(store: Store, spill: Spill, cap: int = CAP):
    return build_output_read_tool(store, spill, cap).run


async def test_reads_the_original_from_the_spill_file_in_chunks(store: Store, spill: Spill):
    conv = store.create()
    store.append(conv.id, _result("c1", "đã rút gọn"))
    spill.write(conv.id, "c1", "0123456789" * 100)
    set_turn_conversation(conv.id)
    run = _read(store, spill)

    first = await run({"id": "c1", "offset": 0, "limit": 300})
    second = await run({"id": "c1", "offset": 300, "limit": 300})

    assert texts.TOOL_OUTPUT_SOURCE_ORIGINAL in first
    assert "0123456789" * 30 in first and "đã rút gọn" not in first
    assert "offset=300" in first
    assert "0-300/1000" in first and "300-600/1000" in second


async def test_a_stored_copy_is_labelled_as_possibly_shortened(store: Store, spill: Spill):
    conv = store.create()
    store.append(conv.id, _result("c1", "nội dung đã lưu"))
    set_turn_conversation(conv.id)

    out = await _read(store, spill)({"id": "c1"})

    assert texts.TOOL_OUTPUT_SOURCE_STORED in out and "nội dung đã lưu" in out
    assert texts.TOOL_OUTPUT_SOURCE_ORIGINAL not in out


async def test_the_spill_file_wins_over_the_stored_copy(store: Store, spill: Spill):
    conv = store.create()
    store.append(conv.id, _result("c1", "bản cắt"))
    spill.write(conv.id, "c1", "bản gốc đầy đủ")
    set_turn_conversation(conv.id)

    out = await _read(store, spill)({"id": "c1"})

    assert "bản gốc đầy đủ" in out and "bản cắt" not in out


async def test_reading_to_the_end_says_so_and_offers_no_further_read(store: Store, spill: Spill):
    conv = store.create()
    store.append(conv.id, _result("c1", "ngắn"))
    set_turn_conversation(conv.id)

    out = await _read(store, spill)({"id": "c1"})

    assert out.endswith(texts.TOOL_OUTPUT_READ_DONE) and "offset=" not in out


async def test_an_offset_past_the_end_returns_an_empty_segment_marked_finished(
    store: Store, spill: Spill
):
    conv = store.create()
    store.append(conv.id, _result("c1", "ngắn"))
    set_turn_conversation(conv.id)

    out = await _read(store, spill)({"id": "c1", "offset": 999})

    assert out.endswith(texts.TOOL_OUTPUT_READ_DONE) and "ngắn" not in out
    assert out.startswith(
        texts.TOOL_OUTPUT_READ_HEADER.format(
            source=texts.TOOL_OUTPUT_SOURCE_STORED, offset=4, end=4, total=4
        )
    )


async def test_a_negative_offset_reads_from_the_start(store: Store, spill: Spill):
    conv = store.create()
    store.append(conv.id, _result("c1", "ngắn"))
    set_turn_conversation(conv.id)

    out = await _read(store, spill)({"id": "c1", "offset": -3})

    header = texts.TOOL_OUTPUT_READ_HEADER.format(
        source=texts.TOOL_OUTPUT_SOURCE_STORED, offset=0, end=4, total=4
    )
    assert out == header + "ngắn" + texts.TOOL_OUTPUT_READ_DONE


async def test_a_call_id_from_another_conversation_is_not_found(store: Store, spill: Spill):
    mine, other = store.create(), store.create()
    store.append(other.id, _result("c1", "của người khác"))
    spill.write(other.id, "c1", "của người khác, bản gốc")
    set_turn_conversation(mine.id)

    with pytest.raises(ToolError, match="c1"):
        await _read(store, spill)({"id": "c1"})


async def test_an_unknown_id_is_an_error(store: Store, spill: Spill):
    conv = store.create()
    set_turn_conversation(conv.id)

    with pytest.raises(ToolError, match="nope"):
        await _read(store, spill)({"id": "nope"})


async def test_an_id_shared_by_two_results_is_refused(store: Store, spill: Spill):
    conv = store.create()
    store.append(conv.id, _result("c1", "một"))
    store.append(conv.id, _result("c1", "hai"))
    spill.write(conv.id, "c1", "bản gốc của một trong hai")
    set_turn_conversation(conv.id)

    with pytest.raises(ToolError, match="nhiều hơn một"):
        await _read(store, spill)({"id": "c1"})


async def test_no_conversation_in_context_reads_nothing(store: Store, spill: Spill):
    conv = store.create()
    store.append(conv.id, _result("c1", "x"))

    with pytest.raises(ToolError):
        await _read(store, spill)({"id": "c1"})


async def test_a_blank_id_is_an_error(store: Store, spill: Spill):
    set_turn_conversation(store.create().id)

    with pytest.raises(ToolError):
        await _read(store, spill)({"id": "  "})


async def test_one_read_never_exceeds_the_registry_cap_even_when_asked_for_more(
    store: Store, spill: Spill
):
    conv = store.create()
    store.append(conv.id, _result("c" * 32, "x"))
    spill.write(conv.id, "c" * 32, "y" * 50_000)
    set_turn_conversation(conv.id)
    tool = build_output_read_tool(store, spill, 1000)

    result = await ToolRegistry([tool], limit=1000, spill=spill).execute(
        tool.name, {"id": "c" * 32, "limit": 40_000}
    )

    assert result.ok and len(result.output) <= 1000
    assert result.shaped_kind == "none" and "offset=" in result.output


async def test_the_tool_needs_no_approval_and_may_run_alongside_others(store: Store, spill: Spill):
    tool = build_output_read_tool(store, spill, CAP)

    assert tool.name == "tool_output_read"
    assert tool.requires_approval is False and tool.parallel is True
