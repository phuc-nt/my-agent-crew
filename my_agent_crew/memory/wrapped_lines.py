"""The lines of `MEMORY.md` as they are meant, with a bullet wrapped by hand read whole.

A bullet written over two lines (`- Tách khỏi Pong …; mọi việc` and an indented
`  sổ cái, nhắc hạn … về đây.`) is one fact. A rewrite that joins it onto one line says the
same thing; read line by line, its second half looked removed and held the rewrite for a
person to approve (`fact_dates.removed_lines`).
"""

from __future__ import annotations

import re

_BULLET = re.compile(r"^[-*+]\s+")


def logical_lines(text: str) -> list[str]:
    """Every non-blank line, stripped, with an indented line that is not itself a bullet
    joined onto the bullet above it. Only an indented line is a continuation: a flush line
    after a bullet is more often a sentence of its own."""
    lines: list[str] = []
    bullet = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            bullet = False
            continue
        starts_bullet = bool(_BULLET.match(line))
        if bullet and not starts_bullet and raw[:1].isspace():
            lines[-1] = f"{lines[-1]} {line}"
            continue
        lines.append(line)
        bullet = starts_bullet
    return lines
