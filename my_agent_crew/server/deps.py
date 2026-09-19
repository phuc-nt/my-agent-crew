"""Request-scoped access to the runtime. Routes that act on one conversation resolve
that conversation's agent, so a health-coach thread never runs with Pong's tools."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.server.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_default_deps(request: Request) -> AgentDeps:
    return get_runtime(request).default


def get_conversation_deps(conv_id: str, request: Request) -> AgentDeps:
    try:
        return get_runtime(request).deps_for_conversation(conv_id)
    except KeyError as exc:
        raise HTTPException(404, "conversation not found") from exc


Rt = Annotated[Runtime, Depends(get_runtime)]
Deps = Annotated[AgentDeps, Depends(get_default_deps)]
ConvDeps = Annotated[AgentDeps, Depends(get_conversation_deps)]
