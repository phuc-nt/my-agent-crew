"""How a save writes a text into `agent.yaml`.

The file is the person's to read and to edit by hand, so a text of several lines that a save
brings (a job's script, its prompt) is written as a block, each line on a line of its own,
the way a person writes it. A block cannot carry every text. What it cannot carry is written
in quotes, and whichever way a text is written, the next boot reads the text that was saved,
to the character.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from ruamel.yaml.scalarstring import LiteralScalarString

from my_agent_crew.agents.profile_write import as_written, read_raw, write_raw

BEFORE = "name: Thợ mã\nschedules: []\n"
CARRIED = [
    "a\nb",
    "a\nb\n",
    "a\nb\n\n",
    " leading\nx\n",
    "x  \ny\n",
    "\nstarts blank\n",
    "a\n\n\nb\n",
    "for i in x:\n    print(i)\n",
    "# not a comment\n: colon\n- dash\n",
    "---\na\n...\n",
    "über\nđ: 1\n😀\n",
    "'one'\n\"two\"\n\\three\n",
    "a\n ",
    "\n",
]
# A carriage return comes back as nothing, and the other alphabets' line ends leave a file
# no reader opens: a block is for what prints.
NOT_CARRIED = [
    "a\r\nb\n",
    "a\tb\nc\n",
    "a\u2028b\nc\n",
    "a\u2029b\nc\n",
    "a\xa0b\nc\n",
    "a\u200bb\nc\n",
    "\ufeffa\nb\n",
    "a\x7fb\nc\n",
]
NEXT_LINES = ["a\x85b", "a\x85b\nc\n", "\x85", "x: \x85 y"]
ONE_LINE = ["chào", "a: b", "# x", " a ", "", "a\tb", "it's", "3", "true", "1.5", "- a"]
# What puts a text into quotes, each with what a fold of the quoted line then tripped on:
# the line was broken after an escape, and the reader put a space where the break stood.
ESCAPED = ["\t", "\r", "\x85", "\ufeff", "\x1b", "\xa0\\", "\u200b\\"]
# One line each, and to the boot's reader no text when it stands bare: a yes or a no, a
# number, a time of day, a date, nothing at all. The writer goes by a later YAML, to
# which each of them is a text and needs no quotes.
NOT_A_TEXT_AT_BOOT = [
    "No",
    "yes",
    "on",
    "OFF",
    "1:30",
    "12:30:45",
    "0b11",
    "1_000",
    "010",
    "0o17",
    "+1",
    "2026-10-12",
    "~",
    "null",
    "=",
    "<<",
    ".inf",
    "1e3",
    "0x1F",
    "190:20:30.15",
]


def saved(tmp_path: Path, row: dict[str, Any], *, plain: bool = False) -> Path:
    """The file after a save brought `row` as the agent's one schedule."""
    manifest = tmp_path / "agent.yaml"
    manifest.write_text(BEFORE, encoding="utf-8")
    raw = read_raw(manifest)
    raw["schedules"] = [row] if plain else as_written([row])
    write_raw(manifest, raw)
    return manifest


def read_back(manifest: Path, key: str) -> tuple[str, str]:
    """The text as the next boot reads it, and as the next save's reader does."""
    booted = yaml.safe_load(manifest.read_text("utf-8"))["schedules"][0][key]
    return booted, str(read_raw(manifest)["schedules"][0][key])


def is_block(manifest: Path, key: str) -> bool:
    """Whether the file gives `key` a block: its lines under it, not one quoted line."""
    return re.search(rf"^ *{key}: \|[0-9+-]*$", manifest.read_text("utf-8"), re.M) is not None


@pytest.mark.parametrize("text", CARRIED)
def test_a_text_of_several_lines_is_written_as_its_lines(tmp_path, text):
    manifest = saved(tmp_path, {"id": "due", "script": text})

    assert is_block(manifest, "script")
    assert read_back(manifest, "script") == (text, text)


@pytest.mark.parametrize("text", NOT_CARRIED)
def test_a_text_a_block_cannot_carry_is_still_the_text_that_was_saved(tmp_path, text):
    manifest = saved(tmp_path, {"id": "due", "script": text})

    assert read_back(manifest, "script") == (text, text)
    assert not is_block(manifest, "script")


@pytest.mark.parametrize("text", NEXT_LINES)
def test_a_text_with_a_next_line_character_is_read_back_whole(tmp_path, text):
    """Left to the writer, the character goes into the file bare and the reader takes it
    for the end of a line: the text came back with a space where it stood."""
    manifest = saved(tmp_path, {"id": "due", "prompt": text})

    assert read_back(manifest, "prompt") == (text, text)


@pytest.mark.parametrize("text", ONE_LINE)
def test_a_text_of_one_line_is_written_as_it_always_was(tmp_path, text):
    row = {"id": "due", "prompt": text}

    written = saved(tmp_path, row).read_text("utf-8")

    assert written == saved(tmp_path, row, plain=True).read_text("utf-8")
    assert not is_block(tmp_path / "agent.yaml", "prompt")


def long_texts(mark: str):
    """A script and a line of words with `mark` in them, pushed along one column at a
    time so that a line of the file would end at every place in them."""
    for pad in range(80):
        pushed = "x" * pad
        yield (
            f"{pushed} = 0\nfor amount in rows:\n"
            f"{mark}if amount > limit and status != done and owner == me and seen < 100:\n"
            f"{mark}{mark}seen = seen + 1\nprint(seen)\n"
        )
        yield f"{pushed}{mark}= 0\n" + f"w{mark} " * 30 + "end\n"


@pytest.mark.parametrize("mark", ESCAPED)
def test_a_long_text_in_quotes_is_still_the_text_that_was_saved(tmp_path, mark):
    """A script indented with tabs is such a text. Read back with a space it never had,
    its indented line is another line, and the next start refuses the file for it."""
    changed = []
    for text in long_texts(mark):
        manifest = saved(tmp_path, {"id": "due", "script": text})
        if read_back(manifest, "script") != (text, text):
            changed.append(text)

    assert changed == []


@pytest.mark.parametrize("text", ["a" * 80 + "  b", "word " * 30 + " two  spaces", "x " * 200])
def test_a_long_line_is_not_folded_into_another_text(tmp_path, text):
    manifest = saved(tmp_path, {"id": "due", "prompt": text})

    assert read_back(manifest, "prompt") == (text, text)
    # The name, the list, the row's id, and the text on a line of its own.
    assert len(manifest.read_text("utf-8").splitlines()) == 4


@pytest.mark.parametrize("text", NOT_A_TEXT_AT_BOOT)
def test_a_text_the_boot_would_read_as_something_else_is_written_in_quotes(tmp_path, text):
    """`then_prompt: No` in the file is a false to the reader the server starts with, and
    a row whose prompt is no text is a file the server does not start with."""
    manifest = saved(tmp_path, {"id": "due", "prompt": text})

    booted, again = read_back(manifest, "prompt")
    assert (type(booted), booted, again) == (str, text, text)


def test_only_a_text_is_looked_at_and_however_deep_it_sits():
    kept = LiteralScalarString("x\ny")
    row = {"n": 3, "flag": True, "none": None, "rows": [1.5, {"deep": "a\nb"}], "kept": kept}

    made = as_written(row)

    deep = made["rows"][1]["deep"]
    assert (made["n"], made["flag"], made["none"], made["rows"][0]) == (3, True, None, 1.5)
    assert (type(deep), deep) == (LiteralScalarString, "a\nb")
    assert made["kept"] is kept
    # What the caller sent is not rewritten under it.
    assert type(row["rows"][1]["deep"]) is str
