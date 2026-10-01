"""Row shapes for canvas documents. A canvas (`artifacts`) points at its newest version; each
version (`artifact_versions`) is a full copy of the document, never a diff; a link
(`conversation_artifacts`) records which version a conversation's agent has last seen; and a
focus (`canvas_focus`) is the canvas a conversation has open in the web UI, with the passage
the person selected in it."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

# The author of a version a person wrote; an agent's versions carry "agent:<agent_id>".
USER = "user"


@dataclass(frozen=True)
class ArtifactSummary:
    id: str
    title: str
    kind: str
    language: str
    agent_id: str  # the agent that created it; "" when a person did on the web
    head_version: int
    source: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ArtifactSummary:
        return cls(**{name: row[name] for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class ArtifactVersion:
    artifact_id: str
    version: int
    size: int  # bytes of UTF-8 content, or of data
    author: str  # "user" or "agent:<agent_id>"
    conversation_id: str  # where the write came from, "" when from nowhere in particular
    note: str  # "" for an ordinary write, else e.g. "restore:<n>"
    created_at: str
    updated_at: str
    content: str | None = None  # text kinds; None when read as metadata only
    data: bytes | None = None  # binary kinds; None when read as metadata only

    def meta(self) -> dict[str, Any]:
        """Everything but the payload: what a history list or an event carries."""
        data = asdict(self)
        del data["content"], data["data"]
        return data

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ArtifactVersion:
        keys = row.keys()
        return cls(**{name: row[name] for name in cls.__dataclass_fields__ if name in keys})


@dataclass(frozen=True)
class Link:
    conversation_id: str
    artifact_id: str
    seen_version: int  # 0 until the conversation's agent has read or written the canvas
    linked_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Link:
        return cls(**{name: row[name] for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Focus:
    conversation_id: str
    artifact_id: str
    # {"version", "text", "line_start", "line_end"} while a passage is selected, else None.
    selection: dict[str, Any] | None
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Focus:
        selection = json.loads(row["selection"]) if row["selection"] else None
        return cls(row["conversation_id"], row["artifact_id"], selection, row["updated_at"])


class VersionConflict(Exception):
    """A write named a base version that is no longer the newest. Carries the newest one so
    the writer can merge against it instead of reading it back."""

    def __init__(self, head_version: int, head_content: str | None):
        super().__init__(f"base version is stale; the newest is {head_version}")
        self.head_version = head_version
        self.head_content = head_content
