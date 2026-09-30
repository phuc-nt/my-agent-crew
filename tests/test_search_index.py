import sqlite3
from pathlib import Path

from my_agent_crew.llm.types import Message
from my_agent_crew.store import Store
from my_agent_crew.store.connection import connect
from my_agent_crew.store.schema import apply_schema
from my_agent_crew.store.search_index import ensure_search_index


def user(text: str) -> Message:
    return Message(role="user", content=text)


def assistant(text: str) -> Message:
    return Message(role="assistant", content=text)


def tool(text: str) -> Message:
    return Message(role="tool", content=text, tool_call_id="call-1")


def indexed_rowids(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT rowid FROM messages_fts").fetchall()
    return {r[0] for r in rows}


class _NoFts5Connection(sqlite3.Connection):
    """A connection standing in for a SQLite build with no FTS5 module compiled in."""

    def execute(self, sql: str, *args: object, **kwargs: object):
        if "VIRTUAL TABLE" in sql and "fts5" in sql:
            raise sqlite3.OperationalError("no such module: fts5")
        return super().execute(sql, *args, **kwargs)


class _BrokenBackfillConnection(sqlite3.Connection):
    """A connection whose backfill statement always fails, to prove the DDL transaction
    rolls back the table and both triggers instead of leaving a half-built index."""

    def execute(self, sql: str, *args: object, **kwargs: object):
        if sql.strip().startswith("INSERT INTO messages_fts"):
            raise sqlite3.OperationalError("gãy giữa backfill")
        return super().execute(sql, *args, **kwargs)


def test_a_missing_fts5_fails_with_a_clear_message(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "agent.sqlite3", factory=_NoFts5Connection)
    try:
        ensure_search_index(conn)
        raise AssertionError("expected ensure_search_index to fail loudly")
    except RuntimeError as exc:
        assert "fts5" in str(exc).lower()


def test_user_and_assistant_messages_are_indexed_immediately_but_not_tool() -> None:
    store = Store(":memory:")
    conv = store.create()
    store.append(conv.id, user("xin chào"))
    store.append(conv.id, assistant("chào bạn"))
    tool_msg = store.append(conv.id, tool("kết quả công cụ"))

    ids = indexed_rowids(store._conn)

    assert tool_msg.id not in ids
    assert len(ids) == 2


def test_store_delete_removes_the_conversations_rows_from_the_index() -> None:
    store = Store(":memory:")
    conv = store.create()
    store.append(conv.id, user("một câu"))
    store.append(conv.id, assistant("một câu trả lời"))
    assert len(indexed_rowids(store._conn)) == 2

    store.delete(conv.id)

    assert indexed_rowids(store._conn) == set()


def test_backfill_indexes_messages_written_before_the_table_existed(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite3"
    store = Store(db_path)
    conv = store.create()
    store.append(conv.id, user("tin cũ một"))
    store.append(conv.id, assistant("tin cũ hai, đọc lại"))
    store.append(conv.id, tool("tin tool không tính"))
    store._conn.execute("DROP TRIGGER messages_fts_ai")
    store._conn.execute("DROP TRIGGER messages_fts_ad")
    store._conn.execute("DROP TABLE messages_fts")
    store._conn.commit()
    store.close()

    reopened = Store(db_path)

    assert len(indexed_rowids(reopened._conn)) == 2
    # Backfilled rows get the same đ→d fold as the insert trigger, so an existing message
    # is as reachable without accents as one written after the index existed.
    assert [h.snippet for h in reopened.search.find("doc")] == ["tin cũ hai, đọc lại"]


def test_reopening_a_database_twice_does_not_duplicate_the_index(tmp_path: Path) -> None:
    db_path = tmp_path / "agent.sqlite3"
    store = Store(db_path)
    conv = store.create()
    store.append(conv.id, user("chỉ một lần"))
    store.close()

    reopened_once = Store(db_path)
    reopened_once.close()
    reopened_twice = Store(db_path)

    assert len(indexed_rowids(reopened_twice._conn)) == 1


def test_a_failed_backfill_leaves_no_table_or_trigger_and_a_later_run_succeeds(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "agent.sqlite3"
    conn = connect(db_path)
    apply_schema(conn)
    conn.execute(
        "INSERT INTO conversations (id, title, created_at, updated_at, cost_cap_usd, skills)"
        " VALUES ('c1', 't', '2026-09-30T00:00:00+00:00', '2026-09-30T00:00:00+00:00', 0.5, '[]')"
    )
    conn.execute(
        "INSERT INTO messages (conversation_id, seq, role, content, tool_calls, created_at)"
        " VALUES ('c1', 1, 'user', 'trước khi có bảng', '[]', '2026-09-30T00:00:00+00:00')"
    )
    conn.commit()
    conn.execute("DROP TRIGGER messages_fts_ai")
    conn.execute("DROP TRIGGER messages_fts_ad")
    conn.execute("DROP TABLE messages_fts")
    conn.commit()
    conn.close()

    broken = sqlite3.connect(db_path, factory=_BrokenBackfillConnection)
    try:
        ensure_search_index(broken)
        raise AssertionError("expected the broken backfill to raise")
    except sqlite3.OperationalError:
        pass

    tables = {
        r[0]
        for r in broken.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'trigger')"
            " AND name LIKE 'messages_fts%'"
        ).fetchall()
    }
    assert tables == set()
    broken.close()

    clean = connect(db_path)
    ensure_search_index(clean)

    rows = clean.execute("SELECT rowid FROM messages_fts").fetchall()
    assert len(rows) == 1


def test_no_code_updates_the_messages_table() -> None:
    """`messages` is append-only; an UPDATE would slip past the insert/delete triggers and
    leave the search index holding stale text. Only this file's own test fixtures may
    write raw SQL against the table to set up a scenario."""
    root = Path(__file__).resolve().parents[1] / "my_agent_crew"
    offenders = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if "UPDATE messages " in p.read_text(encoding="utf-8")
        or "UPDATE messages\n" in p.read_text(encoding="utf-8")
        or "UPDATE messages\t" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []
