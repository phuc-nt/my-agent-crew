"""The YAML block that opens a markdown file: an agent, a command, a skill, a persona.

Kits written for other harnesses often hold a line like `description: Use when: the tests
fail`. YAML refuses it, the second colon would open a mapping inside a plain value, yet
what the author meant is plain to read. So the block is read as YAML first, and a block
YAML takes is exactly what YAML made of it. Only a block it refuses is read a second
time, with the value of each such line taken as the text it is.

The second reading knows one shape and no more: `key: value` on one line, starting at
the first column. A nested key, a value that runs over lines and an item of a list are
left as written, so a block broken there is still refused. It goes by lines and does not
follow YAML's quoting: in a block YAML refused, a line of that shape inside a quoted value
that runs over lines is quoted as well.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

# `key: value` on one line from the first column; a key holding a colon is not one.
_ENTRY = re.compile(r"^(?P<key>[^\s:][^:\n]*:[ \t]+)(?P<value>\S.*?)[ \t\r]*$", re.MULTILINE)
# The colon YAML reads as the start of a mapping: one before a blank, or the last thing.
_OPENS_A_MAPPING = re.compile(r":(?:[ \t]|$)")
# Where YAML would stop reading a plain value and start a remark.
_REMARK = re.compile(r"[ \t]#")
# What a plain scalar does not start with: these say the author wrote YAML on purpose
# (a quote, a list, a block, an anchor, a tag) or wrote a remark.
_INDICATORS = frozenset("[]{},#&*!|>'\"%@`")


def _plain(text: str) -> bool:
    """Whether the text starts as a plain scalar does. `-`, `?` and `:` are indicators
    only before a blank: `--dry-run` is plain, `- item` is a list."""
    if text[0] in _INDICATORS:
        return False
    return not (text[0] in "-?:" and text[1:2] in ("", " ", "\t"))


def _as_text(entry: re.Match[str]) -> str:
    """The line with its value quoted when the value is the shape YAML refuses, and as
    written otherwise. The whole rest of the line is the text, a `#` remark included:
    whoever wrote a second colon unquoted was not writing YAML, and `issue #12` is more
    often a part of the sentence than a remark. A colon that only a remark holds leaves
    the line alone, since YAML reads that line as it is."""
    key, value = entry["key"], entry["value"]
    stated = _REMARK.split(value, maxsplit=1)[0]
    if not (_plain(key) and _plain(value) and _OPENS_A_MAPPING.search(stated)):
        return entry[0]
    return key + json.dumps(value, ensure_ascii=False)


def read_front_matter(front: str) -> Any:
    """What the block states. Raises `yaml.YAMLError` when neither reading takes it, and
    the error is the second reading's: it names what is still in the way."""
    try:
        return yaml.safe_load(front)
    except yaml.YAMLError:
        return yaml.safe_load(_ENTRY.sub(_as_text, front))
