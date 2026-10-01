"""What every row is stamped with: when, in UTC to the second, and a short random id. Kept
apart from `db.py` so the stores it builds can stamp rows without importing it back."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]
