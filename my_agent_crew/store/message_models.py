"""The row shape of one message. The message log is the durable state of a conversation:
an assistant message whose tool calls have no matching tool messages is unfinished work,
and the agent loop finishes it on the next turn — that is what makes a crash resumable."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from my_agent_crew.llm.types import Message, ToolCall


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
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        m = self.message
        return {
            "id": self.id,
            "seq": self.seq,
            "role": m.role,
            "content": m.content,
            "tool_calls": [tc.to_dict() for tc in m.tool_calls],
            "tool_call_id": m.tool_call_id,
            "name": m.name,
            "provider": self.provider,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
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
            reasoning_tokens=row["reasoning_tokens"],
            cached_tokens=row["cached_tokens"],
        )
