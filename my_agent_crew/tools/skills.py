"""Progressive disclosure for skills: the system prompt only lists the skills that are
loaded but not attached, and `skill_read` fetches one in full when the model decides it
needs it. Attached and `always` skills are already in the prompt, reading them is harmless."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from my_agent_crew import texts
from my_agent_crew.skills import Skill
from my_agent_crew.tools.registry import Tool, ToolError

READ_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {"name": {"type": "string", "description": "Tên kỹ năng trong danh sách."}},
    "required": ["name"],
}


def build_skill_tools(skills: Sequence[Skill]) -> list[Tool]:
    by_name = {skill.name: skill for skill in skills}

    async def read(arguments: dict[str, Any]) -> str:
        name = str(arguments.get("name") or "").strip()
        skill = by_name.get(name)
        if skill is None:
            raise ToolError(texts.SKILL_UNKNOWN.format(name=name, names=", ".join(by_name)))
        return skill.body

    return [Tool("skill_read", texts.SKILL_READ_DESCRIPTION, READ_PARAMETERS, read)]
