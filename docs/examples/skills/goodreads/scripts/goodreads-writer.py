#!/usr/bin/env python3
"""Write to Goodreads by driving the site, because the API closed in December 2020.

Reached through `goodreads-write.sh`, which owns the Playwright environment and the
browser profile. Run directly it will still work, but the wrapper is what turns a
missing environment into a line telling you how to build it.

The session lives in a persistent browser profile beside this script. Nothing here
ever types a password: `login` opens a window for a person to use once, and every
other command either finds a live session or says so and stops. A command that tried
to log itself back in would sit at a captcha with nobody watching.

Usage:
  goodreads-writer.py login
  goodreads-writer.py status
  goodreads-writer.py rate <book_id> <1-5>
  goodreads-writer.py shelf <book_id> <read|currently-reading|to-read>
  goodreads-writer.py progress <book_id> <percent>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = "https://www.goodreads.com"
PROFILE = Path(__file__).resolve().parent.parent / ".browser-data"
TIMEOUT_MS = 20_000

# Goodreads labels its shelf buttons with these exact strings.
SHELVES = {
    "read": "Read",
    "currently-reading": "Currently reading",
    "to-read": "Want to read",
    "want-to-read": "Want to read",
}

RELOGIN = "run goodreads-write.sh login in a terminal, then retry"


def emit(payload: dict) -> None:
    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))
    sys.exit(0)


def fail(error: str, fix: str) -> None:
    """Stderr only. stdout is what a caller pipes into jq."""
    print(
        json.dumps({"ok": False, "error": error, "fix": fix}, ensure_ascii=False), file=sys.stderr
    )
    sys.exit(1)


def open_context(playwright, headless: bool):
    PROFILE.mkdir(parents=True, exist_ok=True)
    PROFILE.chmod(0o700)
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE),
        headless=headless,
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        # Goodreads serves a different page to an obviously-automated browser, and the
        # difference is invisible until a selector silently matches nothing.
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    context.set_default_timeout(TIMEOUT_MS)
    return context


def logged_in(page) -> bool:
    page.goto(BASE, wait_until="domcontentloaded")
    if "sign_in" in page.url or "sign_up" in page.url:
        return False
    try:
        page.wait_for_selector(
            'a[href*="/review/list"], nav a[href*="my_books"], a[href*="/user/show"]',
            timeout=8000,
        )
    except Exception:
        return False
    return True


def open_book(page, book_id: str) -> str:
    page.goto(f"{BASE}/book/show/{book_id}", wait_until="domcontentloaded")
    title = page.text_content('h1[data-testid="bookTitle"], h1.Text__title1')
    if not title:
        fail(
            f"book {book_id} did not load a title",
            "check the book id, or Goodreads may be blocking this session",
        )
    return title.strip()


def cmd_login(args, playwright) -> None:
    context = open_context(playwright, headless=False)
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(f"{BASE}/user/sign_in", wait_until="domcontentloaded")
    print("A browser window is open. Sign in, then close the window.", file=sys.stderr)
    try:
        page.wait_for_event("close", timeout=300_000)
    except Exception:
        pass
    context.close()
    emit({"action": "login", "message": "session saved; run status to confirm"})


def cmd_status(args, playwright) -> None:
    context = open_context(playwright, headless=True)
    page = context.pages[0] if context.pages else context.new_page()
    live = logged_in(page)
    context.close()
    if not live:
        fail("session expired", RELOGIN)
    emit({"action": "status", "message": "session is live"})


def _with_session(playwright):
    context = open_context(playwright, headless=True)
    page = context.pages[0] if context.pages else context.new_page()
    if not logged_in(page):
        context.close()
        fail("session expired", RELOGIN)
    return context, page


def cmd_rate(args, playwright) -> None:
    stars = int(args.stars)
    if not 1 <= stars <= 5:
        fail(f"rating {stars} is outside 1-5", "pass a whole number from 1 to 5")
    context, page = _with_session(playwright)
    title = open_book(page, args.book_id)
    button = page.query_selector(f'button[aria-label="Rate {stars} out of 5"]')
    if not button:
        context.close()
        fail(
            "no rating control on the page",
            "Goodreads may have changed the book page; report this rather than guessing",
        )
    button.click()
    page.wait_for_timeout(2000)
    context.close()
    emit({"action": "rate", "book_id": args.book_id, "title": title, "stars": stars})


def cmd_shelf(args, playwright) -> None:
    key = args.shelf.lower().replace(" ", "-")
    label = SHELVES.get(key)
    if not label:
        fail(f"unknown shelf {args.shelf!r}", f"one of: {', '.join(sorted(SHELVES))}")
    context, page = _with_session(playwright)
    title = open_book(page, args.book_id)
    trigger = page.query_selector('button[aria-label*="shelve" i], button.WantToReadButton')
    if trigger:
        trigger.click()
        page.wait_for_timeout(1500)
    button = page.query_selector(f'button[aria-label="{label}"]')
    if not button:
        context.close()
        fail(
            f"no control for shelf {label!r}",
            "Goodreads may have changed the shelving overlay; report this",
        )
    button.click()
    page.wait_for_timeout(2000)
    close = page.query_selector('.Overlay button[aria-label="Close"]')
    if close and close.is_visible():
        close.click()
    context.close()
    emit({"action": "shelf", "book_id": args.book_id, "title": title, "shelf": key})


def cmd_progress(args, playwright) -> None:
    percent = int(args.percent)
    if not 0 <= percent <= 100:
        fail(f"progress {percent} is outside 0-100", "pass a whole number from 0 to 100")
    context, page = _with_session(playwright)
    title = open_book(page, args.book_id)
    trigger = page.get_by_text("Update progress", exact=False)
    if not trigger.count():
        context.close()
        fail(
            "no progress control on the page",
            "progress is only offered for a book on the currently-reading shelf",
        )
    trigger.first.click()
    page.wait_for_timeout(1500)
    field = page.query_selector('input[type="number"], input[name*="percent" i]')
    if not field:
        context.close()
        fail(
            "no progress field appeared",
            "Goodreads may have changed the progress dialog; report this",
        )
    field.fill(str(percent))
    save = page.get_by_role("button", name="Save").or_(page.get_by_role("button", name="Update"))
    save.first.click()
    page.wait_for_timeout(2000)
    context.close()
    emit({"action": "progress", "book_id": args.book_id, "title": title, "percent": percent})


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
