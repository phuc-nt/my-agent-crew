"""A canvas of kind `html` or `mermaid` as the page it is: the one place what an agent wrote runs
as a document. It runs in an opaque origin that cannot reach the app and has no way to send
anything out (`artifacts/render.py`), which is why its policy is not the one
`untrusted_content.py` gives everything else, and why it is framed by the app's own pages and by
no one else's. The route reads and writes nothing. A canvas of another kind, one that is not
there and a version a later save folded away are all 404."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from my_agent_crew.artifacts.mermaid_page import mermaid_page
from my_agent_crew.artifacts.render import html_page, render_csp
from my_agent_crew.server.artifact_errors import artifact_errors
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["artifacts"])

NOT_A_PAGE = "this kind of canvas has no page to run"
PAGE_KINDS = ("html", "mermaid")
# `no-store`: the page is made from the canvas as it is now, so a copy kept by the browser could
# run a version that has been replaced.
HEADERS = {
    "Content-Security-Policy": render_csp(),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-DNS-Prefetch-Control": "off",
    "Cache-Control": "no-store",
}


@router.get("/artifacts/{artifact_id}/render")
async def render_page(
    artifact_id: str, rt: Rt, version: int | None = Query(None, ge=1)
) -> Response:
    """The newest version as a page, or `version`'s."""
    artifacts = rt.store.artifacts
    with artifact_errors(artifacts, artifact_id):
        summary = artifacts.get(artifact_id)
        if summary.kind not in PAGE_KINDS:
            raise HTTPException(404, NOT_A_PAGE)
        if version is None:
            found = artifacts.head(artifact_id)
        else:
            found = artifacts.version(artifact_id, version)
    content = found.content or ""
    body = html_page(content) if summary.kind == "html" else mermaid_page(summary.title, content)
    return Response(body, media_type="text/html; charset=utf-8", headers=HEADERS)
