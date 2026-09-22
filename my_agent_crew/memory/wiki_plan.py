"""Turning what the model wrote into a set of page writes, and back again.

This is the half of a compile with no network and no disk in it, so the part that decides
what happens to the vault can be tested exactly. The job in `wiki_compile.py` supplies the
model output; everything here is a pure function of it.

The parsing is deliberately forgiving in one direction only. A model asked for a list of
pages will sometimes wrap it in prose, or fence it, or get one page's shape wrong out of
six. Losing the other five because of the sixth is the worst outcome, so items are parsed
one at a time and a bad one is dropped. What is never forgiven is a page with no sources:
that is not a formatting slip, it is the vault losing the property that makes it worth
reading.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from my_agent_crew.memory import wiki_store

#: A page needs a name and something to say; anything shorter is a stub the model emitted
#: to fill out a list, and a vault of stubs is worse than a small vault.
MIN_BODY_CHARS = 40


@dataclass(frozen=True)
class Planned:
    """One page a compile wants to write, already checked."""

    slug: str
    kind: str
    title: str
    body: str
    sources: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    status: str = "ok"

    def to_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "sources": self.sources,
            "questions": self.questions,
            "status": self.status,
        }


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip() if value else ""
    return [text] if text else []


def _strip_fence(text: str) -> str:
    """A fenced block's contents, or the text unchanged. Models fence JSON by habit."""
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _items(text: str) -> list[dict]:
    """The page-shaped objects in the model's reply, or none.

    A whole-document parse is tried first because that is the normal case. When it fails
    the objects are pulled out one at a time, so prose around the list costs nothing.
    """
    body = _strip_fence(text)
    try:
        loaded = json.loads(body)
    except json.JSONDecodeError:
        return _salvage(body)
    if isinstance(loaded, dict):
        loaded = loaded.get("pages", [])
    return [item for item in loaded if isinstance(item, dict)] if isinstance(loaded, list) else []


def _salvage(body: str) -> list[dict]:
    """Every balanced `{...}` that parses on its own, in order.

    One malformed page must not cost the rest: a compile that drops five good pages over
    a sixth one's stray comma is a compile nobody will trust to run unattended.
    """
    found: list[dict] = []
    depth = 0
    start = -1
    for index, char in enumerate(body):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0:
                try:
                    item = json.loads(body[start : index + 1])
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    found.append(item)
    return found


def plan_pages(text: str) -> list[Planned]:
    """What this model reply asks the vault to become, with the unusable dropped.

    Dropped rather than repaired: a page missing its sources cannot be repaired here
    without inventing them, and an invented source is the one thing the vault must not
    contain.
    """
    planned: list[Planned] = []
    seen: set[str] = set()
    for item in _items(text):
        title = str(item.get("title") or item.get("page") or "").strip()
        body = str(item.get("body") or "").strip()
        sources = _as_list(item.get("sources"))
        if not title or len(body) < MIN_BODY_CHARS or not sources:
            continue
        kind = str(item.get("kind") or "entities").strip()
        if kind not in wiki_store.KINDS:
            kind = "entities"
        slug = wiki_store.slugify(title)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        status = str(item.get("status") or "ok").strip()
        planned.append(
            Planned(
                slug=slug,
                kind=kind,
                title=title,
                body=body,
                sources=sources,
                questions=_as_list(item.get("questions")),
                status=status if status in wiki_store.STATUSES else "ok",
            )
        )
    return planned


def planned_from_dicts(items: list[dict]) -> list[Planned]:
    """The inverse of `to_dict`, for reading a proposal back at approval time."""
    return [
        Planned(
            slug=str(item["slug"]),
            kind=str(item["kind"]),
            title=str(item["title"]),
            body=str(item["body"]),
            sources=_as_list(item.get("sources")),
            questions=_as_list(item.get("questions")),
            status=str(item.get("status") or "ok"),
        )
        for item in items
        if item.get("slug") and item.get("title")
    ]
