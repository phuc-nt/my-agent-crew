"""How the store opens and writes SQLite: WAL, indexes, and writes that read back."""

import sqlite3
from pathlib import Path

import pytest

from my_agent_crew.llm.types import Message
from my_agent_crew.store import Store
from my_agent_crew.store.connection import connect

EXPECTED_INDEXES = {
    "runs_by_started",
    "runs_by_conversation",
    "conversations_by_agent",
    "conversations_by_channel",
    "approvals_by_conversation",
}


def test_a_file_database_runs_in_wal_mode_with_a_busy_timeout(tmp_path: Path):
    path = tmp_path / "db.sqlite3"
    store = Store(path)
    store.create(title="first")
    assert (tmp_path / "db.sqlite3-wal").exists()
    conn = connect(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    conn.close()
    store.close()


def test_the_hot_queries_have_indexes_and_an_older_database_gains_them(tmp_path: Path):
    path = tmp_path / "db.sqlite3"
    Store(path).close()
    older = sqlite3.connect(path)
    for name in EXPECTED_INDEXES:
        older.execute(f"DROP INDEX {name}")
    older.commit()
    older.close()
    Store(path).close()
    rows = sqlite3.connect(path).execute("SELECT name FROM sqlite_master WHERE type='index'")
    assert EXPECTED_INDEXES <= {row[0] for row in rows}


def test_appending_to_an_unknown_conversation_writes_nothing(store: Store):
    before = store.changes
    with pytest.raises(KeyError):
        store.append("nope", Message(role="user", content="lost"))
    assert store.history("nope") == [] and store.changes == before


def test_the_change_count_moves_on_every_write_and_never_on_a_read(store: Store):
    conv = store.create()
    after_create = store.changes
    store.get(conv.id)
    store.list()
    store.history(conv.id)
    assert store.changes == after_create
    assert store.update(conv.id, title="renamed").title == "renamed"
    assert store.changes > after_create
    with pytest.raises(KeyError):
        store.update("nope", title="x")
    with pytest.raises(KeyError):
        store.add_spend("nope", 0.1)
