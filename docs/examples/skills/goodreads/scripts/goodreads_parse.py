"""Turning Goodreads RSS and HTML into plain dicts.

Kept apart from the command-line script for one reason: nothing in here touches the
network, so a test can feed it a saved file and check the parse. The fetching half is
the half that cannot be tested offline, so it lives alone in the script and stays thin.
"""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime

# Goodreads stamps RSS dates in two shapes depending on the feed.
DATE_FORMATS = ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z")


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def clean_ws(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_date(raw: str | None) -> str | None:
    """A date Goodreads could not be read as one comes back untouched rather than as
    None, because the raw string still tells a reader more than a missing field does."""
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _book_url(book_id: str | None) -> str | None:
    return f"https://www.goodreads.com/book/show/{book_id}" if book_id else None


def parse_shelf(xml_text: str, shelf: str) -> dict:
    channel = ET.fromstring(xml_text).find("channel")
    if channel is None:
        raise ValueError("RSS has no <channel>; Goodreads may have returned an error page")
    title = channel.findtext("title") or ""
    books = []
    for item in channel.findall("item"):
        book_id = item.findtext("book_id")
        books.append(
            {
                "title": clean_ws(item.findtext("title")),
                "author": clean_ws(item.findtext("author_name")),
                "book_id": book_id,
                "isbn": item.findtext("isbn"),
                # Goodreads writes 0 here for a book the user has not rated.
                "user_rating": item.findtext("user_rating"),
                "average_rating": item.findtext("average_rating"),
                "date_read": parse_date(item.findtext("user_read_at")),
                "date_added": parse_date(item.findtext("user_date_added")),
                "review": strip_html(item.findtext("user_review")),
                "shelves": item.findtext("user_shelves"),
                "book_url": _book_url(book_id),
                "review_url": item.findtext("link"),
                "description": strip_html(item.findtext("book_description"))[:300],
                "published": item.findtext("book_published"),
            }
        )
    return {
        "user_name": title.replace(f"'s bookshelf: {shelf}", "").strip(),
        "shelf": shelf,
        "count": len(books),
        "books": books,
    }


def parse_activity(xml_text: str, limit: int) -> dict:
    channel = ET.fromstring(xml_text).find("channel")
    if channel is None:
        raise ValueError("RSS has no <channel>; Goodreads may have returned an error page")
    events = [
        {
            "title": clean_ws(item.findtext("title")),
            "date": parse_date(item.findtext("pubDate")),
            "link": item.findtext("link"),
            "summary": clean_ws(strip_html(item.findtext("description")))[:300],
        }
        for item in list(channel.findall("item"))[:limit]
    ]
    return {"count": len(events), "events": events}


def _schema(page: str) -> dict:
    """The JSON-LD block a book page carries. Absent or malformed on some pages, which
    is why every caller treats an empty dict as normal rather than as a failure."""
    found = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.DOTALL)
    if not found:
        return {}
    try:
        data = json.loads(found.group(1))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _author_name(data: dict) -> str | None:
    author = data.get("author")
    if isinstance(author, list):
        author = author[0] if author else None
    return author.get("name") if isinstance(author, dict) else None


def parse_book(page: str, book_id: str) -> dict:
    """Scraped, not read from an API, so every field can come back None. A page whose
    shape changed yields a mostly-empty record rather than an exception, because a
    missing description is worth reporting and a traceback is not."""
    data = _schema(page)
    title = clean_ws(html.unescape(data.get("name") or ""))
    if not title:
        found = re.search(r"<title>([^|<]+)", page)
        title = clean_ws(found.group(1)) if found else ""
    ratings = re.search(r'"ratingCount"\s*:\s*(\d+)', page)
    reviews = re.search(r'"reviewCount"\s*:\s*(\d+)', page)
    rating = data.get("aggregateRating")
    return {
        "book_id": book_id,
        "title": title,
        "author": _author_name(data),
        "average_rating": rating.get("ratingValue") if isinstance(rating, dict) else None,
        "rating_count": ratings.group(1) if ratings else None,
        "review_count": reviews.group(1) if reviews else None,
        "description": clean_ws(strip_html(data.get("description")))[:500],
        "isbn": data.get("isbn"),
        "published": data.get("datePublished"),
        "genres": data.get("genre") or [],
        "book_url": _book_url(book_id),
        "image_url": data.get("image"),
    }


def parse_search(page: str, limit: int) -> list[dict]:
    """Search has no feed, so this reads the results page. Titles and authors are
    matched separately from ids and lined up by position, which is why a title that
    does not line up comes back as None instead of being attached to the wrong book."""
    ids = re.findall(r"/book/show/(\d+)", page)
    titles = re.findall(r'class="bookTitle"[^>]*>\s*<span[^>]*>([^<]+)</span>', page)
    authors = re.findall(r'class="authorName"[^>]*>[^<]*<span[^>]*>([^<]+)</span>', page)
    books: list[dict] = []
    seen: set[str] = set()
    for index, book_id in enumerate(ids):
        if book_id in seen or len(books) >= limit:
            continue
        seen.add(book_id)
        books.append(
            {
                "book_id": book_id,
                "title": clean_ws(html.unescape(titles[index])) if index < len(titles) else None,
                "author": clean_ws(html.unescape(authors[index])) if index < len(authors) else None,
                "book_url": _book_url(book_id),
            }
        )
    return books
