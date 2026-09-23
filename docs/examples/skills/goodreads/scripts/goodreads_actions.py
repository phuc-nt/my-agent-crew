"""The four writes Goodreads offers on a book page: rate, shelve, progress, review.

Each one finds its control by the label Goodreads gives it, and stops with a JSON error
rather than guessing when the control is missing. A wrong guess on a public profile
costs more than a failed run.
"""

from __future__ import annotations

from goodreads_session import BASE, TIMEOUT_MS, emit, fail, open_book, with_session

# Goodreads labels its shelf buttons with these exact strings, capitals included. The
# shelf already chosen reads "<label>, selected", so an exact match never picks it.
SHELVES = {
    "read": "Read",
    "currently-reading": "Currently Reading",
    "to-read": "Want to Read",
    "want-to-read": "Want to Read",
}

RELOGIN = "run goodreads-write.sh login in a terminal, then retry"


def cmd_rate(args, playwright) -> None:
    stars = int(args.stars)
    if not 1 <= stars <= 5:
        fail(f"rating {stars} is outside 1-5", "pass a whole number from 1 to 5")
    context, page = with_session(playwright)
    title = open_book(page, args.book_id)
    # The header and the review section each carry a row of stars, and the header is
    # rendered twice for narrow and wide layouts; the first visible row is the reader's.
    button = page.locator(f'button[aria-label="Rate {stars} out of 5"]:visible').first
    if not button.count():
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
    context, page = with_session(playwright)
    title = open_book(page, args.book_id)
    # Only the "edit shelf" control is safe to press blind: on a book not yet shelved
    # the main button shelves it as Want to Read the moment it is clicked.
    trigger = page.locator('button[aria-label*="edit shelf" i]:visible').first
    if not trigger.count():
        context.close()
        fail(
            "no edit-shelf control; the book may not be on any shelf yet",
            "shelve it once on the site, or report this if it is already shelved",
        )
    trigger.click()
    button = page.locator(f'.Overlay button[aria-label="{label}"]:visible').first
    try:
        button.wait_for(timeout=TIMEOUT_MS)
    except Exception:
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
    context, page = with_session(playwright)
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


def cmd_review(args, playwright) -> None:
    text = args.text.strip()
    if not text:
        fail("the review text is empty", "pass the review as one quoted argument")
    context, page = with_session(playwright)
    # The editor carries the rating, shelf and read dates already set, so posting it
    # changes only the text. An existing review is replaced, not appended to.
    page.goto(f"{BASE}/review/edit/{args.book_id}", wait_until="domcontentloaded")
    box = page.locator("textarea.FormControl__textarea:visible").first
    try:
        box.wait_for(timeout=TIMEOUT_MS)
    except Exception:
        context.close()
        fail(
            "no review box on the editor page",
            "check the book id, or Goodreads may have changed the editor; report this",
        )
    box.fill(text)
    page.get_by_role("button", name="Post your review").first.click()
    try:
        page.wait_for_url(lambda url: "/review/edit/" not in url, timeout=TIMEOUT_MS)
    except Exception:
        context.close()
        fail(
            "the editor stayed open after posting",
            "report this rather than posting again; the review may already be up",
        )
    context.close()
    emit({"action": "review", "book_id": args.book_id, "chars": len(text)})
