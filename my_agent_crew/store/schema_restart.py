"""Tables for what the process once kept in memory only, and now has to find again when it
starts: a host that sleeps when idle starts the process anew on every wake, and what was
counted or sent before the sleep is still true after it. Additive as every table is
(`schema.py` applies these with its own)."""

from __future__ import annotations

RESTART_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_failure_streaks (
    job_id TEXT PRIMARY KEY, count INTEGER NOT NULL, since TEXT NOT NULL, told_at TEXT
);
CREATE TABLE IF NOT EXISTS telegram_told (
    owner TEXT NOT NULL, approval_id TEXT NOT NULL, message_id INTEGER NOT NULL,
    text TEXT NOT NULL, told_at TEXT NOT NULL, reminded INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (owner, approval_id, message_id)
);
CREATE TABLE IF NOT EXISTS job_cap_days (day TEXT PRIMARY KEY, told_at TEXT NOT NULL);
"""
