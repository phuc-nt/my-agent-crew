"""FastAPI application. `build_runtime` wires settings → agents → tools → store once;
`create_app` mounts the API and, when a bundle exists, the web UI."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from my_agent_crew import __version__
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.config import load_settings
from my_agent_crew.server import (
    routes_activity,
    routes_agents,
    routes_agents_edit,
    routes_agents_files,
    routes_approvals,
    routes_chat,
    routes_conversations,
    routes_credentials,
    routes_inbound,
    routes_jobs,
    routes_memory_agent,
    routes_memory_user,
    routes_memory_wiki,
    routes_model_routes,
    routes_registry,
    routes_settings,
)
from my_agent_crew.server.agent_assembly import build_providers
from my_agent_crew.server.local_guard import allowed_hosts, install_local_guard
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_deps, build_runtime

__all__ = ["build_deps", "build_providers", "build_runtime", "create_app"]

STATIC_DIR = Path(__file__).parent / "static"
# Responses above this size go out gzipped when the client accepts it: the bundle, the
# conversation list and the run feed shrink to a fraction. Event streams are exempt.
GZIP_MIN_BYTES = 1024
# The bundle's files carry a content hash in their name, so a browser may keep them for
# as long as it likes; a new build is a new name. `index.html` is not under /assets and
# is revalidated on every load, which is what makes the new name reach the browser.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
ROUTERS = (
    routes_conversations.router,
    routes_chat.router,
    routes_inbound.router,
    routes_approvals.router,
    routes_settings.router,
    routes_agents.router,
    routes_agents_edit.router,
    routes_agents_files.router,
    routes_registry.router,
    routes_credentials.router,
    routes_model_routes.router,
    routes_activity.router,
    routes_jobs.router,
    routes_memory_user.router,
    routes_memory_agent.router,
    routes_memory_wiki.router,
)


class HashedAssets(StaticFiles):
    """The bundle's hashed files, served as cacheable forever."""

    def file_response(self, *args: object, **kwargs: object) -> FileResponse:
        response = super().file_response(*args, **kwargs)  # type: ignore[arg-type]
        response.headers["cache-control"] = IMMUTABLE_CACHE
        return response


def create_app(runtime: Runtime | AgentDeps | None = None, schedule: bool = True) -> FastAPI:
    if runtime is None:
        runtime = build_runtime(load_settings())
    elif isinstance(runtime, AgentDeps):
        runtime = Runtime.single(runtime)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if schedule:
            runtime.scheduler.start()
            runtime.start_channel()
        try:
            yield
        finally:
            await runtime.stop_channel()
            await runtime.scheduler.stop()
            runtime.hub.close()

    app = FastAPI(title="my-agent-crew", version=__version__, lifespan=lifespan)
    app.state.runtime = runtime
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MIN_BYTES)
    install_local_guard(app, allowed_hosts(os.environ))

    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    if (STATIC_DIR / "index.html").exists():
        app.mount("/assets", HashedAssets(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(status_code=404)
            # A `..` decoded from `%2F` would otherwise walk out of the bundle to any file.
            candidate = (STATIC_DIR / path).resolve()
            if path and candidate.is_relative_to(STATIC_DIR.resolve()) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app
