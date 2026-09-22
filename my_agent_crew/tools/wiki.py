"""The three tools the agent uses on its wiki vault: read a page, search pages, write one.

`wiki_apply` is an upsert rather than a write, and deliberately narrow: it replaces the
part of the page a writer owns and never touches the machine-written block below it. So an
agent rewriting a page cannot destroy the link graph, and a compile regenerating the graph
cannot destroy the writing.

It also refuses a page with no sources. That looks like input validation and is really the
point of the vault: a page that cannot say where it came from is a page that made itself
up, and the cost of letting one in is that every other page becomes less believable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from my_agent_crew.memory import search as search_text
from my_agent_crew.memory import wiki_links, wiki_store
from my_agent_crew.tools import wiki_texts as texts
from my_agent_crew.tools.registry import Tool, ToolError

MAX_HITS = 8


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip() if value else ""
    return [text] if text else []


def search_wiki(memory_dir: Path, query: str, limit: int = MAX_HITS) -> list[tuple[str, str]]:
    """(slug, matching text) for the pages that match, best first.

    The title is searched with the body because a page is about its title, and someone
    looking for a page types the name of the thing rather than a phrase inside it.
    """
    files = [
        (page.slug, f"{page.title}\n{wiki_links.authored_body(page.body)}")
        for page in wiki_store.list_pages(memory_dir)
    ]
    return [(hit.source, hit.text) for hit in search_text.search(files, query, limit)]


def build_wiki_tools(memory_dir: Path) -> list[Tool]:
    async def get(args: dict[str, Any]) -> str:
        slug = wiki_store.slugify(str(args.get("page", "")))
        page = wiki_store.find_page(memory_dir, slug) if slug else None
        if page is None:
            raise ToolError(texts.WIKI_NOT_FOUND.format(slug=slug or args.get("page", "")))
        head = f"# {page.title}\n"
        meta = f"nguồn: {', '.join(page.sources) or '(chưa có)'}"
        if page.questions:
            meta += f"\ncâu hỏi mở: {'; '.join(page.questions)}"
        if page.status != "ok":
            meta += f"\ntrạng thái: {page.status}"
        return f"{head}{meta}\n\n{page.body.strip()}"

    async def find(args: dict[str, Any]) -> str:
        hits = search_wiki(memory_dir, str(args.get("query", "")))
        if not hits:
            return texts.WIKI_EMPTY
        return "\n".join(f"[{slug}] {line}" for slug, line in hits)

    async def apply(args: dict[str, Any]) -> str:
        title = str(args.get("page", "")).strip()
        body = str(args.get("body", "")).strip()
        sources = _as_list(args.get("sources"))
        if not title:
            raise ToolError(texts.WIKI_NO_BODY)
        if not body:
            raise ToolError(texts.WIKI_NO_BODY)
        if not sources:
            raise ToolError(texts.WIKI_NO_SOURCES)
        kind = str(args.get("kind", "entities")).strip() or "entities"
        try:
            wiki_store.check_kind(kind)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

        slug = wiki_store.slugify(title)
        existing = wiki_store.find_page(memory_dir, slug)
        # The page keeps the folder it already lives in: moving it on a re-write would
        # break every link that resolved to the old one.
        target_kind = existing.kind if existing is not None else kind
        managed = wiki_links.split_managed(existing.body)[1] if existing is not None else ""
        page = wiki_store.Page(
            slug=slug,
            kind=target_kind,
            title=title,
            body=wiki_links.set_managed(body, managed),
            sources=sources,
            questions=_as_list(args.get("questions")),
            status=str(args.get("status", "ok")) or "ok",
        )
        try:
            written = wiki_store.write_page(memory_dir, page)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        return texts.WIKI_SAVED.format(
            slug=written.slug, kind=written.kind, sources=len(written.sources)
        )

    return [
        Tool(
            name="wiki_get",
            description=texts.WIKI_GET_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {"page": {"type": "string"}},
                "required": ["page"],
            },
            run=get,
        ),
        Tool(
            name="wiki_search",
            description=texts.WIKI_SEARCH_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            run=find,
        ),
        Tool(
            name="wiki_apply",
            description=texts.WIKI_APPLY_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {
                    "page": {"type": "string", "description": "Tên trang, ví dụ 'Hạn Eco'."},
                    "kind": {"type": "string", "enum": list(wiki_store.KINDS)},
                    "body": {
                        "type": "string",
                        "description": "Nội dung, dùng [[tên]] để liên kết.",
                    },
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "'note:YYYY-MM-DD' hoặc 'conv:<id>'. Bắt buộc.",
                    },
                    "questions": {"type": "array", "items": {"type": "string"}},
                    "status": {"type": "string", "enum": list(wiki_store.STATUSES)},
                },
                "required": ["page", "body", "sources"],
            },
            run=apply,
        ),
    ]
