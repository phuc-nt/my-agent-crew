"""Read-only view of what the agent can do right now. Secrets are reported as present
or absent, never echoed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from my_agent_crew.server.deps import Deps

router = APIRouter(tags=["settings"])


@router.get("/settings")
def get_settings(deps: Deps) -> dict[str, Any]:
    s = deps.settings
    return {
        "home": str(s.home),
        "workspace_dir": str(s.workspace_dir),
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
    }
