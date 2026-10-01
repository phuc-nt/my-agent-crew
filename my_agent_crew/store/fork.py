"""Forking a conversation: a new conversation holding a copy of every message before a
saved user message, so a person can edit and resend an earlier turn without disturbing the
original. See `agent/tool_calls.py` for why an open tool call at the cut is closed rather
than copied, and `texts_fork.py` for the message that closes it.

The fork also links every canvas the source had linked by the time of that message, with
nothing seen, read or told: its agent has read nothing yet, so it reads a canvas again before
it overwrites it, and its first note tells of each one as new. Stamps go to the second, so a
canvas linked in the same second as the message is kept. The canvas open in the source stays
open there only.

Everything here runs under one hold of `self._lock` (the store's own `RLock`), so a
conversation is never left half-copied: any error after `create()` deletes the row it just
made before re-raising, and the SELECTs plus the INSERT…SELECTs that follow are one atomic
unit as far as a caller can observe.
"""

from __future__ import annotations

import sqlite3
import threading

from my_agent_crew.store.models import Conversation
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT
from my_agent_crew.texts_fork import FORK_TITLE_SUFFIX

# Copies everything a later turn needs to keep making sense of the history — the words,
# the tool-call shape, who said it and when, the canvas note it was read after — while
# leaving billing columns out. See the module docstring in `search_index.py`: an INSERT is
# fine here, an UPDATE never is.
_COPY_MESSAGES = """
INSERT INTO messages (conversation_id, seq, role, content, tool_calls, tool_call_id, name,
                       model, created_at, context)
SELECT ?, ROW_NUMBER() OVER (ORDER BY seq), role, content, tool_calls, tool_call_id, name,
       model, created_at, context
FROM messages WHERE conversation_id = ? AND seq < ? ORDER BY seq
"""
# The marks of what was seen, read and told start again at 0 from the column defaults.
_COPY_LINKS = """
INSERT INTO conversation_artifacts (conversation_id, artifact_id, linked_at, shared)
SELECT ?, artifact_id, linked_at, shared FROM conversation_artifacts
WHERE conversation_id = ? AND linked_at <= ? ORDER BY rowid
"""


def _forked_title(title: str) -> str:
    """The fork's title: the source's title with the suffix appended once. A source still
    on the default title stays on the default, so the title job can name it after its own
    first message, same as any other new conversation."""
    if title == CONVERSATION_TITLE_DEFAULT or title.endswith(FORK_TITLE_SUFFIX):
        return title
    return f"{title} {FORK_TITLE_SUFFIX}"


class Forks:
    """Mixed into `Store` alongside `ConversationLookups`; expects the same `_conn` and
    `_lock` attributes, and calls `create`, `get` and `delete`, all of which `Store`
    provides."""

    _conn: sqlite3.Connection
    _lock: threading.RLock

    def fork(
        self, conv_id: str, before_message_id: int, *, autonomous: bool
    ) -> tuple[Conversation, str]:
        """Creates a fork of `conv_id` holding every message before `before_message_id`,
        and returns it with that message's own text as a draft for the composer.

        Raises `KeyError` when `conv_id` or `before_message_id` do not exist, or the
        message belongs to a different conversation. Raises `ValueError` when the message
        is not a `user` message, or the conversation is itself a delegated child."""
        with self._lock:
            source = self.get(conv_id)
            if source.parent_call_id:
                raise ValueError("cannot fork a delegated conversation")
            cut = self._conn.execute(
                "SELECT conversation_id, seq, role, content, created_at FROM messages WHERE id = ?",
                (before_message_id,),
            ).fetchone()
            if cut is None or cut["conversation_id"] != conv_id:
                raise KeyError(before_message_id)
            if cut["role"] != "user":
                raise ValueError("fork point must be a saved user message")
            fork = self.create(
                title=_forked_title(source.title),
                autonomous=autonomous,
                cost_cap_usd=source.cost_cap_usd,
                skills=source.skills,
                agent_id=source.agent_id,
                forked_from=source.id,
            )
            try:
                self._conn.execute(_COPY_MESSAGES, (fork.id, conv_id, cut["seq"]))
                self._conn.execute(_COPY_LINKS, (fork.id, conv_id, cut["created_at"]))
                self._conn.commit()
            except Exception:
                self.delete(fork.id)
                raise
            return fork, cut["content"]
