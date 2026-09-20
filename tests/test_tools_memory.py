from datetime import datetime
from pathlib import Path

from my_agent_crew import texts
from my_agent_crew.memory import user_store
from my_agent_crew.tools.memory import (
    append_daily_note,
    build_memory_tools,
    count_notes,
    search_memory,
)
from my_agent_crew.tools.registry import ToolRegistry


def registry(tmp_path: Path) -> ToolRegistry:
    return ToolRegistry(build_memory_tools(tmp_path / "memory", tmp_path / "MEMORY.md"))


async def test_save_then_search_finds_by_every_term(tmp_path: Path):
    reg = registry(tmp_path)
    await reg.execute("memory_save", {"text": "Người dùng thích cà phê đen buổi sáng"})
    await reg.execute("memory_save", {"text": "Dự án my-crew dùng Python"})
    hit = await reg.execute("memory_search", {"query": "cà phê sáng"})
    miss = await reg.execute("memory_search", {"query": "bóng đá"})
    assert "cà phê đen" in hit.output and "my-crew" not in hit.output
    assert miss.output == texts.MEMORY_EMPTY

    # No note holds both words, so both partial matches are worth showing.
    both = await reg.execute("memory_search", {"query": "cà phê Python"})
    assert "cà phê đen" in both.output and "my-crew" in both.output


async def test_empty_note_is_rejected(tmp_path: Path):
    reg = registry(tmp_path)
    result = await reg.execute("memory_save", {"text": "   "})
    assert result.ok is False and count_notes(tmp_path / "memory") == 0


def test_daily_note_is_a_dated_markdown_file_with_timestamps(tmp_path: Path):
    memory = tmp_path / "memory"
    at = datetime(2026, 9, 19, 8, 5)
    path = append_daily_note(memory, "ghi nhớ A", at)
    append_daily_note(memory, "ghi nhớ B", at.replace(hour=9))
    assert path == memory / "2026-09-19.md"
    text = path.read_text()
    assert text.startswith("# 2026-09-19\n") and "- 08:05 ghi nhớ A" in text
    assert "- 09:05 ghi nhớ B" in text and count_notes(memory) == 2


def test_search_covers_memory_file_and_newest_day_first(tmp_path: Path):
    memory = tmp_path / "memory"
    memory_file = tmp_path / "MEMORY.md"
    memory_file.write_text("# Bền\n- Thích trà xanh\n")
    append_daily_note(memory, "uống trà đá", datetime(2026, 9, 1, 8, 0))
    append_daily_note(memory, "uống trà nóng", datetime(2026, 9, 2, 8, 0))
    hits = search_memory(memory, memory_file, "trà")
    # The source carries the heading the entry sits under, so a hit says where it came from.
    assert [src for src, _ in hits] == [
        "MEMORY.md › Bền",
        "2026-09-02.md › 2026-09-02",
        "2026-09-01.md › 2026-09-01",
    ]
    assert search_memory(memory, memory_file, "") == []


def fact(user_dir: Path, name: str, description: str, body: str) -> None:
    user_store.write_fact(
        user_dir,
        name=name,
        description=description,
        type="preference",
        body=body,
        written_by="coach",
        source="chat",
    )


async def test_search_reaches_the_shared_facts_and_reports_where_they_live(tmp_path: Path):
    user_dir = tmp_path / "owner"
    fact(user_dir, "ca-phe", "Thích cà phê đen", "Uống cà phê đen mỗi sáng.")
    reg = ToolRegistry(build_memory_tools(tmp_path / "memory", tmp_path / "MEMORY.md", user_dir))

    out = await reg.execute("memory_search", {"query": "cà phê"})
    assert "[user/ca-phe.md]" in out.output and "Thích cà phê đen" in out.output


def test_a_fact_matches_on_its_body_too(tmp_path: Path):
    user_dir = tmp_path / "owner"
    fact(user_dir, "ca-phe", "Thói quen sáng", "Uống cà phê đen mỗi sáng.")
    [(source, line)] = search_memory(tmp_path / "memory", tmp_path / "MEMORY.md", "đen", user_dir)
    assert source == "user/ca-phe.md"
    # The description and the body are one thought, so the hit shows both.
    assert line == "Thói quen sáng Uống cà phê đen mỗi sáng."


def test_shared_facts_come_before_the_agents_own_notes(tmp_path: Path):
    user_dir = tmp_path / "owner"
    fact(user_dir, "ca-phe", "Thích cà phê", "đen")
    (tmp_path / "MEMORY.md").write_text("- Sếp thích cà phê sữa", encoding="utf-8")
    hits = search_memory(tmp_path / "memory", tmp_path / "MEMORY.md", "cà phê", user_dir)
    assert [s for s, _ in hits] == ["user/ca-phe.md", "MEMORY.md"]


def test_search_still_works_for_an_agent_with_no_shared_facts(tmp_path: Path):
    (tmp_path / "MEMORY.md").write_text("- Sếp thích cà phê", encoding="utf-8")
    hits = search_memory(tmp_path / "memory", tmp_path / "MEMORY.md", "cà phê")
    assert [s for s, _ in hits] == ["MEMORY.md"]
