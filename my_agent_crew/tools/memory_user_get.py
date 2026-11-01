"""`user_memory_get`: one fact about the person in full, as of a day.

The prompt carries only the index line of each fact; this is how an agent reads the rest
— who stands behind it, when it holds, where it came from, what it replaced — and how it
answers "what was true on that day". Each read counts as the fact being used
(`fact_recall`), which is what the person sees as the fact's usefulness.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from my_agent_crew import texts, texts_facts
from my_agent_crew.memory import fact_recall, fact_report, user_store
from my_agent_crew.tools.registry import Tool, ToolError

FACT_NAME_SCHEMA = {"type": "string", "description": "tên ngắn dạng chu-de-ngan"}


def build_user_memory_get(user_dir: Path) -> Tool:
    async def get(args: dict[str, Any]) -> str:
        name = str(args.get("name", "")).strip()
        as_of = str(args.get("as_of") or "").strip()
        today = date.today()
        try:
            name = user_store.check_name(name)
            day = date.fromisoformat(as_of) if as_of else today
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        directory = user_store.facts_dir(user_dir)
        current = user_store.read_fact(user_dir, name)
        text = fact_report.report(directory, current, name, day, today)
        if not text:
            if current is None and not as_of:
                return texts.USER_MEMORY_NOT_FOUND.format(name=name)
            return texts_facts.USER_MEMORY_NOTHING_ON.format(name=name, day=day.isoformat())
        fact_recall.bump(directory, [name])
        return text

    return Tool(
        name="user_memory_get",
        description=texts_facts.USER_MEMORY_GET_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "name": FACT_NAME_SCHEMA,
                "as_of": {"type": "string", "description": texts_facts.USER_MEMORY_AS_OF},
            },
            "required": ["name"],
        },
        run=get,
        # Only the recall count changes, and a replayed read counting twice harms nothing.
        replay_safe=True,
    )
