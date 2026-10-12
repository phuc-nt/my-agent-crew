"""What an agent's scripts keep from one run to the next (`store` and `load` in a script).

A row is one key of one namespace of one agent, with its value as JSON text. A namespace is
the conversation or the job a script ran for (`script/store_session.py` says which), and an
agent never reads another's. Nothing is written while a script runs: what it wrote is applied
once it ended well, all of it in one transaction, and only when the namespace then still
holds no more than it may.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass

from my_agent_crew.store.stamps import now_iso

CONVERSATION, JOB = "conv:", "job:"


def conversation_namespace(conversation_id: str) -> str:
    return CONVERSATION + conversation_id


def job_namespace(schedule_id: str) -> str:
    return JOB + schedule_id


def held_chars(held: Mapping[str, str]) -> int:
    """What a namespace holds, counted as its limit counts it: every key and every value."""
    return sum(len(key) + len(text) for key, text in held.items())


@dataclass(frozen=True)
class KeptValue:
    namespace: str
    key: str
    text: str  # the value as JSON
    updated_at: str


class ScriptStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def read(self, agent_id: str, namespace: str) -> dict[str, str]:
        """Every key of one namespace, with its value as JSON text."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value_json FROM script_store WHERE agent_id = ? AND namespace = ?",
                (agent_id, namespace),
            ).fetchall()
        return {row["key"]: row["value_json"] for row in rows}

    def kept_by(self, agent_id: str) -> list[KeptValue]:
        """All one agent keeps, for the owner's screens: by namespace, then by key."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT namespace, key, value_json, updated_at FROM script_store"
                " WHERE agent_id = ? ORDER BY namespace, key",
                (agent_id,),
            ).fetchall()
        return [KeptValue(*row) for row in rows]

    def value(self, agent_id: str, namespace: str, key: str) -> KeptValue | None:
        """One key of one namespace as it is kept, or None for a key that holds nothing."""
        with self._lock:
            row = self._conn.execute(
                "SELECT namespace, key, value_json, updated_at FROM script_store"
                " WHERE agent_id = ? AND namespace = ? AND key = ?",
                (agent_id, namespace, key),
            ).fetchone()
        return None if row is None else KeptValue(*row)

    def _drop(self, where: str, named: tuple[str, ...]) -> int:
        with self._lock:
            gone = self._conn.execute(f"DELETE FROM script_store WHERE {where}", named).rowcount
            self._conn.commit()
        return gone

    def forget(self, agent_id: str, namespace: str, key: str | None = None) -> int:
        """Drops one key of a namespace, or all the namespace holds when no key is named:
        how many rows went. The owner's doing and never a script's. A script running
        meanwhile goes by what it saw when it first asked, and its end writes only the keys
        it wrote itself (`apply`), so nothing it merely read comes back."""
        if key is None:
            return self._drop("agent_id = ? AND namespace = ?", (agent_id, namespace))
        return self._drop("agent_id = ? AND namespace = ? AND key = ?", (agent_id, namespace, key))

    def forget_agent(self, agent_id: str) -> int:
        """Drops all one agent kept, which goes when the agent does: nobody is shown it
        after, and an agent later given the same id would read it as its own."""
        return self._drop("agent_id = ?", (agent_id,))

    def apply(
        self, agent_id: str, namespace: str, writes: Mapping[str, str | None], most: int
    ) -> bool:
        """One script's writes, all of them or none; a value of None drops its key. False,
        with nothing written, when the namespace would then hold more than `most`. That is
        measured here, inside the transaction: another run may have written the namespace
        since the script looked, and the table never holds one over its limit."""
        stamp = now_iso()
        with self._lock:
            try:
                for key, text in writes.items():
                    if text is None:
                        self._conn.execute(
                            "DELETE FROM script_store"
                            " WHERE agent_id = ? AND namespace = ? AND key = ?",
                            (agent_id, namespace, key),
                        )
                        continue
                    self._conn.execute(
                        "INSERT INTO script_store (agent_id, namespace, key, value_json,"
                        " updated_at) VALUES (?,?,?,?,?)"
                        " ON CONFLICT(agent_id, namespace, key) DO UPDATE SET"
                        " value_json = excluded.value_json, updated_at = excluded.updated_at",
                        (agent_id, namespace, key, text, stamp),
                    )
                # Counted in Python: SQLite's LENGTH stops at a NUL, which a text may hold.
                fits = held_chars(self.read(agent_id, namespace)) <= most
                if fits:
                    self._conn.commit()
                else:
                    self._conn.rollback()
            except BaseException:
                self._conn.rollback()
                raise
        return fits
