"""Wikilinks between pages, and the one block of a page that the machine owns.

A page body is written by a model or a person and must survive every compile untouched.
But a vault is only useful if each page says what it connects to, and those connections
change whenever *another* page changes — so they cannot be written by hand either.

The split is a pair of markers. Everything between them is regenerated on every compile;
everything outside is returned exactly as it was found. `split_managed` and `set_managed`
are the only two functions that know where the line is, so there is one place to be right.
"""

from __future__ import annotations

import re

from my_agent_crew.memory.wiki_store import slugify

OPEN = "<!-- wiki:related -->"
CLOSE = "<!-- /wiki:related -->"

#: `[[Tên trang]]`, the whole name between the brackets. Nothing else in a note looks like
#: this, so the pattern can stay simple; a link with no closing bracket is not a link.
LINK_PATTERN = re.compile(r"\[\[([^\[\]]+)\]\]")

_BLOCK_PATTERN = re.compile(re.escape(OPEN) + r".*?" + re.escape(CLOSE), re.DOTALL)


def links_in(text: str) -> list[str]:
    """The slugs this text points at, in order, without repeats.

    Slugs rather than the written names: `[[Hạn Eco]]` and `[[hạn eco]]` are the same
    target, and a caller resolving links wants one lookup, not two.
    """
    seen: list[str] = []
    for raw in LINK_PATTERN.findall(text):
        slug = slugify(raw.strip())
        if slug and slug not in seen:
            seen.append(slug)
    return seen


def split_managed(body: str) -> tuple[str, str]:
    """`(what the author wrote, what the machine wrote)`.

    A body with no block yet is all author's, which is the normal case the first time a
    page is written.
    """
    match = _BLOCK_PATTERN.search(body)
    if match is None:
        return body.strip(), ""
    managed = match.group(0)
    authored = (body[: match.start()] + body[match.end() :]).strip()
    return authored, managed


def authored_body(body: str) -> str:
    """Just the part a compile must not touch."""
    return split_managed(body)[0]


def render_related(links: list[str], backlinks: list[str]) -> str:
    """The managed block for a page. Empty on both sides means no block at all.

    An empty block would be a heading with nothing under it on most pages in a young
    vault, which reads as a fault rather than as an absence.
    """
    if not links and not backlinks:
        return ""
    lines = [OPEN, "", "## Liên quan", ""]
    if links:
        lines.append("Trang này nhắc tới: " + ", ".join(f"[[{slug}]]" for slug in links))
    if backlinks:
        lines.append("Được nhắc tới ở: " + ", ".join(f"[[{slug}]]" for slug in backlinks))
    lines.extend(["", CLOSE])
    return "\n".join(lines)


def set_managed(body: str, block: str) -> str:
    """Replace the machine's part, leaving the author's part exactly as it was."""
    authored, _ = split_managed(body)
    if not block:
        return authored
    return f"{authored}\n\n{block}\n" if authored else f"{block}\n"


def backlinks_of(pages: dict[str, str]) -> dict[str, list[str]]:
    """For each slug, which pages point at it.

    `pages` maps slug to body. Only the authored part counts: counting the managed block
    too would make every link mutual the moment it was rendered once, and the second
    compile would report a graph it had itself invented.
    """
    found: dict[str, list[str]] = {slug: [] for slug in pages}
    for slug, body in sorted(pages.items()):
        for target in links_in(authored_body(body)):
            if target != slug and target in found and slug not in found[target]:
                found[target].append(slug)
    return found
