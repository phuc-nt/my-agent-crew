from datetime import datetime
from pathlib import Path

import pytest

from my_agent_crew.memory import user_store


def write(user_dir: Path, name: str, **overrides: object) -> user_store.Fact:
    fields: dict = {
        "description": "Thích trả lời ngắn",
        "type": "preference",
        "body": "Người dùng muốn câu trả lời ngắn gọn.",
        "written_by": "coach",
        "source": "chat",
    }
    fields.update(overrides)
    return user_store.write_fact(user_dir, name, **fields)  # type: ignore[arg-type]


def test_a_fact_round_trips_through_its_file(tmp_path: Path):
    written = write(tmp_path, "tra-loi-ngan")
    [read] = user_store.list_facts(tmp_path)
    assert read == written
    assert read.body == "Người dùng muốn câu trả lời ngắn gọn."
    assert read.written_by == "coach" and read.source == "chat"


def test_writing_the_same_name_updates_in_place_instead_of_adding_a_second_fact(tmp_path: Path):
    write(tmp_path, "tra-loi-ngan", now=datetime(2026, 9, 19, 8, 0))
    write(tmp_path, "tra-loi-ngan", description="Đã đổi ý", now=datetime(2026, 9, 20, 8, 0))
    facts = user_store.list_facts(tmp_path)
    assert len(facts) == 1
    assert facts[0].description == "Đã đổi ý"
    assert facts[0].updated.startswith("2026-09-20")


def test_a_name_that_is_not_a_slug_is_refused_before_anything_is_written(tmp_path: Path):
    with pytest.raises(ValueError):
        write(tmp_path, "Tên Có Dấu Cách")
    with pytest.raises(ValueError):
        write(tmp_path, "")
    assert user_store.list_facts(tmp_path) == []


def test_an_unknown_type_is_refused(tmp_path: Path):
    with pytest.raises(ValueError):
        write(tmp_path, "abc", type="nonsense")


def test_the_index_lists_every_fact_newest_first(tmp_path: Path):
    write(tmp_path, "cu", description="Cũ", now=datetime(2026, 9, 18, 8, 0))
    write(tmp_path, "moi", description="Mới", type="project", now=datetime(2026, 9, 20, 8, 0))
    index = user_store.read_index(tmp_path)
    assert index.splitlines() == [
        "- [Mới](moi.md) · project · coach",
        "- [Cũ](cu.md) · preference · coach",
    ]


def test_forgetting_removes_the_file_and_its_index_line(tmp_path: Path):
    write(tmp_path, "tra-loi-ngan")
    write(tmp_path, "giu-lai", description="Giữ lại")
    assert user_store.delete_fact(tmp_path, "tra-loi-ngan") is True
    assert [f.name for f in user_store.list_facts(tmp_path)] == ["giu-lai"]
    assert "tra-loi-ngan" not in user_store.read_index(tmp_path)


def test_forgetting_something_that_was_never_remembered_says_so(tmp_path: Path):
    assert user_store.delete_fact(tmp_path, "khong-co") is False


def test_a_malformed_fact_file_is_skipped_rather_than_breaking_the_prompt(tmp_path: Path):
    write(tmp_path, "tot")
    broken = user_store.facts_dir(tmp_path) / "hong.md"
    broken.write_text("không có frontmatter gì cả", encoding="utf-8")
    assert [f.name for f in user_store.list_facts(tmp_path)] == ["tot"]


def test_user_md_is_read_when_present_and_empty_otherwise(tmp_path: Path):
    assert user_store.read_user_md(tmp_path) == ""
    (tmp_path / "USER.md").write_text("# Về tôi\n\nTên là Phúc.\n", encoding="utf-8")
    assert user_store.read_user_md(tmp_path) == "# Về tôi\n\nTên là Phúc."
