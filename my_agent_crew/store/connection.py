"""How the store opens SQLite.

The connection runs in WAL mode with `synchronous=NORMAL`: a commit appends to the log
without forcing the main file to disk, which is what makes the many small writes of a
turn cheap. A power cut can lose the last few commits but never corrupts the file; a
process crash loses nothing. WAL is remembered in the file itself, the other settings
are per connection. `busy_timeout` covers a reader opened beside the server, such as a
backup, so the server waits for it instead of failing with "database is locked"."""

from __future__ import annotations

import sqlite3
from pathlib import Path

PRAGMAS = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("busy_timeout", "5000"),
    ("cache_size", "-16000"),
    ("temp_store", "MEMORY"),
)


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    for name, value in PRAGMAS:
        conn.execute(f"PRAGMA {name} = {value}")
    return conn
