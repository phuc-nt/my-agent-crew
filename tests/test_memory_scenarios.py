"""The regression corpus of the facts about the person: the stories a memory must get
right, each told as the writes it is made of and what must be true afterwards.

A change to reconciliation, validity or the index that breaks one of these breaks what
the crew believes about the person, so these are kept as scenarios, not unit checks.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from my_agent_crew.memory import fact_history, user_store
from my_agent_crew.memory.fact_reconcile import CONFIRMED, CREATED, DISPUTED, SUPERSEDED


def say(user_dir: Path, name: str, body: str, when: datetime, **extra):
    """One write, by default the person saying it in a chat."""
    extra.setdefault("description", body)
    return user_store.save_fact(
        user_dir,
        name=name,
        type=extra.pop("type", "preference"),
        body=body,
        written_by=extra.pop("written_by", "coach"),
        source="chat",
        now=when,
        **extra,
    )


def on(user_dir: Path, name: str, day: date):
    directory = user_store.facts_dir(user_dir)
    held = fact_history.as_of(
        user_store.read_fact(user_dir, name), fact_history.versions(directory, name), day
    )
    return held.body if held else None


def test_a_changed_taste_replaces_the_old_one_and_remembers_it(tmp_path: Path):
    say(tmp_path, "do-uong", "Thích trà", datetime(2026, 3, 1, 9))
    outcome, fact = say(tmp_path, "do-uong", "Chuyển sang cà phê", datetime(2026, 9, 1, 9))

    assert outcome == SUPERSEDED and fact.version == 2
    assert "Chuyển sang cà phê" in user_store.read_index(tmp_path, date(2026, 9, 2))
    assert "Thích trà" not in user_store.read_index(tmp_path, date(2026, 9, 2))
    assert on(tmp_path, "do-uong", date(2026, 5, 1)) == "Thích trà"
    assert on(tmp_path, "do-uong", date(2026, 10, 1)) == "Chuyển sang cà phê"


def test_a_job_change_announced_ahead_holds_only_from_its_day(tmp_path: Path):
    say(tmp_path, "cong-ty", "Làm ở công ty A", datetime(2026, 1, 5, 9), type="profile")
    outcome, _ = say(
        tmp_path,
        "cong-ty",
        "Làm ở công ty B",
        datetime(2026, 11, 1, 9),
        type="profile",
        valid_from="2026-12-01",
    )

    assert outcome == SUPERSEDED
    before = user_store.read_index(tmp_path, date(2026, 11, 15))
    assert before.startswith("- [Làm ở công ty A](cong-ty.md)")
    assert "→ từ 2026-12-01: Làm ở công ty B" in before
    assert user_store.read_index(tmp_path, date(2026, 12, 1)).startswith(
        "- [Làm ở công ty B](cong-ty.md)"
    )
    assert on(tmp_path, "cong-ty", date(2026, 11, 30)) == "Làm ở công ty A"
    assert on(tmp_path, "cong-ty", date(2026, 12, 1)) == "Làm ở công ty B"


def test_an_inference_does_not_overwrite_what_the_person_said(tmp_path: Path):
    say(tmp_path, "an-chay", "Ăn chay thứ hai", datetime(2026, 8, 1, 9))
    outcome, held = say(
        tmp_path, "an-chay", "Đã bỏ ăn chay", datetime(2026, 9, 1, 9), basis="inferred"
    )

    assert outcome == DISPUTED and held.body == "Ăn chay thứ hai"
    assert user_store.read_fact(tmp_path, "an-chay").body == "Ăn chay thứ hai"
    assert fact_history.versions(user_store.facts_dir(tmp_path), "an-chay") == []


def test_an_inference_may_replace_another_inference(tmp_path: Path):
    say(tmp_path, "gio-ngu", "Ngủ lúc 23h", datetime(2026, 8, 1, 9), basis="inferred")
    outcome, _ = say(tmp_path, "gio-ngu", "Ngủ lúc 0h", datetime(2026, 9, 1, 9), basis="inferred")
    assert outcome == SUPERSEDED


def test_saying_the_same_thing_again_adds_evidence_not_a_version(tmp_path: Path):
    say(
        tmp_path,
        "ngu-som",
        "Ngủ trước 23h",
        datetime(2026, 8, 1, 9),
        basis="inferred",
        sources=("conv:a",),
    )
    outcome, fact = say(
        tmp_path, "ngu-som", "Ngủ trước 23h", datetime(2026, 9, 1, 9), sources=("conv:b",)
    )

    assert outcome == CONFIRMED and fact.version == 1
    assert fact.sources == ("conv:a", "conv:b")
    assert fact.stands_on == "said" and fact.confirmed == "2026-09-01T09:00:00"
    assert fact.updated == "2026-08-01T09:00:00"


def test_retract_keeps_the_history_and_purge_erases_it(tmp_path: Path):
    directory = user_store.facts_dir(tmp_path)
    say(tmp_path, "benh-an", "Dị ứng tôm", datetime(2026, 8, 1, 9))
    assert user_store.delete_fact(tmp_path, "benh-an", now=datetime(2026, 9, 1, 9))

    assert user_store.read_fact(tmp_path, "benh-an") is None
    assert "benh-an" not in user_store.read_index(tmp_path)
    assert [v.fact.name for v in fact_history.retracted(directory)] == ["benh-an"]
    assert on(tmp_path, "benh-an", date(2026, 8, 15)) == "Dị ứng tôm"

    assert user_store.purge_fact(tmp_path, "benh-an")
    assert fact_history.versions(directory, "benh-an") == []
    assert fact_history.retracted(directory) == []


def test_a_fact_past_its_last_day_leaves_the_prompt(tmp_path: Path):
    say(
        tmp_path,
        "chuyen-di",
        "Đang ở Đà Nẵng",
        datetime(2026, 10, 1, 9),
        type="project",
        valid_until="2026-10-05",
    )

    assert "Đang ở Đà Nẵng" in user_store.read_index(tmp_path, date(2026, 10, 5))
    assert "đến 2026-10-05" in user_store.read_index(tmp_path, date(2026, 10, 5))
    assert user_store.read_index(tmp_path, date(2026, 10, 6)) == ""
    assert user_store.read_fact(tmp_path, "chuyen-di") is not None


def test_a_fact_written_before_bases_existed_keeps_its_old_standing(tmp_path: Path):
    directory = user_store.facts_dir(tmp_path)
    directory.mkdir(parents=True)
    for name, who in (("tu-web", "web"), ("tu-agent", "coach")):
        (directory / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: Cũ\ntype: profile\nwritten_by: {who}\n"
            "source: chat\nupdated: '2026-01-01T09:00:00'\n---\n\nCũ\n",
            encoding="utf-8",
        )

    assert user_store.read_fact(tmp_path, "tu-web").stands_on == "operator"
    agent_fact = user_store.read_fact(tmp_path, "tu-agent")
    assert agent_fact.stands_on == "inferred" and agent_fact.version == 1
    outcome, _ = say(tmp_path, "tu-web", "Mới", datetime(2026, 9, 1), basis="inferred")
    assert outcome == DISPUTED
    outcome, _ = say(tmp_path, "tu-agent", "Mới", datetime(2026, 9, 1), basis="inferred")
    assert outcome == SUPERSEDED


def test_a_fact_retracted_then_written_again_continues_its_versions(tmp_path: Path):
    say(tmp_path, "the-thao", "Chạy bộ", datetime(2026, 8, 1, 9))
    user_store.delete_fact(tmp_path, "the-thao", now=datetime(2026, 8, 10, 9))
    outcome, fact = say(tmp_path, "the-thao", "Bơi", datetime(2026, 9, 1, 9))

    assert outcome == CREATED and fact.version == 2
