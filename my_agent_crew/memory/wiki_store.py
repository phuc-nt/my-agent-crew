"""The wiki vault: one page per thing the agent knows about, as files on disk.

A daily note records what happened on a day. That is the right shape for writing and the
wrong shape for asking: "what do I know about the Eco Retreat deadline" is spread over
eleven notes, and the answer is whichever fragment the search happened to rank first. A
page gathers those fragments under the name of the thing itself, so the question has one
place to be answered from.

Two rules make the vault safe to regenerate:

* **A page records where it came from.** `sources` lists the notes or conversations the
  page was built out of, so a claim can be traced back rather than believed. A page with
  no sources is a page that made itself up, and the lint says so.
* **Only part of the file is machine-owned.** Everything between the related markers is
  rewritten on every compile; everything else belongs to whoever wrote it, model or
  person, and a compile must return it unchanged. Without that split the vault would be
  either frozen or untrustworthy — a compile would overwrite the one correction someone
  made by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from my_agent_crew.memory.wiki_slug import slugify

__all__ = ["slugify"]  # re-exported: a page's slug is part of this module's surface

SEPARATOR = "---"

#: The three folders a page can live in. `entities` are things with names (a person, a
#: place, a contract), `concepts` are ideas that recur, `syntheses` are pages written
#: across several others rather than out of notes directly.
KINDS = ("entities", "concepts", "syntheses")

#: A page is either believed or flagged for a person to look at. Anything the compile is
#: unsure of lands in `review` rather than being dropped, because a quiet drop loses the
#: very thing that needed attention.
STATUSES = ("ok", "review")

WIKI_DIRNAME = "wiki"
INDEX_NAME = "index.md"


@dataclass(frozen=True)
class Page:
    slug: str
    kind: str
    title: str
    body: str
    sources: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    status: str = "ok"
    updated: str = ""

    @property
    def path_parts(self) -> tuple[str, str]:
        return self.kind, f"{self.slug}.md"

    def to_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "sources": list(self.sources),
            "questions": list(self.questions),
            "status": self.status,
            "updated": self.updated,
        }


def wiki_dir(memory_dir: Path) -> Path:
    return memory_dir / WIKI_DIRNAME


def check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"kind phải là một trong {', '.join(KINDS)}, nhận {kind!r}")
    return kind


def check_slug(slug: str) -> str:
    """A slug becomes a path, so anything that could climb out of the vault is refused.

    What is allowed is a letter or digit of any script, plus `-` between them. Restricting
    it to `a-z0-9` would be the wrong guard: it refuses a Japanese title, which is a page
    name and not an attack, while a separator or a dot segment is refused either way.

    An uppercase letter is still refused, because `slugify` lowercases: `HOA` beside `hoa`
    is one page written twice, and on a case-insensitive filesystem it is one file that
    two slugs both claim. Scripts without case are unaffected — they have no other form
    to collide with.
    """
    if not slug or slug[0] == "-" or slug[-1] == "-" or slug != slug.lower():
        raise ValueError(f"slug không hợp lệ: {slug!r}")
    if not all(ch.isalnum() or ch == "-" for ch in slug):
        raise ValueError(f"slug không hợp lệ: {slug!r}")
    return slug


def _as_list(value: object) -> list[str]:
    """Frontmatter written by a model is not always a list. One string is one item."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip() if value else ""
    return [text] if text else []


def parse_page(path: Path, kind: str) -> Page | None:
    """None when the file is not a page we wrote; a broken file must not break the vault."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith(SEPARATOR):
        return None
    _, _, rest = text.partition("\n")
    front, sep, body = rest.partition(f"\n{SEPARATOR}\n")
    if not sep:
        return None
    try:
        data = yaml.safe_load(front) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    status = str(data.get("status", "ok"))
    return Page(
        slug=path.stem,
        kind=kind,
        title=str(data.get("title") or path.stem),
        body=body.strip(),
        sources=_as_list(data.get("sources")),
        questions=_as_list(data.get("questions")),
        status=status if status in STATUSES else "review",
        updated=str(data.get("updated", "")),
    )


def render_page(page: Page) -> str:
    front = {
        "title": page.title,
        "kind": page.kind,
        "sources": list(page.sources),
        "questions": list(page.questions),
        "status": page.status,
        "updated": page.updated,
    }
    dumped = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    return f"{SEPARATOR}\n{dumped}\n{SEPARATOR}\n\n{page.body.strip()}\n"


def read_page(memory_dir: Path, kind: str, slug: str) -> Page | None:
    path = wiki_dir(memory_dir) / check_kind(kind) / f"{check_slug(slug)}.md"
    return parse_page(path, kind) if path.is_file() else None


def find_page(memory_dir: Path, slug: str) -> Page | None:
    """The page with this slug in whichever folder holds it.

    Callers that have only a wikilink have only a name: a link says `[[Hạn Eco]]`, never
    which of the three folders the target sits in.
    """
    for kind in KINDS:
        page = read_page(memory_dir, kind, slug)
        if page is not None:
            return page
    return None


def list_pages(memory_dir: Path) -> list[Page]:
    """Every page in the vault, ordered by kind then slug so the index is stable."""
    root = wiki_dir(memory_dir)
    pages: list[Page] = []
    for kind in KINDS:
        directory = root / kind
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            page = parse_page(path, kind)
            if page is not None:
                pages.append(page)
    return pages


def write_page(memory_dir: Path, page: Page, today: date | None = None) -> Page:
    """Write one page, stamping `updated` when the caller did not."""
    stamped = page
    if not page.updated:
        stamped = Page(**{**page.to_dict(), "updated": (today or date.today()).isoformat()})  # type: ignore[arg-type]
    check_kind(stamped.kind)
    check_slug(stamped.slug)
    directory = wiki_dir(memory_dir) / stamped.kind
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stamped.slug}.md").write_text(render_page(stamped), encoding="utf-8")
    return stamped
