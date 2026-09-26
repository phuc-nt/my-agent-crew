"""Persona files and memory enter the system prompt, re-read every turn."""

from dataclasses import replace
from datetime import date
from pathlib import Path

from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.context import (
    MAX_SECTION_CHARS,
    MAX_USER_SECTION_CHARS,
    bootstrap_sections,
    turn_tail_sections,
)
from my_agent_crew.config import Settings
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory import user_store
from my_agent_crew.texts import USER_FACTS_SECTION_TITLE, USER_MD_SECTION_TITLE
from tests.conftest import collect


def test_sections_follow_persona_memory_daily_order(settings: Settings):
    profile = default_profile(settings)
    home = settings.home
    (home / "memory").mkdir(parents=True)
    (home / "SOUL.md").write_text("Tôi kiên nhẫn.")
    (home / "IDENTITY.md").write_text("   ")
    (home / "MEMORY.md").write_text("Người dùng tên Phúc.")
    (home / "memory" / "2026-09-18.md").write_text("# 2026-09-18\n- 08:00 chạy bộ")
    (home / "memory" / "2026-09-19.md").write_text("# 2026-09-19\n- 07:00 dậy sớm")
    (home / "memory" / "2026-09-10.md").write_text("cũ, không đọc")
    sections = bootstrap_sections(profile)
    assert [title for title, _ in sections] == ["SOUL.md", "MEMORY.md"]
    assert sections[0][1] == "Tôi kiên nhẫn."
    # The notes of yesterday and today change daily, so they ride at the tail instead.
    tail = turn_tail_sections(profile, today=date(2026, 9, 19))
    assert [title for title, _ in tail] == ["memory/2026-09-18.md", "memory/2026-09-19.md"]


def test_the_previous_summary_opens_the_tail_and_is_absent_when_empty(settings: Settings):
    profile = default_profile(settings)
    (settings.home / "memory").mkdir(parents=True)
    (settings.home / "memory" / "2026-09-19.md").write_text("- 07:00 dậy sớm")
    tail = turn_tail_sections(profile, date(2026, 9, 19), "Đã bàn về giấc ngủ.", "18/9 22:00")
    assert tail[0] == ("Cuộc trước (lần cuối 18/9 22:00)", "Đã bàn về giấc ngủ.")
    assert [title for title, _ in tail[1:]] == ["memory/2026-09-19.md"]
    assert turn_tail_sections(profile, date(2026, 9, 19), "   ", "") == [
        ("memory/2026-09-19.md", "- 07:00 dậy sớm")
    ]


def test_oversized_section_is_capped(settings: Settings):
    settings.home.mkdir(parents=True)
    (settings.home / "AGENTS.md").write_text("x" * (MAX_SECTION_CHARS + 500))
    [(_, body)] = bootstrap_sections(default_profile(settings))
    assert len(body) == MAX_SECTION_CHARS + 2 and body.endswith("…")


async def test_persona_and_memory_reach_the_model_each_turn(deps_factory):
    deps = deps_factory(script=[completion("ok"), completion("ok")])
    home: Path = deps.settings.home
    (home / "SOUL.md").write_text("Tên tôi là Pong.")
    conv = deps.store.create()
    await collect(run_turn(deps, conv.id, "chào"))
    (home / "MEMORY.md").write_text("Sếp thích trà.")
    await collect(run_turn(deps, conv.id, "nữa"))
    first, second = (r.messages[0].content for r in deps.chain.providers["scripted"].requests)
    assert "## SOUL.md\nTên tôi là Pong." in first
    assert "Sếp thích trà." not in first and "Sếp thích trà." in second
    assert deps.agent.name in second and date.today().isoformat() in second


def _write_fact(settings: Settings, name: str, description: str) -> None:
    user_store.write_fact(
        settings.user_dir,
        name=name,
        description=description,
        type="preference",
        body="chi tiết",
        written_by="coach",
        source="chat",
    )


def test_the_shared_user_sections_sit_between_persona_and_memory(settings: Settings):
    home = settings.home
    (home / "memory").mkdir(parents=True)
    (home / "SOUL.md").write_text("Tôi kiên nhẫn.")
    (home / "MEMORY.md").write_text("Ghi nhớ riêng.")
    settings.user_dir.mkdir(parents=True, exist_ok=True)
    (settings.user_dir / "USER.md").write_text("Phúc, làm sản phẩm.")
    _write_fact(settings, "ngu-som", "Ngủ trước 23h")

    sections = bootstrap_sections(default_profile(settings))
    assert [title for title, _ in sections] == [
        "SOUL.md",
        USER_MD_SECTION_TITLE,
        USER_FACTS_SECTION_TITLE,
        "MEMORY.md",
    ]
    assert sections[1][1] == "Phúc, làm sản phẩm."
    assert "Ngủ trước 23h" in sections[2][1] and "ngu-som.md" in sections[2][1]


def test_the_prompt_carries_the_index_not_the_facts_themselves(settings: Settings):
    _write_fact(settings, "ngu-som", "Ngủ trước 23h")
    [(_, body)] = bootstrap_sections(default_profile(settings))
    assert "chi tiết" not in body


def test_no_user_section_appears_when_nothing_is_known(settings: Settings):
    settings.home.mkdir(parents=True)
    (settings.home / "SOUL.md").write_text("Tôi kiên nhẫn.")
    assert [t for t, _ in bootstrap_sections(default_profile(settings))] == ["SOUL.md"]


def test_the_user_sections_are_capped_harder_than_the_rest(settings: Settings):
    settings.user_dir.mkdir(parents=True, exist_ok=True)
    (settings.user_dir / "USER.md").write_text("x" * (MAX_USER_SECTION_CHARS + 500))
    [(_, body)] = bootstrap_sections(default_profile(settings))
    assert len(body) == MAX_USER_SECTION_CHARS + 2 and body.endswith("…")
    assert MAX_USER_SECTION_CHARS < MAX_SECTION_CHARS


def test_every_agent_sees_the_same_user_memory(settings: Settings):
    _write_fact(settings, "ngu-som", "Ngủ trước 23h")
    coach = replace(default_profile(settings), id="coach", name="Coach")
    assert coach.settings.user_dir == settings.user_dir
    titles = [t for t, _ in bootstrap_sections(coach)]
    assert USER_FACTS_SECTION_TITLE in titles
