"""What the crew is wired to: every tool and who holds it, every outside connection and
whether it is configured.

Nothing here returns a secret's value. A key is reported as present or absent, and a
Telegram chat is reported as set or not — enough to tell a missing key from a wrong one
without putting either into a browser tab, a screenshot or a bug report.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from ruamel.yaml import YAMLError

from my_agent_crew.agents.profile_write import read_raw
from my_agent_crew.llm.ollama import base_url as ollama_base_url
from my_agent_crew.server.deps import Rt
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.tool_assembly import OPTIONAL_TOOLS
from my_agent_crew.tools.web import search_backends

router = APIRouter(tags=["registry"])
ROUTES_ENV = "MY_AGENT_ROUTES"


def _holders(rt: Runtime, name: str) -> list[str]:
    return sorted(
        agent_id for agent_id, deps in rt.agents.items() if deps.tools.get(name) is not None
    )


@router.get("/tools")
def list_tools(rt: Rt) -> list[dict[str, Any]]:
    """Every tool any agent holds, with the agents holding it.

    The union rather than the master's own set: an agent's profile can cap its tools, so
    reading one agent's registry would hide tools the rest of the crew still uses.
    """
    seen: dict[str, dict[str, Any]] = {}
    for deps in rt.agents.values():
        for tool in deps.tools.describe():
            seen.setdefault(tool["name"], tool)
    return [
        {**tool, "agents": _holders(rt, name), "optional": name in OPTIONAL_TOOLS}
        for name, tool in sorted(seen.items())
    ]


def _telegram(rt: Runtime) -> list[dict[str, Any]]:
    """One row per agent with a Telegram channel. The token lives in an environment
    variable, so what is reported is its name and whether it is filled in — never what
    it holds, and never the chat it talks to.

    `configured` is that agent's own env var, not whether the crew has a channel at all:
    only the master's block builds one, and reporting the crew's state on every row would
    show a working channel for an agent whose token was never set.
    """
    out = []
    for profile in rt.profiles():
        telegram = profile.telegram
        if telegram is None:
            continue
        out.append(
            {
                "agent_id": profile.id,
                "token_env": telegram.token_env,
                "configured": bool(os.environ.get(telegram.token_env)),
                # The person talks to one bot; a block on anyone else is ignored at boot,
                # so the page can say that rather than showing a channel that never runs.
                "ignored": not profile.is_master,
            }
        )
    return out


def config_path(home: Path) -> Path:
    return home / "config.yaml"


def routes_source(home: Path) -> Literal["env", "config", "default"]:
    """Where the routes in force were read from — the variable, `config.yaml` or the
    default — so the page knows whether saving them from the web changes anything."""
    if os.environ.get(ROUTES_ENV):
        return "env"
    try:
        return "config" if read_raw(config_path(home)).get("routes") else "default"
    except (OSError, ValueError, YAMLError):
        return "default"


@router.get("/connections")
def list_connections(rt: Rt) -> dict[str, Any]:
    s = rt.settings
    return {
        "providers": [{"name": name, "built": True} for name in sorted(rt.default.chain.providers)],
        "routes": [{"provider": r.provider, "model": r.model} for r in s.routes],
        "routes_source": routes_source(s.home),
        "vision_routes": [{"provider": r.provider, "model": r.model} for r in s.vision_routes],
        "keys": [
            {"name": "OPENROUTER_API_KEY", "present": bool(s.openrouter_api_key)},
            {"name": "BRAVE_API_KEY", "present": bool(s.brave_api_key)},
            {"name": "TAVILY_API_KEY", "present": bool(s.tavily_api_key)},
            {"name": "FIRECRAWL_API_KEY", "present": bool(s.firecrawl_api_key)},
        ],
        # Which backend answers a search, best first. Never empty: DuckDuckGo needs no
        # key, so the page can say "search works" on a machine with no keys at all.
        "search_backends": search_backends(s),
        "firecrawl_base_url": s.firecrawl_base_url,
        # Ollama is always built because it needs no key, so the useful thing to show is
        # where it is being looked for — that separates "not running" from "wrong host".
        "ollama_base_url": ollama_base_url(),
        "telegram": _telegram(rt),
    }
