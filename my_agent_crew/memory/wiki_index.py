"""The list of wiki page names that rides in the system prompt.

Names only, never bodies. A vault of any size would swamp the prompt if it were pasted
in, and a model given a page's title without its text will answer from the title — so
the section says, in as many words, that this is an index and `wiki_get` is what reads.

The three tiers below exist because the failure changes shape as the vault grows. A
small vault is worth listing in full. A large one listed in full stops being scannable
and becomes a second prompt competing with the first. A very large one cannot be listed
at all, so the honest thing is to report its shape and let the agent search.
"""

from __future__ import annotations

from pathlib import Path

from my_agent_crew.memory import wiki_store
from my_agent_crew.tools import wiki_texts as texts

#: Above this many pages the index is names alone, grouped by folder.
GROUPED_ABOVE = 40
#: Above this many it is only the count per folder: any list this long is skimmed, not read.
COUNTS_ONLY_ABOVE = 200


def _by_kind(pages: list[wiki_store.Page]) -> dict[str, list[wiki_store.Page]]:
    grouped: dict[str, list[wiki_store.Page]] = {kind: [] for kind in wiki_store.KINDS}
    for page in pages:
        grouped.setdefault(page.kind, []).append(page)
    return {kind: found for kind, found in grouped.items() if found}


def index_body(pages: list[wiki_store.Page]) -> str:
    """The body of the Wiki section for these pages, or `""` when the vault is empty.

    An empty vault gets no section at all rather than an empty heading: a heading with
    nothing under it reads as a fault, and it would invite the model to mention a wiki
    the person has never seen.
    """
    if not pages:
        return ""
    lines = [texts.WIKI_PROMPT_HINT, ""]
    grouped = _by_kind(pages)
    if len(pages) > COUNTS_ONLY_ABOVE:
        lines.append(texts.WIKI_PROMPT_COUNT.format(count=len(pages)))
        lines.extend(f"- {kind}: {len(found)}" for kind, found in grouped.items())
        return "\n".join(lines)
    names_only = len(pages) > GROUPED_ABOVE
    for kind, found in grouped.items():
        lines.append(f"- {kind}:")
        for page in found:
            # The slug is what `wiki_get` takes, the title is what the page is called;
            # both are needed because the model reads one and must type the other.
            label = page.slug if names_only else f"{page.slug} — {page.title}"
            lines.append(f"  - {label}")
    return "\n".join(lines)


def wiki_section(memory_dir: Path) -> tuple[str, str] | None:
    """`(title, body)` for the prompt, or `None` when there is nothing to index."""
    body = index_body(wiki_store.list_pages(memory_dir))
    return (texts.WIKI_SECTION_TITLE, body) if body else None
