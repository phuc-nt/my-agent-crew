from pathlib import Path

from my_agent_crew import texts
from my_agent_crew.agent.prompt import active_skills, build_system_prompt
from my_agent_crew.config import Route, Settings
from my_agent_crew.skills import BUILTIN_DIR, load_skills
from my_agent_crew.skills.loader import parse_skill


def test_builtin_cite_sources_is_always_on():
    skills = load_skills(BUILTIN_DIR)
    names = {s.name: s for s in skills}
    assert names["cite-sources"].always is True
    assert "web_search" in names["cite-sources"].body


def test_home_skill_shadows_builtin_and_adds_new(tmp_path: Path):
    (tmp_path / "cite-sources.md").write_text(
        "---\nname: cite-sources\ndescription: mine\n---\nbody mine\n"
    )
    (tmp_path / "extra.md").write_text("No front matter at all.")
    skills = {s.name: s for s in load_skills(BUILTIN_DIR, tmp_path)}
    assert skills["cite-sources"].body == "body mine"
    assert skills["cite-sources"].always is False
    assert skills["extra"].body == "No front matter at all."


def test_parse_skill_without_front_matter_uses_filename():
    s = parse_skill("just text", "fallback")
    assert (s.name, s.body, s.always) == ("fallback", "just text", False)


def test_active_skills_are_always_plus_attached():
    a = parse_skill("---\nname: a\nalways: true\n---\nA", "a")
    b = parse_skill("---\nname: b\n---\nB", "b")
    c = parse_skill("---\nname: c\n---\nC", "c")
    assert [s.name for s in active_skills([a, b, c], ["c"])] == ["a", "c"]


def test_indexed_skills_are_named_with_a_description_but_not_pasted_in_full():
    attached = parse_skill("---\nname: a\ndescription: Kỹ năng A\n---\nBody A", "a")
    indexed = parse_skill("---\nname: b\ndescription: Kỹ năng B\n---\nBody B", "b")
    settings = Settings(home="/tmp/x", routes=(Route("fake", "echo"),))
    text = build_system_prompt(settings, [attached], ["workspace_read"], skill_index=[indexed])
    assert "Body A" in text
    assert "Body B" not in text
    assert "- b: Kỹ năng B" in text
    assert "skill_read" in text


def test_no_index_section_when_every_skill_is_already_in_the_prompt():
    skill = parse_skill("---\nname: a\ndescription: Kỹ năng A\n---\nBody A", "a")
    settings = Settings(home="/tmp/x", routes=(Route("fake", "echo"),))
    text = build_system_prompt(settings, [skill], ["workspace_read"], skill_index=[])
    assert texts.SKILL_INDEX_HEADING not in text


def test_a_long_description_is_cut_and_a_large_index_keeps_names_only():
    long_one = parse_skill(f"---\nname: a\ndescription: {'x' * 300}\n---\nBody", "a")
    settings = Settings(home="/tmp/x", routes=(Route("fake", "echo"),))
    text = build_system_prompt(settings, [], ["t"], skill_index=[long_one])
    line = next(ln for ln in text.splitlines() if ln.startswith("- a:"))
    assert len(line) < 140 and line.endswith("…")

    many = [
        parse_skill(f"---\nname: s{i}\ndescription: mô tả {i}\n---\nBody", f"s{i}")
        for i in range(45)
    ]
    big = build_system_prompt(settings, [], ["t"], skill_index=many)
    assert "- s0" in big and "mô tả 0" not in big


def test_system_prompt_lists_tools_and_skills_in_chosen_language():
    vi = Settings(home="/tmp/x", routes=(Route("fake", "echo"),), language="vi")
    en = Settings(home="/tmp/x", routes=(Route("fake", "echo"),), language="en")
    skill = parse_skill("---\nname: k\n---\nRule K", "k")
    text_vi = build_system_prompt(vi, [skill], ["workspace_read"])
    text_en = build_system_prompt(en, [skill], ["workspace_read"])
    assert "workspace_read" in text_vi and "Rule K" in text_vi and "tiếng Việt" in text_vi
    assert "Rule K" in text_en and "English" in text_en
