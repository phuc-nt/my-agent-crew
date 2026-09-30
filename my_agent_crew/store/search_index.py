"""The FTS5 index over `messages`, built once and kept current by triggers.

An ordinary FTS5 table, not external-content: the indexed text has `đ`/`Đ` already
replaced by `d`/`D` so a search for `doc` reaches `đọc`, which makes the indexed row
differ from `messages.content` and rules out `rebuild` reading the source column back.

Building the table, its triggers and the backfill all happen inside one transaction, so a
crash between `CREATE VIRTUAL TABLE` and the backfill `INSERT` cannot leave an empty index
that a later, ordinary startup mistakes for a finished one and never fills in.
"""

from __future__ import annotations

import sqlite3

from my_agent_crew import texts

# `content` already has its `đ`/`Đ` folded to `d`/`D`, matching what a query goes through
# in `store/search.py`; both trigger bodies and the backfill share the same expression so
# the rule can only drift in one place.
_FOLD_D = "replace(replace({column}, 'đ', 'd'), 'Đ', 'D')"

_CREATE_TABLE = (
    "CREATE VIRTUAL TABLE messages_fts USING fts5(body, tokenize='unicode61 remove_diacritics 2')"
)

# `messages` is append-only (see `store/messages.py`); the only place a row leaves it is
# the explicit `DELETE` in `Store.delete`, which is why there is a delete trigger but
# deliberately no update trigger. Anyone who adds an `UPDATE messages` later must add a
# trigger for it too, and `tests/test_search_index.py` greps for that statement so the gap
# cannot slip in silently.
_CREATE_INSERT_TRIGGER = f"""
CREATE TRIGGER messages_fts_ai AFTER INSERT ON messages
WHEN new.role IN ('user', 'assistant')
BEGIN
    INSERT INTO messages_fts (rowid, body) VALUES (new.id, {_FOLD_D.format(column="new.content")});
END
"""

_CREATE_DELETE_TRIGGER = """
CREATE TRIGGER messages_fts_ad AFTER DELETE ON messages
WHEN old.role IN ('user', 'assistant')
BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
END
"""

_BACKFILL = f"""
INSERT INTO messages_fts (rowid, body)
SELECT id, {_FOLD_D.format(column="content")} FROM messages WHERE role IN ('user', 'assistant')
"""


def ensure_search_index(conn: sqlite3.Connection) -> None:
    """Builds `messages_fts` and its triggers the first time this database is opened.

    Called at the end of `apply_schema`, after its own `commit()`, so this always starts
    with no transaction open. `BEGIN IMMEDIATE` takes the write lock before checking
    whether the table exists, so two connections racing to open the same fresh file cannot
    both decide to build it.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'messages_fts'"
        ).fetchone()
        if exists is not None:
            conn.rollback()
            return
        conn.execute(_CREATE_TABLE)
        conn.execute(_CREATE_INSERT_TRIGGER)
        conn.execute(_CREATE_DELETE_TRIGGER)
        conn.execute(_BACKFILL)
        conn.commit()
    except sqlite3.OperationalError as exc:
        conn.rollback()
        if "fts5" in str(exc).lower() or "no such module" in str(exc).lower():
            raise RuntimeError(texts.SEARCH_INDEX_NO_FTS5) from exc
        raise
    except Exception:
        conn.rollback()
        raise
