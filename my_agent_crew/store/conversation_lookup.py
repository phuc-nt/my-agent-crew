"""Finding a conversation by what it relates to rather than by its id: the one an agent
currently holds on a channel, the one before it, or the one a delegating tool call opened.

These are the queries where the answer may legitimately be "none"; the store's own `get`
raises instead, because asking for a conversation by id means you believe it exists.
"""

from __future__ import annotations

import sqlite3
import threading

from my_agent_crew.store.models import Conversation, StoredMessage


def _one(
    conn: sqlite3.Connection, lock: threading.Lock, sql: str, params: tuple[object, ...]
) -> Conversation | None:
    with lock:
        row = conn.execute(sql, params).fetchone()
    return Conversation.from_row(row) if row else None


def latest_for_channel(
    conn: sqlite3.Connection, lock: threading.Lock, agent_id: str, channel: str
) -> Conversation | None:
    """The newest conversation an agent holds on a channel, by creation time. Delegated
    children are skipped: they carry no channel of their own and are not the thread the
    person is in."""
    return _one(
        conn,
        lock,
        "SELECT * FROM conversations WHERE agent_id = ? AND channel = ? AND parent_call_id = ''"
        " ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (agent_id, channel),
    )


def previous_for_channel(
    conn: sqlite3.Connection, lock: threading.Lock, agent_id: str, channel: str, before: str
) -> Conversation | None:
    """The conversation this agent held on the channel right before `before`. Ordered by
    rowid, not `created_at`: two opened in the same millisecond share a timestamp. Delegated
    children are skipped: they carry no channel of their own and are not what the person
    said last."""
    return _one(
        conn,
        lock,
        "SELECT * FROM conversations WHERE agent_id = ? AND channel = ? AND parent_call_id = ''"
        " AND rowid < (SELECT rowid FROM conversations WHERE id = ?)"
        " ORDER BY rowid DESC LIMIT 1",
        (agent_id, channel, before),
    )


def for_parent_call(
    conn: sqlite3.Connection, lock: threading.Lock, parent_call_id: str
) -> Conversation | None:
    """The conversation a given tool call already opened, so a delegating turn that was
    interrupted and resumed picks its child back up instead of starting a second one."""
    if not parent_call_id:
        return None
    return _one(
        conn,
        lock,
        "SELECT * FROM conversations WHERE parent_call_id = ? ORDER BY rowid LIMIT 1",
        (parent_call_id,),
    )


def children_of(
    conn: sqlite3.Connection, lock: threading.Lock, call_ids: tuple[str, ...]
) -> list[Conversation]:
    """Every conversation opened by one of these tool calls, oldest first — what a parent
    turn spawned, for the cost rollup and for showing the tree in the UI."""
    if not call_ids:
        return []
    marks = ",".join("?" * len(call_ids))
    with lock:
        rows = conn.execute(
            f"SELECT * FROM conversations WHERE parent_call_id IN ({marks}) ORDER BY rowid",
            call_ids,
        ).fetchall()
    return [Conversation.from_row(r) for r in rows]


def delegating_call_ids(history: list[StoredMessage], tool_name: str) -> tuple[str, ...]:
    """The ids of the delegating tool calls in a conversation's history.

    A child is linked to the call that opened it, not to the conversation, so finding what
    a conversation delegated is always these two steps. `tool_name` is passed in rather
    than imported: the store does not know what the agents package calls its tools."""
    return tuple(
        call.id
        for stored in history
        for call in stored.message.tool_calls
        if call.name == tool_name
    )
