#!/usr/bin/env python3
"""Write to Goodreads by driving the site, because the API closed in December 2020.

Reached through `goodreads-write.sh`, which owns the Playwright environment and the
browser profile. Run directly it will still work, but the wrapper is what turns a
missing environment into a line telling you how to build it.

This file is only the command line. The browser session lives in
`goodreads_session.py`, and the writes themselves in `goodreads_actions.py`.

Usage:
  goodreads-writer.py login
  goodreads-writer.py status
  goodreads-writer.py rate <book_id> <1-5>
  goodreads-writer.py shelf <book_id> <read|currently-reading|to-read>
  goodreads-writer.py progress <book_id> <percent>
  goodreads-writer.py review <book_id> <text>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from goodreads_actions import (  # noqa: E402
    SHELVES,
    cmd_progress,
    cmd_rate,
    cmd_review,
    cmd_shelf,
)
from goodreads_session import cmd_login, cmd_status, fail  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write to Goodreads through a saved session.")
    sub = parser.add_subparsers(dest="cmd")

    login = sub.add_parser("login", help="open a window to sign in once (a person must do this)")
    login.set_defaults(func=cmd_login)

    status = sub.add_parser("status", help="say whether the saved session is still live")
    status.set_defaults(func=cmd_status)

    rate = sub.add_parser("rate", help="rate a book 1-5")
    rate.add_argument("book_id")
    rate.add_argument("stars")
    rate.set_defaults(func=cmd_rate)

    shelf = sub.add_parser("shelf", help="move a book to a shelf")
    shelf.add_argument("book_id")
    shelf.add_argument("shelf", help=" | ".join(sorted(SHELVES)))
    shelf.set_defaults(func=cmd_shelf)

    progress = sub.add_parser("progress", help="set reading progress as a percentage")
    progress.add_argument("book_id")
    progress.add_argument("percent")
    progress.set_defaults(func=cmd_progress)

    review = sub.add_parser("review", help="post or replace the review text for a book")
    review.add_argument("book_id")
    review.add_argument("text", help="the whole review, as one quoted argument")
    review.set_defaults(func=cmd_review)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        fail(
            "Playwright is not installed in this skill's environment",
            "use goodreads-write.sh, which reports the exact command to build it",
        )
    try:
        with sync_playwright() as playwright:
            args.func(args, playwright)
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001 - every failure leaves as one JSON line
        fail(
            f"{type(error).__name__}: {error}",
            "if this repeats, report it rather than retrying with different selectors",
        )


if __name__ == "__main__":
    main()
