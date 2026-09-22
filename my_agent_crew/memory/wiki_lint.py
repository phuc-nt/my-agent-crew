"""What is wrong with the vault, as facts rather than as an opinion.

A vault degrades quietly. A page loses its last source in a rewrite, a link points at a
page nobody wrote, a page stops being updated while the thing it describes moves on.
None of that raises an error, and none of it is visible from any single page — which is
exactly why it needs a report that reads the whole vault at once.

The two dashboards this produces answer the two questions a person actually asks: what
does the agent still not know (open questions), and what have I stopped being able to
trust (stale, unsourced, dangling).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from my_agent_crew.memory import wiki_links, wiki_store

#: Older than this and a page is reported as stale. Not deleted, not flagged on the page
#: itself: a page can be old and perfectly correct, so this is a prompt to look, never a
#: judgement that the page is wrong.
STALE_DAYS = 90


@dataclass(frozen=True)
class Problem:
    slug: str
    kind: str
    detail: str


def _parse_day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def unsourced(pages: list[wiki_store.Page]) -> list[Problem]:
    """Pages that cannot say where they came from. The worst state a page can be in:
    it still reads as knowledge while having stopped being traceable."""
    return [Problem(page.slug, "unsourced", page.title) for page in pages if not page.sources]


def dangling(pages: list[wiki_store.Page]) -> list[Problem]:
    """Links pointing at pages nobody has written.

    Reported rather than removed: a dangling link is usually a page that *should* exist,
    so it is a to-do list for the next compile, not a fault to clean away.
    """
    known = {page.slug for page in pages}
    found: list[Problem] = []
    for page in pages:
        for target in wiki_links.links_in(wiki_links.authored_body(page.body)):
            if target not in known:
                found.append(Problem(page.slug, "dangling", target))
    return found


def stale(pages: list[wiki_store.Page], today: date, days: int = STALE_DAYS) -> list[Problem]:
    """Pages not touched for a long time, and pages with no date at all.

    An undated page counts as stale because there is no evidence it is current, and
    treating absence of evidence as freshness is how a vault starts lying.
    """
    found: list[Problem] = []
    for page in pages:
        day = _parse_day(page.updated)
        if day is None:
            found.append(Problem(page.slug, "stale", "không có ngày cập nhật"))
        elif (today - day).days > days:
            found.append(Problem(page.slug, "stale", f"{(today - day).days} ngày"))
    return found


def needs_review(pages: list[wiki_store.Page]) -> list[Problem]:
    return [Problem(page.slug, "review", page.title) for page in pages if page.status != "ok"]


def open_questions(pages: list[wiki_store.Page]) -> list[tuple[str, str]]:
    """`(slug, question)` for everything the vault admits it does not know."""
    return [(page.slug, question) for page in pages for question in page.questions]


def lint(memory_dir: Path, today: date | None = None) -> list[Problem]:
    """Every problem in the vault, grouped by sort so a report reads in one pass."""
    pages = wiki_store.list_pages(memory_dir)
    today = today or date.today()
    return unsourced(pages) + dangling(pages) + needs_review(pages) + stale(pages, today)
