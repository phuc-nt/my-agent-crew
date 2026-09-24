"""Tools for what the crew knows about the person, shared by every agent.

Whether a write lands immediately depends on who asked for it. In a chat or Telegram
turn the person is right there and can object, so the fact is written. In a scheduled
job nobody is watching, so the same call becomes a proposal for later review — an
unattended agent should not be able to rewrite the person's profile on its own.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import person_is_present, turn_source
from my_agent_crew.memory import user_store
from my_agent_crew.store import Store
from my_agent_crew.store.memory_proposals import USER_FACT, USER_FORGET
from my_agent_crew.tools.registry import Tool, ToolError

FACT_NAME_SCHEMA = {"type": "string", "description": "tên ngắn dạng chu-de-ngan"}


def build_user_memory_tools(user_dir: Path, store: Store, agent_id: str) -> list[Tool]:
    async def save(args: dict[str, Any]) -> str:
        name = str(args.get("name", "")).strip()
        description = str(args.get("description", "")).strip()
        fact_type = str(args.get("type", "")).strip()
        body = str(args.get("body", "")).strip()
        if not name or not body:
            raise ToolError("cần cả name và body")
        try:
            user_store.check_name(name)
            user_store.check_type(fact_type)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if not person_is_present():
            store.proposals.create(
                agent_id=agent_id,
                kind=USER_FACT,
                name=name,
                description=description,
                type=fact_type,
                body=body,
                source=turn_source(),
            )
            return texts.USER_MEMORY_PROPOSED.format(name=name)
        user_store.write_fact(
            user_dir,
            name=name,
            description=description,
            type=fact_type,
            body=body,
            written_by=agent_id,
            source=turn_source(),
        )
        return texts.USER_MEMORY_SAVED.format(name=name)

    async def forget(args: dict[str, Any]) -> str:
        name = str(args.get("name", "")).strip()
        try:
            user_store.check_name(name)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if not person_is_present():
            store.proposals.create(
                agent_id=agent_id, kind=USER_FORGET, name=name, source=turn_source()
            )
            return texts.USER_MEMORY_FORGET_PROPOSED.format(name=name)
        if not user_store.delete_fact(user_dir, name):
            return texts.USER_MEMORY_NOT_FOUND.format(name=name)
        return texts.USER_MEMORY_FORGOTTEN.format(name=name)

    return [
        Tool(
            name="user_memory_save",
            description=texts.USER_MEMORY_SAVE_DESCRIPTION + texts.MEMORY_IS_NOT_A_LEDGER,
            parameters={
                "type": "object",
                "properties": {
                    "name": FACT_NAME_SCHEMA,
                    "description": {"type": "string", "description": "một dòng tóm tắt"},
                    "type": {"type": "string", "enum": list(user_store.FACT_TYPES)},
                    "body": {"type": "string", "description": "nội dung, Markdown"},
                },
                "required": ["name", "description", "type", "body"],
            },
            run=save,
        ),
        Tool(
            name="user_memory_forget",
            description=texts.USER_MEMORY_FORGET_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {"name": FACT_NAME_SCHEMA},
                "required": ["name"],
            },
            run=forget,
        ),
    ]
