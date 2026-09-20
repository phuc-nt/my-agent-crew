"""Reading and writing the files an agent already reads at the start of every turn."""

from __future__ import annotations

import pytest

from my_agent_crew.memory import agent_store


def test_memory_md_round_trips_and_creates_its_folder(tmp_path):
    memory_file = tmp_path / "coach" / "MEMORY.md"
    assert agent_store.read_memory_md(memory_file) == ""

    agent_store.write_memory_md(memory_file, "Sếp thích trà.")
    assert agent_store.read_memory_md(memory_file) == "Sếp thích trà."


def test_notes_are_listed_newest_day_first_with_their_size(tmp_path):
    memory_dir = tmp_path / "memory"
    for day, body in (("2026-09-18", "cũ"), ("2026-09-20", "mới nhất"), ("2026-09-19", "giữa")):
        agent_store.write_note(memory_dir, day, body)

    notes = agent_store.list_notes(memory_dir)
    assert [n.day for n in notes] == ["2026-09-20", "2026-09-19", "2026-09-18"]
    assert notes[0].chars == len("mới nhất")
    assert notes[0].to_dict() == {"day": "2026-09-20", "chars": len("mới nhất")}


def test_files_that_are_not_daily_notes_are_ignored(tmp_path):
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "scratch.md").write_text("không phải nhật ký")
    agent_store.write_note(memory_dir, "2026-09-20", "hôm nay")

    assert [n.day for n in agent_store.list_notes(memory_dir)] == ["2026-09-20"]


def test_a_note_round_trips(tmp_path):
    memory_dir = tmp_path / "memory"
    assert agent_store.read_note(memory_dir, "2026-09-20") == ""

    agent_store.write_note(memory_dir, "2026-09-20", "- 08:00 chạy bộ")
    assert agent_store.read_note(memory_dir, "2026-09-20") == "- 08:00 chạy bộ"


def test_listing_notes_of_an_agent_that_has_none(tmp_path):
    assert agent_store.list_notes(tmp_path / "missing") == []


@pytest.mark.parametrize("day", ["../../etc/passwd", "2026-9-20", "hôm nay", "", "2026-09-20.md"])
def test_a_day_that_is_not_a_date_cannot_name_a_file(tmp_path, day):
    """The day becomes a filename, so anything but a date could point outside the folder."""
    with pytest.raises(ValueError):
        agent_store.read_note(tmp_path, day)
    with pytest.raises(ValueError):
        agent_store.write_note(tmp_path, day, "x")
