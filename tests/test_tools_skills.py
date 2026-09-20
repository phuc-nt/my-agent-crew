import pytest

from my_agent_crew.skills.loader import parse_skill
from my_agent_crew.tools import ToolError, ToolRegistry
from my_agent_crew.tools.skills import build_skill_tools


def skills():
    return [
        parse_skill("---\nname: goodreads\ndescription: Đọc kệ sách\n---\nGọi API Goodreads", "g"),
        parse_skill("---\nname: voz\ndescription: Đọc voz\n---\nĐọc thread", "v"),
    ]


async def test_skill_read_returns_the_full_body():
    (tool,) = build_skill_tools(skills())
    assert tool.name == "skill_read"
    assert tool.requires_approval is False
    assert await tool.run({"name": "goodreads"}) == "Gọi API Goodreads"


async def test_skill_read_on_an_unknown_name_lists_what_exists():
    (tool,) = build_skill_tools(skills())
    with pytest.raises(ToolError) as excinfo:
        await tool.run({"name": "nope"})
    message = str(excinfo.value)
    assert "nope" in message and "goodreads" in message and "voz" in message


async def test_skill_read_reports_a_failure_instead_of_raising_through_the_registry():
    registry = ToolRegistry(build_skill_tools(skills()))
    result = await registry.execute("skill_read", {"name": ""})
    assert result.ok is False and "goodreads" in result.output
