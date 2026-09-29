"""Model calls made beside a turn rather than by it.

The turn loop writes each completion to the message log, which is the usage ledger. The
other calls — naming a conversation, recapping it, summarising a long tool output, reading
a picture or a scanned page, consolidating memory, compiling the wiki — are billed just
the same, so each one is written here with what it was for, and the ledger reads both
tables. Only figures are kept: a prompt can hold anything, a ledger row never does."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

# What a side call was for. A fixed set, so the ledger groups by something a person can
# read and a call site that invents a new word fails where it is written.
PURPOSES = frozenset(
    {"title", "session_summary", "tool_summary", "image", "pdf", "consolidate", "wiki"}
)


@dataclass(frozen=True)
class SideCall:
    agent_id: str
    purpose: str
    provider: str
    model: str
    # None when the provider did not say what the call cost, or the call was abandoned
    # before it answered; the ledger counts those apart instead of guessing.
    cost_usd: float | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    # The conversation the call was made for; None for work that belongs to none, such as
    # a nightly consolidation.
    conversation_id: str | None = None


class SideCallStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def record(self, call: SideCall, stamp: str | None = None) -> None:
        """`stamp` is the UTC time of the call, now unless given, like a message's."""
        if call.purpose not in PURPOSES:
            raise ValueError(f"unknown side call purpose: {call.purpose!r}")
        stamp = stamp or datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO side_calls (agent_id, conversation_id, purpose, provider, model,"
                " cost_usd, prompt_tokens, completion_tokens, cached_tokens, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    call.agent_id,
                    call.conversation_id,
                    call.purpose,
                    call.provider,
                    call.model,
                    call.cost_usd,
                    call.prompt_tokens,
                    call.completion_tokens,
                    call.cached_tokens,
                    stamp,
                ),
            )
            self._conn.commit()

    def for_conversation(self, conv_id: str) -> list[SideCall]:
        """What was spent beside this conversation's turns, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM side_calls WHERE conversation_id = ? ORDER BY id", (conv_id,)
            ).fetchall()
        return [
            SideCall(
                agent_id=r["agent_id"],
                purpose=r["purpose"],
                provider=r["provider"],
                model=r["model"],
                cost_usd=r["cost_usd"],
                prompt_tokens=r["prompt_tokens"],
                completion_tokens=r["completion_tokens"],
                cached_tokens=r["cached_tokens"],
                conversation_id=r["conversation_id"],
            )
            for r in rows
        ]
