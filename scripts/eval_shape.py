"""The shapes a value in a case file may take, checked as the file is read: shared by the case,
its `expect` block and its canvas steps, so each refuses a typo the same way."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def only(raw: Mapping[str, Any], allowed: Sequence[str], where: str) -> None:
    unknown = sorted(set(raw) - set(allowed), key=str)
    if unknown:
        raise ValueError(f"{where}: unknown key {unknown[0]!r}; known keys: {', '.join(allowed)}")


def strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{where} must be a list of non-empty strings")
    return tuple(value)


def needles(raw: object, key: str, where: str) -> tuple[str, ...]:
    """A string, or a list of them."""
    return strings([raw] if isinstance(raw, str) else raw, f"{where}: {key}")


def is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def count_or_none(raw: object, key: str, where: str) -> int | None:
    if raw is None:
        return None
    if not isinstance(raw, int) or not is_count(raw):
        raise ValueError(f"{where}: {key} must be a whole number, 0 or more")
    return raw


def flag(raw: object, key: str, where: str) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"{where}: {key} is true or false")
    return raw
