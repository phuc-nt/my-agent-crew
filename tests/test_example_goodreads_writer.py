"""The Goodreads writer drives a real browser, so the site itself is not tested here.

What is tested is the part that runs before a browser opens: the command line, and the
checks that must stop a bad write before it reaches a public profile. A review posts
under the person's name, so an empty one has to fail without touching the session.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "examples"
    / "skills"
    / "goodreads"
    / "scripts"
    / "goodreads-writer.py"
)


@pytest.fixture(scope="module")
def writer():
    """Load by path with bytecode off, so no __pycache__ lands in the sample folder.
    Playwright is imported lazily inside main(), so this needs no browser installed."""
    spec = importlib.util.spec_from_file_location("goodreads_writer", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_review_takes_the_whole_text_as_one_argument(writer) -> None:
    args = writer.build_parser().parse_args(["review", "123", "Rất thích, đọc lại lần nữa."])
    assert args.func is writer.cmd_review
    assert args.book_id == "123"
    assert args.text == "Rất thích, đọc lại lần nữa."


@pytest.mark.parametrize("text", ["", "   \n "])
def test_empty_review_fails_before_opening_a_browser(writer, text, capsys) -> None:
    args = writer.build_parser().parse_args(["review", "123", text])
    # None in place of Playwright: any attempt to open a session would raise, not exit.
    with pytest.raises(SystemExit) as exited:
        writer.cmd_review(args, None)
    assert exited.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["ok"] is False
    assert "empty" in error["error"]
