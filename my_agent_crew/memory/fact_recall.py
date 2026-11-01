"""How often each fact was actually read back, and when last.

A fact's index line rides in every prompt, so being in the prompt says nothing about being
useful. Being looked up (by `user_memory_get` or a `memory_search` hit) does: the counts
are what the person and the fact review see as the fact's usefulness. Kept beside the
facts in one small JSON file, since a read must not rewrite the fact itself.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

RECALL_FILE = ".recall.json"


def _path(facts_dir: Path) -> Path:
    return facts_dir / RECALL_FILE


def read(facts_dir: Path) -> dict[str, dict]:
    path = _path(facts_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _write(facts_dir: Path, data: dict[str, dict]) -> None:
    facts_dir.mkdir(parents=True, exist_ok=True)
    _path(facts_dir).write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")


def bump(facts_dir: Path, names: Iterable[str], now: datetime | None = None) -> None:
    names = list(dict.fromkeys(names))
    if not names:
        return
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    data = read(facts_dir)
    for name in names:
        entry = data.get(name) if isinstance(data.get(name), dict) else {}
        data[name] = {"count": int(entry.get("count", 0)) + 1, "last": stamp}
    _write(facts_dir, data)


def forget(facts_dir: Path, name: str) -> None:
    data = read(facts_dir)
    if data.pop(name, None) is not None:
        _write(facts_dir, data)
