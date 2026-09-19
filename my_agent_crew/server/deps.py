"""Request-scoped access to the wired dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from my_agent_crew.agent.loop import AgentDeps


def get_deps(request: Request) -> AgentDeps:
    return request.app.state.deps


Deps = Annotated[AgentDeps, Depends(get_deps)]
