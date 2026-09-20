"""Read-only view of what the agents can do right now. Secrets are reported as present
or absent, never echoed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from my_agent_crew.agents.templates_cli import list_templates
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["settings"])


@router.get("/templates")
def get_templates() -> list[dict[str, Any]]:
    """The bundled agent templates. Read-only: installing one writes to the home directory
    and needs a restart, so it stays a command rather than a button."""
    return [t.to_dict() for t in list_templates()]


@router.get("/settings")
def get_settings(rt: Rt) -> dict[str, Any]:
    s = rt.settings
    deps = rt.default
    return {
        "home": str(s.home),
        "workspace_dir": str(s.workspace_dir),
        "users_dir": str(s.users_dir),
        "routes": [{"provider": r.provider, "model": r.model} for r in s.routes],
        "providers": sorted(deps.chain.providers),
        "language": s.language,
        "cost_cap_usd": s.cost_cap_usd,
        "max_steps": s.max_steps,
        "autonomous_default": s.autonomous_default,
        "keys": {
            "openrouter": bool(s.openrouter_api_key),
            "brave": bool(s.brave_api_key),
            "tavily": bool(s.tavily_api_key),
        },
        "tools": deps.tools.describe(),
        "skills": [sk.to_dict() for sk in deps.skills],
        "agents": [p.to_dict() for p in rt.profiles()],
    }
