from pathlib import Path

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


def test_system_prompt_lists_tools_and_skills_in_chosen_language():
    vi = Settings(home="/tmp/x", routes=(Route("fake", "echo"),), language="vi")
    en = Settings(home="/tmp/x", routes=(Route("fake", "echo"),), language="en")
    skill = parse_skill("---\nname: k\n---\nRule K", "k")
    text_vi = build_system_prompt(vi, [skill], ["workspace_read"])
    text_en = build_system_prompt(en, [skill], ["workspace_read"])
    assert "workspace_read" in text_vi and "Rule K" in text_vi and "tiếng Việt" in text_vi
    assert "Rule K" in text_en and "English" in text_en
