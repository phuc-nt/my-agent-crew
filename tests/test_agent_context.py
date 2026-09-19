"""Persona files and memory enter the system prompt, re-read every turn."""

from datetime import date
from pathlib import Path

from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.context import MAX_SECTION_CHARS, bootstrap_sections
from my_agent_crew.config import Settings
from my_agent_crew.llm.fake import completion
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
    sections = bootstrap_sections(profile, today=date(2026, 9, 19))
    assert [title for title, _ in sections] == [
        "SOUL.md",
        "MEMORY.md",
        "memory/2026-09-18.md",
        "memory/2026-09-19.md",
    ]
    assert sections[0][1] == "Tôi kiên nhẫn."


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
