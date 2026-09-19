"""FastAPI application. `build_deps` wires settings → providers → tools → store once;
`create_app` mounts the API and, when a bundle exists, the web UI."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from my_agent_crew import __version__
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.config import Settings, ensure_home, load_settings
from my_agent_crew.llm.fake import EchoProvider
from my_agent_crew.llm.openrouter import OpenRouterProvider
from my_agent_crew.llm.provider import Provider, ProviderChain
from my_agent_crew.server import (
    routes_approvals,
    routes_chat,
    routes_conversations,
    routes_settings,
)
from my_agent_crew.skills import BUILTIN_DIR, load_skills
from my_agent_crew.store import Store
from my_agent_crew.tools import ToolRegistry
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.web import build_web_tools
from my_agent_crew.tools.workspace import build_workspace_tools

STATIC_DIR = Path(__file__).parent / "static"


def build_providers(settings: Settings, client: httpx.AsyncClient) -> dict[str, Provider]:
    providers: dict[str, Provider] = {"fake": EchoProvider()}
    if settings.openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(settings.openrouter_api_key, client)
    return providers


def build_deps(settings: Settings, client: httpx.AsyncClient | None = None) -> AgentDeps:
    ensure_home(settings)
    client = client or httpx.AsyncClient()
    store = Store(settings.db_path)
    tools = ToolRegistry(
        [
            *build_workspace_tools(settings.workspace_dir),
            *build_web_tools(settings, client),
            *build_memory_tools(store),
        ]
    )
    chain = ProviderChain(build_providers(settings, client), settings.routes)
    skills = load_skills(BUILTIN_DIR, settings.skills_dir)
    return AgentDeps(settings=settings, chain=chain, tools=tools, store=store, skills=skills)


def create_app(deps: AgentDeps | None = None) -> FastAPI:
    deps = deps or build_deps(load_settings())
    app = FastAPI(title="my-agent-crew", version=__version__)
    app.state.deps = deps

    for router in (
        routes_conversations.router,
        routes_chat.router,
        routes_approvals.router,
        routes_settings.router,
    ):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    if (STATIC_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = STATIC_DIR / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app
