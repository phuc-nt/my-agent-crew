"""Tables and the additive migrations that keep an older `agent.sqlite3` usable."""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    autonomous INTEGER NOT NULL DEFAULT 0, cost_cap_usd REAL NOT NULL, skills TEXT NOT NULL,
    spent_usd REAL NOT NULL DEFAULT 0, unknown_cost_calls INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'idle', agent_id TEXT NOT NULL DEFAULT 'default',
    summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, seq INTEGER NOT NULL,
    role TEXT NOT NULL, content TEXT NOT NULL, tool_calls TEXT NOT NULL, tool_call_id TEXT,
    name TEXT, provider TEXT, model TEXT, cost_usd REAL, created_at TEXT NOT NULL,
    UNIQUE (conversation_id, seq)
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, message_id INTEGER NOT NULL,
    tool_call_id TEXT NOT NULL, tool_name TEXT NOT NULL, arguments TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (conversation_id, tool_call_id)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, conversation_id TEXT, source TEXT NOT NULL,
    title TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
    steps TEXT NOT NULL DEFAULT '[]', spent_usd REAL NOT NULL DEFAULT 0,
    unknown_cost_calls INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS job_state (
    job_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_proposals (
    id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
    description TEXT NOT NULL, type TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL,
    source TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT
);
"""

# (table, column, definition) added after the table first shipped.
ADDED_COLUMNS = (
    ("conversations", "agent_id", "TEXT NOT NULL DEFAULT 'default'"),
    ("conversations", "channel", "TEXT NOT NULL DEFAULT ''"),
    ("conversations", "summary", "TEXT NOT NULL DEFAULT ''"),
    ("memory_proposals", "previous_body", "TEXT NOT NULL DEFAULT ''"),
    # Tools this conversation lets through without asking, as a JSON list of names.
    ("conversations", "auto_approve", "TEXT NOT NULL DEFAULT '[]'"),
    # An approval nobody answers by `expires_at` is treated as denied.
    ("approvals", "expires_at", "TEXT"),
    ("approvals", "resolved_at", "TEXT"),
    ("messages", "prompt_tokens", "INTEGER"),
    ("messages", "completion_tokens", "INTEGER"),
    # The parent's tool call that opened this conversation, when an agent delegated it.
    # Lets a turn resumed after an interruption find the child it already started instead
    # of opening a second one.
    ("conversations", "parent_call_id", "TEXT NOT NULL DEFAULT ''"),
)


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for table, column, definition in ADDED_COLUMNS:
        present = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in present:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.commit()
