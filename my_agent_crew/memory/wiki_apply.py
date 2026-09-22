"""Writing a planned set of pages into the vault, then rebuilding the link graph.

The graph is rebuilt across the whole vault rather than for the pages just written,
because a new page changes what *other* pages link to: writing `[[hạn eco]]` on a new
page means the Hạn Eco page has gained a backlink it cannot know about. A partial rebuild
would leave the vault describing a graph that was true one compile ago.

Nothing here talks to a model. Given the same plan and the same vault it does the same
thing, which is what makes a compile safe to run unattended.
"""

from __future__ import annotations

import json
from pathlib import Path

from my_agent_crew.memory import wiki_links, wiki_store
from my_agent_crew.memory.wiki_plan import Planned, planned_from_dicts
from my_agent_crew.memory.wiki_reports import write_reports

#: A whole batch of pages, as JSON in the proposal's body, decided in one approval.
#: It lives here rather than with the job so applying an approval needs nothing that
#: talks to a model.
WIKI_COMPILE = "wiki_compile"


def apply_wiki_proposal(memory_dir: Path, body: str) -> tuple[int, int]:
    """Write an approved batch of pages. `(pages written, pages whose links changed)`.

    The batch is read back out of the proposal rather than passed in, so approving from
    the web days later writes exactly what the run proposed and nothing else.
    """
    try:
        items = json.loads(body)
    except json.JSONDecodeError:
        return 0, 0
    planned = planned_from_dicts(items if isinstance(items, list) else [])
    if not planned:
        return 0, 0
    written = write_planned(memory_dir, planned)
    changed = rebuild_links(memory_dir)
    # Regenerated here rather than by the job, so a batch approved from the web days
    # later leaves the dashboards describing the vault as it now is. A report that
    # lags the thing it reports on is worse than no report.
    write_reports(memory_dir)
    return len(written), changed


def capture_previous(memory_dir: Path, planned: list[Planned]) -> list[dict]:
    """What the pages about to be overwritten say now, so one step back stays possible.

    Only the pages that already exist: a new page's "previous" is its absence, and
    recording an empty page instead would make an undo write blanks over nothing.
    """
    previous: list[dict] = []
    for page in planned:
        existing = wiki_store.find_page(memory_dir, page.slug)
        if existing is not None:
            previous.append(
                {
                    "slug": existing.slug,
                    "kind": existing.kind,
                    "title": existing.title,
                    "body": wiki_links.authored_body(existing.body),
                    "sources": existing.sources,
                    "questions": existing.questions,
                    "status": existing.status,
                }
            )
    return previous


def write_planned(memory_dir: Path, planned: list[Planned]) -> list[str]:
    """Write each page, keeping the folder an existing page already lives in.

    Returns the slugs written. The managed link block is dropped on purpose: it is
    regenerated from the whole vault immediately afterwards, and carrying the old one
    through would briefly leave a page claiming links the compile has just changed.
    """
    written: list[str] = []
    for page in planned:
        existing = wiki_store.find_page(memory_dir, page.slug)
        wiki_store.write_page(
            memory_dir,
            wiki_store.Page(
                slug=page.slug,
                kind=existing.kind if existing is not None else page.kind,
                title=page.title,
                body=page.body,
                sources=page.sources,
                questions=page.questions,
                status=page.status,
            ),
        )
        written.append(page.slug)
    return written


def rebuild_links(memory_dir: Path) -> int:
    """Regenerate every page's related block from the vault as it now stands.

    Returns how many pages changed. A page whose block is already right is not rewritten,
    so a compile that adds nothing new leaves every file's timestamp alone and the vault
    reads as untouched, because it was.
    """
    pages = wiki_store.list_pages(memory_dir)
    bodies = {page.slug: page.body for page in pages}
    backlinks = wiki_links.backlinks_of(bodies)
    known = set(bodies)
    changed = 0
    for page in pages:
        authored = wiki_links.authored_body(page.body)
        # Only links to pages that exist: a link to a page nobody has written yet is a
        # note to self in the author's text, not an edge in the graph.
        outgoing = [slug for slug in wiki_links.links_in(authored) if slug in known]
        block = wiki_links.render_related(outgoing, backlinks.get(page.slug, []))
        body = wiki_links.set_managed(page.body, block)
        if body.strip() == page.body.strip():
            continue
        # The page keeps its `updated` stamp: the machine redrawing a link block is not
        # the page having been revised, and dating it today would hide when the words
        # that matter last changed.
        wiki_store.write_page(memory_dir, wiki_store.Page(**{**page.to_dict(), "body": body}))  # type: ignore[arg-type]
        changed += 1
    return changed
