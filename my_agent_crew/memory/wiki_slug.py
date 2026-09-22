"""Turning a page title into the file name that page keeps.

The slug is the page's identity: a compile finds an existing page by slugging the title
it was given, so two titles that slug the same are one page, and a title that slugs
differently after an edit is a new page beside the old one. That makes this a small
function with large consequences, which is why it lives on its own.
"""

from __future__ import annotations

import re

from my_agent_crew.memory.search import normalize

#: For a title that survives normalization with nothing left, such as one made only of
#: punctuation. It is deliberately not a catch-all: see `slugify`.
UNTITLED = "khong-ten"


def slugify(title: str) -> str:
    """A file name for a title, stable enough that the same thing keeps the same page.

    Accents are dropped through the same `normalize` the search uses, so `Hạn Eco` and
    `han eco` are one page rather than two that each know half the story. That matters
    more here than in search: a duplicate hit is noise, a duplicate page is a fork.

    What is kept is every letter and digit of any script, not just `a-z0-9`. A live
    compile filed a Japanese book title under `UNTITLED`, and a fallback shared by every
    non-Latin title is not a bad name but a merge: the next such book would land on the
    same page and overwrite it.
    """
    plain = normalize(title)
    kept = "".join(ch if ch.isalnum() else "-" for ch in plain)
    slug = re.sub(r"-+", "-", kept).strip("-")
    return slug or UNTITLED
