"""Row shapes. The message log is the durable state of a conversation: an assistant
message whose tool calls have no matching tool messages is unfinished work, and the
agent loop finishes it on the next turn — that is what makes a crash resumable."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from my_agent_crew.llm.types import Message, ToolCall

IDLE = "idle"
AWAITING_APPROVAL = "awaiting_approval"


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    created_at: str
    updated_at: str
    autonomous: bool
    cost_cap_usd: float
    skills: tuple[str, ...]
    spent_usd: float
    unknown_cost_calls: int
    status: str
    agent_id: str = "default"
    channel: str = ""  # "" for the web UI, else e.g. "telegram:<chat_id>"
    summary: str = ""  # short recap written when the next conversation opens
    auto_approve: tuple[str, ...] = ()  # tools the user chose to always allow here

    @property
    def over_budget(self) -> bool:
        return self.cost_cap_usd > 0 and self.spent_usd >= self.cost_cap_usd

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["skills"] = list(self.skills)
        data["auto_approve"] = list(self.auto_approve)
        data["over_budget"] = self.over_budget
        return data

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Conversation:
        return cls(
            id=row["id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            autonomous=bool(row["autonomous"]),
            cost_cap_usd=row["cost_cap_usd"],
            skills=tuple(json.loads(row["skills"])),
            spent_usd=row["spent_usd"],
            unknown_cost_calls=row["unknown_cost_calls"],
            status=row["status"],
            agent_id=row["agent_id"],
            channel=row["channel"],
            summary=row["summary"],
            auto_approve=tuple(json.loads(row["auto_approve"])),
        )


@dataclass(frozen=True)
class StoredMessage:
    id: int
    seq: int
    message: Message
    provider: str | None
    model: str | None
    cost_usd: float | None
    created_at: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        m = self.message
        return {
            "id": self.id,
            "seq": self.seq,
            "role": m.role,
            "content": m.content,
            "tool_calls": [asdict(tc) for tc in m.tool_calls],
            "tool_call_id": m.tool_call_id,
            "name": m.name,
            "provider": self.provider,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> StoredMessage:
        calls = tuple(ToolCall(**tc) for tc in json.loads(row["tool_calls"]))
        message = Message(
            role=row["role"],
            content=row["content"],
            tool_calls=calls,
            tool_call_id=row["tool_call_id"],
            name=row["name"],
        )
        return cls(
            id=row["id"],
            seq=row["seq"],
            message=message,
            provider=row["provider"],
            model=row["model"],
            cost_usd=row["cost_usd"],
            created_at=row["created_at"],
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
        )


@dataclass(frozen=True)
class Approval:
    id: str
    conversation_id: str
    message_id: int
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    status: str
    created_at: str
    expires_at: str | None = None  # None on rows older than the expiry rule
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Approval:
        return cls(
            id=row["id"],
            conversation_id=row["conversation_id"],
            message_id=row["message_id"],
            tool_call_id=row["tool_call_id"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments"]),
            status=row["status"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            resolved_at=row["resolved_at"],
        )
