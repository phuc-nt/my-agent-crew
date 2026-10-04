"""The reads that count the canvases, as reads of a store every thread shares: each runs with
the store's lock held, and hands back a value its reader cannot change."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from my_agent_crew.store.artifact_usage import Written
from my_agent_crew.store.db import Store

COACH = "agent:coach"


def _lock_is_held(store: Store) -> bool:
    """Whether a thread other than this one would have to wait for the store's lock."""
    took: list[bool] = []

    def take() -> None:
        took.append(store._lock.acquire(blocking=False))
        if took[0]:
            store._lock.release()

    thread = threading.Thread(target=take)
    thread.start()
    thread.join()
    return not took[0]


class _Watched:
    """The store's connection, noting for each statement whether the lock was held."""

    def __init__(self, store: Store):
        self._store = store
        self.held: list[bool] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        self.held.append(_lock_is_held(self._store))
        return self._store._conn.execute(sql, params)


def test_the_canvases_are_counted_with_the_stores_lock_held(store: Store, monkeypatch):
    """One connection serves every thread, so a read made while another thread is halfway
    through a write would count a version that may yet be rolled back."""
    conv = store.create()
    art = store.artifacts.create("Kế hoạch", "markdown", "coach", COACH, conv.id, "# a").id
    watched = _Watched(store)
    monkeypatch.setattr(store.artifacts, "_conn", watched)
    assert store.artifacts.sizes() == {art: 3}
    assert store.artifacts.written_in(conv.id) == [Written(art, 1, "Kế hoạch")]
    assert watched.held == [True, True]


def test_a_canvas_named_as_written_cannot_be_changed_by_its_reader():
    written = Written("a" * 12, 2, "Kế hoạch")
    with pytest.raises(FrozenInstanceError):
        written.version = 3  # type: ignore[misc]
    assert written == Written("a" * 12, 2, "Kế hoạch")
