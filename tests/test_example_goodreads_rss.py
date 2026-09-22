"""The Goodreads sample parses feeds and scraped pages, and both change without warning.

These run against a saved feed rather than the live site, so a failure here means the
parser broke and not that Goodreads was slow. The one thing worth pinning hardest is
what happens when a page comes back empty: Goodreads answers a blocked scrape with a
200-family status and no body, and a parser that treats that as data produces a record
full of nulls that reads exactly like a real answer.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

BUNDLE = Path(__file__).resolve().parent.parent / "docs" / "examples" / "skills" / "goodreads"
SCRIPTS = BUNDLE / "scripts"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "goodreads-shelf.rss"


def _load(name: str, filename: str | None = None):
    """Import a sample script by path. Bytecode writing is off for the duration: the
    sample is a folder people copy, and a __pycache__ left inside it is junk that ends
    up committed, and that the leak scan then has to read as if it were source."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (filename or f"{name}.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


parse = _load("goodreads_parse")


def test_shelf_reads_every_book() -> None:
    result = parse.parse_shelf(FIXTURE.read_text(encoding="utf-8"), "currently-reading")
    assert result["count"] == 2
    titles = [book["title"] for book in result["books"]]
    assert titles == ["The Cartographer's Dilemma", "Notes on Slow Water"]


def test_shelf_strips_markup_and_normalises_dates() -> None:
    books = parse.parse_shelf(FIXTURE.read_text(encoding="utf-8"), "currently-reading")["books"]
    first, second = books
    # The feed wraps descriptions and reviews in HTML; a briefing prints them as text.
    assert "<b>" not in first["description"]
    assert first["description"].endswith("moved.")
    assert "<i>" not in second["review"]
    assert second["date_read"] == "2026-09-07"
    assert first["date_read"] is None, "an unfinished book has no read date"


def test_shelf_keeps_an_unrated_book_distinct_from_a_rated_one() -> None:
    """Goodreads writes 0 for unrated, and 0 is falsy — so anything that tests the
    rating for truth rather than for 0 quietly turns a 4-star book into an unrated one."""
    books = parse.parse_shelf(FIXTURE.read_text(encoding="utf-8"), "currently-reading")["books"]
    assert books[0]["user_rating"] == "0"
    assert books[1]["user_rating"] == "4"


def test_unparseable_date_survives_as_itself() -> None:
    assert parse.parse_date("sometime last spring") == "sometime last spring"
    assert parse.parse_date(None) is None


def test_feed_without_a_channel_is_an_error_not_an_empty_shelf() -> None:
    with pytest.raises(ValueError, match="channel"):
        parse.parse_shelf("<rss></rss>", "read")


def test_empty_page_yields_no_title_so_the_caller_can_refuse_it() -> None:
    """parse_book never raises — it is the script that decides an untitled record means
    the page never arrived. This pins the signal that decision rests on."""
    assert parse.parse_book("", "123")["title"] == ""
    assert parse.parse_search("", 10) == []


def test_book_page_without_json_ld_still_finds_a_title() -> None:
    page = "<html><head><title>Some Book | Goodreads</title></head><body></body></html>"
    assert parse.parse_book(page, "7")["title"] == "Some Book"


def test_malformed_json_ld_does_not_crash_the_parse() -> None:
    page = '<script type="application/ld+json">{not json</script><title>Fallback</title>'
    assert parse.parse_book(page, "7")["title"] == "Fallback"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    # -B for the same reason _load disables bytecode: the script imports its parser
    # module, and the cache that creates would be written inside the sample folder.
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / "goodreads-rss.py"), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_script_parses_a_saved_feed_without_touching_the_network() -> None:
    done = _run("shelf", "12345", "--shelf", "currently-reading", "--rss-file", str(FIXTURE))
    assert done.returncode == 0, done.stderr
    payload = json.loads(done.stdout)
    assert payload["ok"] is True
    assert payload["count"] == 2


def test_missing_user_id_fails_on_stderr_leaving_stdout_clean() -> None:
    """The sample ships no goodreads.json, so this is the first run every copier gets.
    stdout has to stay empty because a caller pipes it into jq."""
    done = _run("shelf")
    assert done.returncode == 1
    assert done.stdout == ""
    reported = json.loads(done.stderr)
    assert reported["ok"] is False
    assert "goodreads.json" in reported["fix"]


def test_an_empty_page_is_refused_rather_than_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Goodreads answers a blocked scrape with a 202 and no body, so urllib raises
    nothing and the parse yields a record of nulls that reads like a real answer. This
    is the guard that turns that silence into a failure, and it is worth pinning
    because the bug it prevents is invisible in the output."""
    script = _load("gr_script", "goodreads-rss.py")

    class EmptyResponse:
        status = 202

        def read(self) -> bytes:
            return b""

        def __enter__(self) -> EmptyResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(script.urllib.request, "urlopen", lambda *a, **k: EmptyResponse())
    with pytest.raises(script.ScrapeBlocked, match="empty body"):
        script.fetch("https://www.goodreads.com/book/show/1")


def test_help_names_the_user_id_as_optional() -> None:
    done = _run("shelf", "--help")
    assert done.returncode == 0
    assert "goodreads.json" in done.stdout, "help must say where the id comes from"
