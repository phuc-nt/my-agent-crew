"""What a conversation has open in the web canvas.

A focus is web UI state: the canvas a conversation has open and the passage the person
selected in it, which the next turn's note quotes once and clears. The note names the open
canvas once (`noted`); opening the same canvas again keeps that, while opening another one or
selecting a passage has to be told again. Setting one names a conversation and a canvas that
both exist, or stores nothing."""

from __future__ import annotations

import json
from typing import Any

from my_agent_crew.store.artifact_models import Focus
from my_agent_crew.store.stamps import now_iso

# Selects the pair only while both rows exist; an insert from it stores nothing otherwise.
# The WHERE also keeps SQLite from reading the upsert's ON as a join's.
BOTH_EXIST = "FROM conversations c, artifacts a WHERE c.id = ? AND a.id = ?"
_SET_FOCUS = (
    "INSERT INTO canvas_focus (conversation_id, artifact_id, selection, updated_at)"
    f" SELECT c.id, a.id, ?, ? {BOTH_EXIST} ON CONFLICT (conversation_id) DO UPDATE SET"
    " artifact_id = excluded.artifact_id, selection = excluded.selection,"
    " updated_at = excluded.updated_at, noted = CASE WHEN canvas_focus.artifact_id ="
    " excluded.artifact_id AND excluded.selection = '' THEN canvas_focus.noted ELSE 0 END"
)


class CanvasFocus:
    """Mixed into `ArtifactLinks`, whose `_write` runs one step under the shared lock."""

    def focus(self, conversation_id: str) -> Focus | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM canvas_focus WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
        return None if row is None else Focus.from_row(row)

    def set_focus(
        self, conversation_id: str, artifact_id: str, selection: dict[str, Any] | None
    ) -> bool:
        """False, with nothing stored, when either is missing."""
        stored = "" if selection is None else json.dumps(selection, ensure_ascii=False)
        params = (stored, now_iso(), conversation_id, artifact_id)
        return self._write(lambda: self._conn.execute(_SET_FOCUS, params).rowcount > 0, True)

    def clear_selection(self, conversation_id: str, *, commit: bool = True) -> None:
        sql = "UPDATE canvas_focus SET selection = '', updated_at = ? WHERE conversation_id = ?"
        self._write(lambda: self._conn.execute(sql, (now_iso(), conversation_id)), commit)

    def note_focus(
        self, conversation_id: str, *, clear_selection: bool = False, commit: bool = True
    ) -> None:
        """Records that a note named the open canvas, and with `clear_selection` that it
        quoted the selected passage, which is then dropped."""
        sql, params = "UPDATE canvas_focus SET noted = 1", [conversation_id]
        if clear_selection:
            sql, params = sql + ", selection = '', updated_at = ?", [now_iso(), *params]
        where = f"{sql} WHERE conversation_id = ?"
        self._write(lambda: self._conn.execute(where, params), commit)

    def clear_focus(self, conversation_id: str) -> None:
        sql = "DELETE FROM canvas_focus WHERE conversation_id = ?"
        self._write(lambda: self._conn.execute(sql, (conversation_id,)), True)
