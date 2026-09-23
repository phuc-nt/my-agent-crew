"""The browser session behind every Goodreads write: one persistent profile beside
the scripts, a check that it is still signed in, and the two commands that manage it.

Nothing here ever types a password. `login` opens a window for a person to use once,
and every other command either finds a live session or says so and stops. A command
that tried to log itself back in would sit at a captcha with nobody watching.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = "https://www.goodreads.com"
PROFILE = Path(__file__).resolve().parent.parent / ".browser-data"
TIMEOUT_MS = 20_000

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
    # The HTML arrives with the title but without the controls: the rating stars and
    # the shelving menu appear only once the page's scripts have run. Looking for them
    # at domcontentloaded finds nothing, and a button clicked before then does nothing.
    try:
        page.wait_for_selector('button[aria-label="Rate 1 out of 5"]', timeout=TIMEOUT_MS)
    except Exception:
        fail(
            f"book {book_id} never finished rendering its controls",
            "retry once; if it repeats, Goodreads may have changed the book page",
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


def with_session(playwright):
    context = open_context(playwright, headless=True)
    page = context.pages[0] if context.pages else context.new_page()
    if not logged_in(page):
        context.close()
        fail("session expired", RELOGIN)
    return context, page
