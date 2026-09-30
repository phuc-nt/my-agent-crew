"""Searching the message log built by `store/search_index.py`.

Every value a caller supplies travels as a named SQL parameter; the only thing built by
string concatenation is a fixed set of optional `WHERE` clauses, none of which carries
user text."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from typing import Any

from my_agent_crew.memory.search import normalize, terms_of

# Per-conversation cap on `store/search.py`'s dedup query: enough to show a thread found
# the topic without one very active conversation crowding out every other hit.
PER_CONVERSATION_CAP = 3

_FIND = """
WITH hit AS (
    SELECT m.id AS message_id, m.conversation_id, m.role, m.content, m.created_at,
           c.agent_id, c.title, messages_fts.rank AS score
    FROM messages_fts
    JOIN messages m ON m.id = messages_fts.rowid
    JOIN conversations c ON c.id = m.conversation_id
    WHERE messages_fts MATCH :q
    {filters}
), uniq AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY agent_id, role, content
                                 ORDER BY created_at DESC, message_id DESC) AS same
    FROM hit
), per_conv AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY conversation_id
                                 ORDER BY score, message_id) AS k
    FROM uniq WHERE same = 1
)
SELECT * FROM per_conv WHERE k <= :cap ORDER BY score, created_at DESC, message_id DESC LIMIT :limit
"""


def match_query(query: str) -> str | None:
    """`query` as an FTS5 `MATCH` expression, or None when it has nothing to search for.

    Each term is quoted (`"term"*`) with any `"` inside it doubled, which neutralises
    every FTS5 operator (`AND`, `NEAR(`, `*`, bare `(`/`)`) without needing to recognise
    them: a quoted string has no special syntax of its own.
    """
    terms = terms_of(query)
    if not terms:
        return None
    return " ".join(f'"{t.replace(chr(34), chr(34) * 2)}"*' for t in terms)


def snippet(original: str, terms: list[str], width: int = 160) -> str:
    """A slice of `original` around the first matching term, marked with `…` where it was
    cut.

    `terms` are already the output of `terms_of`, so finding one means folding `original`
    through the same `normalize` and searching there. Folding almost always keeps the
    same length as the original — a mark is dropped, not replaced by something wider —
    so the offset found in the folded text is normally the offset of the same character
    in the original. When a character folds to a different length — text that arrived
    already decomposed, say — the two offsets drift apart; snippet correctness matters
    less than never slicing mid-character, so that case falls back to the start of the
    text instead of trusting an offset that might land inside one.
    """
    folded = normalize(original)
    position = -1
    if len(folded) == len(original):
        for term in terms:
            position = folded.find(term)
            if position != -1:
                break
    if position == -1:
        start, end = 0, min(width, len(original))
    else:
        start = max(0, position - width // 2)
        end = min(len(original), start + width)
        start = max(0, end - width)
    head = "…" if start > 0 else ""
    tail = "…" if end < len(original) else ""
    return f"{head}{original[start:end]}{tail}"


@dataclass(frozen=True)
class SearchHit:
    conversation_id: str
    agent_id: str
    title: str
    message_id: int
    role: str
    snippet: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "agent_id": self.agent_id,
            "title": self.title,
            "message_id": self.message_id,
            "role": self.role,
            "snippet": self.snippet,
            "created_at": self.created_at,
        }


class SearchStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def find(
        self,
        query: str,
        *,
        agent_ids: list[str] | None = None,
        since: str | None = None,
        exclude_conversation: str | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        q = match_query(query)
        if q is None:
            return []
        terms = terms_of(query)
        clauses: list[str] = []
        params: dict[str, Any] = {"q": q, "cap": PER_CONVERSATION_CAP, "limit": limit}
        if agent_ids is not None:
            placeholders = ", ".join(f":agent{i}" for i in range(len(agent_ids)))
            clauses.append(f"AND c.agent_id IN ({placeholders})")
            params.update({f"agent{i}": a for i, a in enumerate(agent_ids)})
        if since is not None:
            clauses.append("AND m.created_at >= :since")
            params["since"] = since
        if exclude_conversation is not None:
            clauses.append("AND m.conversation_id != :exclude")
            params["exclude"] = exclude_conversation
        sql = _FIND.format(filters="\n".join(clauses))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            SearchHit(
                conversation_id=row["conversation_id"],
                agent_id=row["agent_id"],
                title=row["title"],
                message_id=row["message_id"],
                role=row["role"],
                snippet=snippet(row["content"], terms),
                created_at=row["created_at"],
            )
            for row in rows
        ]
