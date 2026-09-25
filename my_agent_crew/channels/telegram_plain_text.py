"""Markdown turned into text that reads well in a Telegram chat.

Messages go out without a parse mode, so every marker a model writes shows literally. The
ones models reach for most are rewritten: bold and italic lose their asterisks, headings
their hashes, a `---` rule becomes a blank line, and a table becomes one line per row,
its cells joined by " · ". A phone screen cannot line columns up anyway, and a row of
pipes and dashes is the part of a morning brief the person reads least.
"""

from __future__ import annotations

import re

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
# Single asterisks hugging a phrase; one standing between words or digits (`2*3`) stays.
_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_DIVIDER_CELL = re.compile(r"^:?-{2,}:?$")
_EXTRA_BLANKS = re.compile(r"\n{3,}")
CELL_SEPARATOR = " · "


def plain_text(text: str) -> str:
    lines = [_line(line) for line in text.split("\n")]
    text = "\n".join(line for line in lines if line is not None)
    text = _HEADING.sub("", _ITALIC.sub(r"\1", _BOLD.sub(r"\1", text)))
    return _EXTRA_BLANKS.sub("\n\n", text)


def _line(line: str) -> str | None:
    """The line as it should read, or None when it carries nothing but layout."""
    if _RULE.match(line):
        return ""
    if not _TABLE_ROW.match(line):
        return line
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if all(_DIVIDER_CELL.match(cell) for cell in cells):
        return None
    return CELL_SEPARATOR.join(cell for cell in cells if cell)
