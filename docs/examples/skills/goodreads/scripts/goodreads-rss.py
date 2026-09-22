#!/usr/bin/env python3
"""Read Goodreads without an API key. The official API closed in December 2020, so
what is left is the public RSS feeds and, for the two things with no feed, the pages
themselves.

The user id is read from `goodreads.json` next to this script when no id is given on
the command line. That is deliberate: an id that has to be typed is an id that gets
typed wrong, or passed as a flag when the script wants it positionally, and the
failure looks like Goodreads being down rather than like a typo.

Every command prints one JSON object. A failure prints one too, on stderr, so a
caller piping stdout into jq gets either a clean parse or nothing.

Usage:
  goodreads-rss.py shelf [user_id] [--shelf read|currently-reading|to-read|<name>]
                         [--limit N] [--sort date_read|date_added|rating|title]
  goodreads-rss.py activity [user_id] [--limit N]
  goodreads-rss.py book <book_id>
  goodreads-rss.py search <query> [--limit N]

Add --rss-file <path> to shelf or activity to parse a saved feed instead of fetching.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from goodreads_parse import parse_activity, parse_book, parse_search, parse_shelf  # noqa: E402

CONFIG = Path(__file__).resolve().parent / "goodreads.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

BLOCKED_FIX = (
    "Goodreads is refusing scraped page requests; only the RSS commands "
    "(shelf, activity) work. Tell the person rather than trying another scrape."
)


class ScrapeBlocked(RuntimeError):
    """Goodreads served an empty page instead of refusing outright."""


def fail(message: str, fix: str) -> None:
    """Stderr, never stdout: a caller pipes stdout into jq, and appending an error
    object to a list of books turns a clean failure into a parse error elsewhere."""
    print(
        json.dumps({"ok": False, "error": message, "fix": fix}, ensure_ascii=False), file=sys.stderr
    )
    sys.exit(1)


def user_id(given: str | None) -> str:
    if given:
        return given
    if CONFIG.is_file():
        try:
            configured = json.loads(CONFIG.read_text(encoding="utf-8")).get("user_id")
        except json.JSONDecodeError:
            fail(f"{CONFIG.name} is not valid JSON", f'write {{"user_id": "…"}} into {CONFIG}')
        else:
            if configured:
                return str(configured)
    fail(
        "no Goodreads user id",
        f'pass it as the first argument, or write {{"user_id": "…"}} into {CONFIG}',
    )
    raise AssertionError  # unreachable; fail() exits


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8", "replace")
    if not body.strip():
        # Goodreads answers a blocked scrape with 202 and an empty body rather than an
        # error status, so urllib raises nothing. Parsing that silence yields a record
        # of nulls that reads like a real answer, which is the failure worth catching.
        raise ScrapeBlocked(f"Goodreads returned {response.status} with an empty body")
    return body


def read_feed(args: argparse.Namespace, url: str) -> str:
    if getattr(args, "rss_file", None):
        return Path(args.rss_file).read_text(encoding="utf-8")
    return fetch(url)


def emit(payload: dict) -> None:
    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))


def cmd_shelf(args: argparse.Namespace) -> None:
    uid = user_id(args.user_id)
    limit = min(args.limit, 200)
    url = (
        f"https://www.goodreads.com/review/list_rss/{uid}"
        f"?shelf={urllib.parse.quote(args.shelf)}&per_page={limit}&sort={args.sort}&order=d"
    )
    emit({"user_id": uid, **parse_shelf(read_feed(args, url), args.shelf)})


def cmd_activity(args: argparse.Namespace) -> None:
    uid = user_id(args.user_id)
    url = f"https://www.goodreads.com/user/updates_rss/{uid}"
    emit({"user_id": uid, **parse_activity(read_feed(args, url), args.limit)})


def cmd_book(args: argparse.Namespace) -> None:
    page = fetch(f"https://www.goodreads.com/book/show/{args.book_id}")
    record = parse_book(page, args.book_id)
    if not record["title"]:
        raise ScrapeBlocked("the book page carried no title")
    emit(record)


def cmd_search(args: argparse.Namespace) -> None:
    query = urllib.parse.quote(args.query)
    page = fetch(f"https://www.goodreads.com/search?q={query}&search_type=books")
    books = parse_search(page, args.limit)
    if not books:
        # A served page that yields nothing means the markup moved, not that Goodreads
        # has no copy of a common title. Reporting an empty list as success would send
        # the caller off to say the book does not exist.
        raise ScrapeBlocked("the search page returned no recognisable results")
    emit({"query": args.query, "count": len(books), "books": books})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read Goodreads shelves, activity and books without an API key.",
        epilog=f"user_id is optional; it falls back to the user_id key in {CONFIG.name}.",
    )
    sub = parser.add_subparsers(dest="cmd")

    shelf = sub.add_parser("shelf", help="books on a shelf (default: read)")
    shelf.add_argument("user_id", nargs="?", help="optional; falls back to goodreads.json")
    shelf.add_argument(
        "--shelf", default="read", help="read | currently-reading | to-read | <name>"
    )
    shelf.add_argument("--limit", type=int, default=20, help="max books, capped at 200")
    shelf.add_argument(
        "--sort", default="date_added", help="date_read | date_added | rating | title"
    )
    shelf.add_argument("--rss-file", help="parse this saved feed instead of fetching")
    shelf.set_defaults(func=cmd_shelf)

    activity = sub.add_parser("activity", help="recent activity on the profile")
    activity.add_argument("user_id", nargs="?", help="optional; falls back to goodreads.json")
    activity.add_argument("--limit", type=int, default=20)
    activity.add_argument("--rss-file", help="parse this saved feed instead of fetching")
    activity.set_defaults(func=cmd_activity)

    book = sub.add_parser("book", help="details for one book (scraped, fields may be null)")
    book.add_argument("book_id")
    book.set_defaults(func=cmd_book)

    search = sub.add_parser("search", help="find books by title or author (scraped)")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except ScrapeBlocked as error:
        fail(str(error), BLOCKED_FIX)
    except Exception as error:  # noqa: BLE001 - every failure leaves as one JSON line
        fail(
            f"{type(error).__name__}: {error}",
            "Goodreads may have changed its pages; report this rather than scraping around it",
        )


if __name__ == "__main__":
    main()
