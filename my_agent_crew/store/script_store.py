"""What an agent's scripts keep from one run to the next (`store` and `load` in a script).

A row is one key of one namespace of one agent, with its value as JSON text. A namespace is
the conversation or the job a script ran for (`script/store_session.py` says which), and an
agent never reads another's. Nothing is written while a script runs: what it wrote is applied
once it ended well, all of it in one transaction, and only when the namespace then still
holds no more than it may.

An id outlives its agent: removing an agent stops nothing it is doing, and the id may be
given to another. So each id has an era, which moves on when all its agent kept is dropped
with it. A write names the era it was made in, and one of an era gone by is not written.
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
        # How many agents of each id were removed. In memory: no script outlives the server.
        self._eras: dict[str, int] = {}

    def era(self, agent_id: str) -> int:
        """Which agent of that id this is. An agent takes it as it is put together and hands
        it back with what its scripts wrote (`apply`), so what was put together for an agent
        since removed writes nothing, whoever has the id by then."""
        with self._lock:
            return self._eras.get(agent_id, 0)

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
        after, and an agent later given the same id would read it as its own. The id's era
        moves on in the same hold of the lock, so a script the agent is still running writes
        nothing when it ends."""
        with self._lock:
            self._eras[agent_id] = self._eras.get(agent_id, 0) + 1
            return self._drop("agent_id = ?", (agent_id,))

    def apply(
        self,
        agent_id: str,
        namespace: str,
        writes: Mapping[str, str | None],
        most: int,
        era: int | None = None,
    ) -> bool:
        """One script's writes, all of them or none; a value of None drops its key. False,
        with nothing written, when the namespace would then hold more than `most`. That is
        measured here, inside the transaction: another run may have written the namespace
        since the script looked, and the table never holds one over its limit.

        False too, with nothing written, when `era` is named and is not the id's now: the
        agent the writes were made for was removed. It is looked at under the lock a removal
        takes, so none falls between the look and the write. Without one nothing is asked:
        that is for a write nobody made for an agent."""
        stamp = now_iso()
        with self._lock:
            if era is not None and era != self._eras.get(agent_id, 0):
                return False
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
