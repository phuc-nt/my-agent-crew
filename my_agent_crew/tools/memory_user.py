"""Tools for what the crew knows about the person, shared by every agent.

Whether a write lands immediately depends on who asked for it. In a chat or Telegram
turn the person is right there and can object, so the fact is written. In a scheduled
job nobody is watching, so the same call becomes a proposal for later review — an
unattended agent should not be able to rewrite the person's profile on its own.

A write that lands is reconciled with the fact already there (`user_store.save_fact`):
the same claim again only adds evidence, a new claim replaces the old one and keeps it
in the history, and an agent's inference that contradicts what the person said becomes
a proposal instead of a silent overwrite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from my_agent_crew import texts, texts_facts
from my_agent_crew.agent.turn_context import (
    person_is_present,
    turn_conversation_id,
    turn_source,
)
from my_agent_crew.memory import user_store
from my_agent_crew.memory.fact_index import BASIS_LABELS
from my_agent_crew.memory.fact_model import INFERRED, SAID
from my_agent_crew.memory.fact_reconcile import CONFIRMED, CREATED, DISPUTED
from my_agent_crew.store import Store
from my_agent_crew.store.memory_proposals import USER_FACT, USER_FORGET
from my_agent_crew.tools.memory_user_get import FACT_NAME_SCHEMA, build_user_memory_get
from my_agent_crew.tools.registry import Tool, ToolError


def _sources() -> tuple[str, ...]:
    conv_id = turn_conversation_id()
    return (f"conv:{conv_id}",) if conv_id else ()


def build_user_memory_tools(user_dir: Path, store: Store, agent_id: str) -> list[Tool]:
    def propose(name: str, description: str, fact_type: str, body: str, reasons: str = "") -> None:
        store.proposals.create(
            agent_id=agent_id,
            kind=USER_FACT,
            name=name,
            description=description,
            type=fact_type,
            body=body,
            source=turn_source(),
            reasons=reasons,
        )

    async def save(args: dict[str, Any]) -> str:
        name = str(args.get("name", "")).strip()
        description = str(args.get("description", "")).strip()
        fact_type = str(args.get("type", "")).strip()
        body = str(args.get("body", "")).strip()
        basis = str(args.get("basis") or SAID).strip().lower()
        if not name or not body:
            raise ToolError("cần cả name và body")
        if basis not in (SAID, INFERRED):
            raise ToolError("basis phải là said hoặc inferred")
        try:
            user_store.check_name(name)
            user_store.check_type(fact_type)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if not person_is_present():
            propose(name, description, fact_type, body)
            return texts.USER_MEMORY_PROPOSED.format(name=name)
        try:
            outcome, fact = user_store.save_fact(
                user_dir,
                name=name,
                description=description,
                type=fact_type,
                body=body,
                written_by=agent_id,
                source=turn_source(),
                basis=basis,
                valid_from=str(args.get("valid_from") or ""),
                valid_until=str(args.get("valid_until") or ""),
                sources=_sources(),
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        if outcome == DISPUTED:
            held = BASIS_LABELS[fact.stands_on]
            why = texts_facts.USER_MEMORY_DISPUTE_REASON.format(held=held, version=fact.version)
            propose(name, description, fact_type, body, why)
            return texts_facts.USER_MEMORY_DISPUTED.format(name=name, held=held)
        if outcome == CREATED:
            return texts_facts.USER_MEMORY_CREATED.format(name=name)
        if outcome == CONFIRMED:
            return texts_facts.USER_MEMORY_CONFIRMED.format(name=name, version=fact.version)
        return texts_facts.USER_MEMORY_SUPERSEDED.format(name=name, version=fact.version)

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
        return texts_facts.USER_MEMORY_RETRACTED.format(name=name)

    day = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
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
                    "basis": {
                        "type": "string",
                        "enum": [SAID, INFERRED],
                        "description": texts_facts.USER_MEMORY_BASIS_DESCRIPTION,
                    },
                    "valid_from": {**day, "description": texts_facts.USER_MEMORY_VALID_FROM},
                    "valid_until": {**day, "description": texts_facts.USER_MEMORY_VALID_UNTIL},
                },
                "required": ["name", "description", "type", "body"],
            },
            run=save,
        ),
        build_user_memory_get(user_dir),
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
