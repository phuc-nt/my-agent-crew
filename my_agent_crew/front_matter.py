"""The YAML block that opens a markdown file: an agent, a command, a skill, a persona.

Kits written for other harnesses often hold a line like `description: Use when: the tests
fail`. YAML refuses it, the second colon would open a mapping inside a plain value, yet
what the author meant is plain to read. So the block is read as YAML first, and a block
YAML takes is exactly what YAML made of it. Only a block it refuses is read a second
time, with the value of each such line taken as the text it is.

The second reading knows one shape and no more: `key: value` on one line, starting at
the first column. A nested key, a value that runs over lines and an item of a list are
left as written, so a block broken there is still refused. It goes by lines and does not
follow YAML's quoting, so a line of that shape inside a value that runs over lines is
taken too; what such a line states is then not in what the block states, and the block
is refused as YAML refused it.
"""

from __future__ import annotations

import json
import re
from typing import Any

import yaml

# `key: value` on one line from the first column; a key holding a colon is not one. The
# value runs to the end of the line and the blanks that end it are cut off afterwards: a
# match that stops before them starts over at every blank of a long run inside the value.
_ENTRY = re.compile(r"^(?P<key>[^\s:][^:\n]*:[ \t]+)(?P<value>\S.*)$", re.MULTILINE)
# What ends a line for YAML, or what YAML takes in no text at all. A line holding one is
# not one line to YAML, and quoting it would hide that.
_NOT_ONE_LINE = re.compile("[\x00-\x08\x0a-\x1f\x7f-\x9f\u2028\u2029]")
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


def _as_text(entry: re.Match[str], taken: list[str]) -> str:
    """The line with its value quoted when the value is the shape YAML refuses, and as
    written otherwise; a line quoted is added to `taken`. The whole rest of the line is
    the text, a `#` remark included: whoever wrote a second colon unquoted was not writing
    YAML, and `issue #12` is more often a part of the sentence than a remark. A colon that
    only a remark holds leaves the line alone, since YAML reads that line as it is."""
    key, value = entry["key"], entry["value"].rstrip(" \t\r")
    stated = _REMARK.split(value, maxsplit=1)[0]
    if _NOT_ONE_LINE.search(value):
        return entry[0]
    if not (_plain(key) and _plain(value) and _OPENS_A_MAPPING.search(stated)):
        return entry[0]
    taken.append(key + json.dumps(value, ensure_ascii=False))
    return taken[-1]


def read_front_matter(front: str) -> Any:
    """What the block states. Raises `yaml.YAMLError` when neither reading takes it: the
    second reading's error where it has one, which names what is still in the way, and
    the first's where a line was taken as text that is no entry of the block."""
    try:
        return yaml.safe_load(front)
    except yaml.YAMLError as refused:
        taken: list[str] = []
        stated = yaml.safe_load(_ENTRY.sub(lambda entry: _as_text(entry, taken), front))
        # A line is taken on the word of its shape. Each has to be an entry of its own in
        # what the block states, or it stood inside a value, or under a key stated twice.
        alone = [yaml.safe_load(line) for line in taken]
        said = {key: text for one in alone if isinstance(one, dict) for key, text in one.items()}
        if not (isinstance(stated, dict) and len(said) == len(taken)):
            raise refused
        if not said.items() <= stated.items():
            raise refused
        return stated
