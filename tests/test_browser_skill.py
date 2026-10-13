"""The sample skill that teaches the browser's working loop names tools and parameters as
they are: a tool renamed or taken away must not leave the skill sending a model after it."""

from __future__ import annotations

import re
from pathlib import Path

from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.browser.tools import build_browser_tools
from my_agent_crew.config_browser import BROWSER_ACT, BrowserSettings
from my_agent_crew.skills.loader import load_skills

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "examples" / "skills"
CALL = re.compile(r"\b(browser_[a-z_]+)\(([^)]*)\)")


def test_the_skill_names_every_browser_tool_with_parameters_that_tool_takes(tmp_path):
    settings = BrowserSettings(enabled=True, mode=BROWSER_ACT)
    pool = BrowserPool(tmp_path / "browser", settings)
    built = build_browser_tools(pool, "coach", settings, tmp_path, 20_000)
    tools = {tool.name: tool.parameters["properties"] for tool in built}
    skills = load_skills(EXAMPLES, which=lambda _: "/usr/bin/true")
    (skill,) = [found for found in skills if found.name == "browser-use"]

    assert set(re.findall(r"\bbrowser_[a-z_]+", skill.body)) == set(tools)
    shown = [
        (name, part.split("=")[0].strip())
        for name, inside in CALL.findall(skill.body)
        for part in inside.split(",")
    ]
    assert {name for name, _param in shown} >= {"browser_navigate", "browser_act", "browser_tabs"}
    for name, param in shown:
        assert param in tools[name], f"{name} takes no `{param}`"
    # It is read by a model at work: short enough to be read whole.
    assert len(skill.body) < 4_000 and "[new]" in skill.body
