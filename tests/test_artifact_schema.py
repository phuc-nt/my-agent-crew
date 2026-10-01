"""Canvas tables arrive on an older database without touching what it already holds."""

import sqlite3
from pathlib import Path

from my_agent_crew.store.db import Store

CANVAS_TABLES = {"artifacts", "artifact_versions", "conversation_artifacts", "canvas_focus"}
CANVAS_INDEXES = {
    "conversation_artifacts_by_artifact",
    "artifacts_by_updated",
    "artifact_versions_by_conversation",
    "artifact_versions_by_size",
}


def _names(conn: sqlite3.Connection, kind: str) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,))
    return {row[0] for row in rows}


def test_a_new_database_has_every_canvas_table_and_index(store: Store):
    assert CANVAS_TABLES <= _names(store._conn, "table")
    assert CANVAS_INDEXES <= _names(store._conn, "index")


def test_version_payloads_are_the_last_columns_so_metadata_reads_skip_them(store: Store):
    columns = [row[1] for row in store._conn.execute("PRAGMA table_info(artifact_versions)")]
    assert columns[-2:] == ["content", "data"]


def _plan(store: Store, sql: str) -> str:
    return " | ".join(row[3] for row in store._conn.execute(f"EXPLAIN QUERY PLAN {sql}"))


def test_version_sizes_are_summed_from_an_index_without_reading_the_payloads(store: Store):
    """The storage check runs on every canvas write; scanning the table instead would walk
    every page that holds a version's text."""
    for sql in (
        "SELECT COALESCE(SUM(size), 0) FROM artifact_versions",
        "SELECT artifact_id, SUM(size) FROM artifact_versions GROUP BY artifact_id",
    ):
        assert "COVERING INDEX artifact_versions_by_size" in _plan(store, sql)


def test_an_older_database_gains_the_canvas_tables_and_keeps_its_messages(tmp_path: Path):
    path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL,"
        " created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        " autonomous INTEGER NOT NULL DEFAULT 0, cost_cap_usd REAL NOT NULL,"
        " skills TEXT NOT NULL, spent_usd REAL NOT NULL DEFAULT 0,"
        " unknown_cost_calls INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'idle');"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " conversation_id TEXT NOT NULL, seq INTEGER NOT NULL, role TEXT NOT NULL,"
        " content TEXT NOT NULL, tool_calls TEXT NOT NULL, tool_call_id TEXT, name TEXT,"
        " provider TEXT, model TEXT, cost_usd REAL, created_at TEXT NOT NULL,"
        " UNIQUE (conversation_id, seq));"
        "INSERT INTO conversations (id, title, created_at, updated_at, cost_cap_usd, skills)"
        " VALUES ('c1', 'cũ', 't', 't', 0.5, '[]');"
        "INSERT INTO messages (conversation_id, seq, role, content, tool_calls, created_at)"
        " VALUES ('c1', 1, 'user', 'xin chào', '[]', 't');"
    )
    old.commit()
    old.close()

    store = Store(path)

    assert CANVAS_TABLES <= _names(store._conn, "table")
    assert CANVAS_INDEXES <= _names(store._conn, "index")
    [message] = store.history("c1")
    assert message.message.content == "xin chào"
    [row] = store._conn.execute("SELECT context FROM messages").fetchall()
    assert row[0] == ""


def test_opening_the_same_database_twice_changes_nothing_the_second_time(tmp_path: Path):
    path = tmp_path / "agent.sqlite3"
    Store(path).close()
    first = sqlite3.connect(path).execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    Store(path).close()
    second = sqlite3.connect(path).execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    assert first == second
