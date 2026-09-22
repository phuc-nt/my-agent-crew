"""One agent's wiki vault over HTTP.

The vault is a folder of markdown files, so every one of these endpoints is a thin pass
over `wiki_store`. What the web UI adds is the shape a person needs: the whole vault as a
list without its bodies, one page in full, and the lint report as data rather than as the
markdown dashboard written beside the pages.

Editing a page from here rebuilds the link graph, because an edited `[[link]]` changes
what *other* pages say they are linked from. Leaving that to the next compile would let
the vault describe a graph that was true yesterday.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from my_agent_crew import texts
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.memory import wiki_lint, wiki_store
from my_agent_crew.memory.wiki_apply import rebuild_links
from my_agent_crew.memory.wiki_compile import JOB_SOURCE, compile_wiki
from my_agent_crew.memory.wiki_reports import write_reports
from my_agent_crew.server.deps import Rt
from my_agent_crew.tools.wiki import search_wiki

router = APIRouter(tags=["memory"])


class PageBody(BaseModel):
    title: str | None = None
    body: str | None = None
    sources: list[str] | None = None
    questions: list[str] | None = None
    status: str | None = None


def _profile(rt: Rt, agent_id: str) -> AgentProfile:
    try:
        return rt.deps_for(agent_id).profile
    except KeyError as exc:
        raise HTTPException(404, "agent not found") from exc


def _page(profile: AgentProfile, slug: str) -> wiki_store.Page:
    page = wiki_store.find_page(profile.memory_dir, slug)
    if page is None:
        raise HTTPException(404, "page not found")
    return page


def _summary(page: wiki_store.Page) -> dict[str, Any]:
    """A page without its body. The list view is a table of contents, and sending every
    body would make opening the tab cost the whole vault."""
    return {
        "slug": page.slug,
        "kind": page.kind,
        "title": page.title,
        "status": page.status,
        "updated": page.updated,
        "sources": list(page.sources),
        "question_count": len(page.questions),
    }


@router.get("/agents/{agent_id}/memory/wiki")
def list_wiki(agent_id: str, rt: Rt, q: str = "") -> dict[str, Any]:
    profile = _profile(rt, agent_id)
    pages = wiki_store.list_pages(profile.memory_dir)
    if q.strip():
        # Ranked by the same search the agent's own `wiki_search` tool uses, so what a
        # person finds here is what the agent would have found.
        order = [slug for slug, _ in search_wiki(profile.memory_dir, q, limit=len(pages) or 1)]
        by_slug = {page.slug: page for page in pages}
        pages = [by_slug[slug] for slug in order if slug in by_slug]
    return {
        "pages": [_summary(page) for page in pages],
        "kinds": list(wiki_store.KINDS),
        "count": len(pages),
    }


@router.get("/agents/{agent_id}/memory/wiki/pages/{slug}")
def get_wiki_page(agent_id: str, slug: str, rt: Rt) -> dict[str, Any]:
    return _page(_profile(rt, agent_id), slug).to_dict()


@router.put("/agents/{agent_id}/memory/wiki/pages/{slug}")
def put_wiki_page(agent_id: str, slug: str, body: PageBody, rt: Rt) -> dict[str, Any]:
    """Edit a page in place. Only the fields sent are changed, so a UI that shows the
    body alone cannot silently drop the sources it never displayed."""
    profile = _profile(rt, agent_id)
    page = _page(profile, slug)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    wiki_store.write_page(profile.memory_dir, wiki_store.Page(**{**page.to_dict(), **fields}))  # type: ignore[arg-type]
    rebuild_links(profile.memory_dir)
    write_reports(profile.memory_dir)
    return _page(profile, slug).to_dict()


@router.delete("/agents/{agent_id}/memory/wiki/pages/{slug}")
def delete_wiki_page(agent_id: str, slug: str, rt: Rt) -> dict[str, Any]:
    profile = _profile(rt, agent_id)
    page = _page(profile, slug)
    (wiki_store.wiki_dir(profile.memory_dir) / page.kind / f"{page.slug}.md").unlink()
    # The pages that linked here now have a dangling link. Rebuilding drops the edge from
    # their related block, and the lint report picks the link itself up as a to-do.
    rebuild_links(profile.memory_dir)
    write_reports(profile.memory_dir)
    return {"slug": slug, "deleted": True}


@router.get("/agents/{agent_id}/memory/wiki/report")
def wiki_report(agent_id: str, rt: Rt) -> dict[str, Any]:
    profile = _profile(rt, agent_id)
    pages = wiki_store.list_pages(profile.memory_dir)
    return {
        "problems": [vars(p) for p in wiki_lint.lint(profile.memory_dir)],
        "questions": [{"slug": slug, "question": q} for slug, q in wiki_lint.open_questions(pages)],
    }


@router.post("/agents/{agent_id}/memory/wiki/compile", status_code=202)
async def compile_now(agent_id: str, rt: Rt) -> dict[str, Any]:
    """Starts a compile and returns at once; the run shows its progress in Activity.

    It shares the consolidation's busy set: both read the same notes and write to the same
    memory folder, and two of them at once would race over the same files.
    """
    _profile(rt, agent_id)
    if agent_id in rt.consolidating:
        raise HTTPException(409, texts.CONSOLIDATE_BUSY)
    deps = rt.deps_for(agent_id)
    rt.consolidating.add(agent_id)

    async def run() -> None:
        try:
            await compile_wiki(deps, rt.hub)
        finally:
            rt.consolidating.discard(agent_id)

    rt.scheduler.keep(asyncio.create_task(run()))
    return {"agent_id": agent_id, "run_source": JOB_SOURCE}
