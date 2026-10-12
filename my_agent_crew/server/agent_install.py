"""Bringing agents into the running crew from what the home holds: a template installed
over HTTP, a folder copied in by hand.

Both read the home as the crew a start would read. A home that cannot be read that way is
a 422 that says which file, and so is an agent whose folders cannot be made.

An install writes into the home, and what it leaves there the next start reads. So
everything the request names is checked, and the home read, before a file is written. When
what it wrote cannot join the crew, the folders it made are taken away and every file it
wrote over is put back as it stood: a refused install leaves the home as it was. Without
that, one refusal left a folder behind which stopped every start after it.
"""

from __future__ import annotations

import shutil
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from my_agent_crew import texts
from my_agent_crew.agents import load_profiles
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.agents.profile_edit import check_agent_id
from my_agent_crew.agents.templates_cli import (
    MANIFEST,
    Template,
    add_template,
    landing,
    list_templates,
)
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import check_delegates


class InstallRequest(BaseModel):
    template: str
    agent_id: str = ""
    workspace: str = ""
    force: bool = False


def read_crew(rt: Runtime) -> list[AgentProfile]:
    """The crew as the home states it now. Any file under the home can be the broken one,
    including a folder copied in by hand, so this says which rather than failing as a
    traceback."""
    try:
        profiles = load_profiles(rt.settings)
        check_delegates(profiles)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return profiles


def joined(rt: Runtime, profiles: list[AgentProfile]) -> list[str]:
    """The ids that joined the running crew. Building an agent makes its folders, and a
    workspace that is a file, or lies where nothing can be made, is the profile's fault."""
    try:
        return rt.add_agents(profiles)
    except OSError as exc:
        raise HTTPException(422, str(exc)) from exc


def _named(body: InstallRequest, rt: Runtime) -> tuple[Template, str]:
    """The template and the id the request means, each a plain name nobody else goes by."""
    template = {t.id: t for t in list_templates()}.get(body.template)
    if template is None:
        raise HTTPException(404, texts.TEMPLATE_UNKNOWN.format(template=body.template))
    agent_id = body.agent_id or template.id
    try:
        check_agent_id(agent_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    folder = rt.settings.home / "agents" / agent_id
    # `force` writes over an agent's own file. An id that runs without one is the master's,
    # or an agent a kit brings: a file written there took the id from it at the next
    # start, or stopped that start.
    theirs = agent_id in rt.agents and not (folder / MANIFEST).is_file()
    if theirs or (folder.exists() and not body.force):
        raise HTTPException(409, texts.AGENT_EXISTS.format(agent_id=agent_id))
    return template, agent_id


def _workspace(text: str) -> Path | None:
    """The folder the request pins, made the way building the agent makes it. Asked now
    because an agent that already runs is not built again: over one, a workspace that
    cannot be a folder was written into its file and only stopped the next start."""
    if not text:
        return None
    workspace = Path(text).expanduser().resolve()
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(422, str(exc)) from exc
    return workspace


def _put_back(stood: dict[Path, bytes | None], made: list[Path], root: Path | None) -> None:
    """The home as it was before the install wrote: each file it wrote over holds what
    it held, each file and folder it made is gone. `root` is the `agents` folder when the
    install made that too; it goes only once it is empty again."""
    for target, held in stood.items():
        if held is None:
            if target.is_file():
                target.unlink()
        elif target.read_bytes() != held:
            target.write_bytes(held)
    for folder in made:
        shutil.rmtree(folder, ignore_errors=True)
    if root is not None:
        with suppress(OSError):
            root.rmdir()


def install(body: InstallRequest, rt: Runtime) -> dict[str, Any]:
    home = rt.settings.home
    template, agent_id = _named(body, rt)
    read_crew(rt)
    workspace = _workspace(body.workspace)
    root = home / "agents"
    fresh = None if root.exists() else root
    made = [f for f in (root / name for name in (agent_id, *template.delegates)) if not f.exists()]
    stood = {
        target: target.read_bytes() if target.is_file() else None
        for target in landing(template.id, home, agent_id)
    }
    try:
        agent_dir, peers = add_template(
            template.id, home, agent_id, body.force, workspace=workspace
        )
        profiles = read_crew(rt)
        try:
            added = joined(rt, profiles)
        except RuntimeError:
            added = []
    except (HTTPException, ValueError, OSError) as exc:
        _put_back(stood, made, fresh)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(422, str(exc)) from exc
    installed = [agent_dir.name, *peers]
    if added and rt.channel is not None:
        rt.channel.use_agents(rt.agents)
    live = [name for name in installed if name in added]
    needs_restart = any(p.id in installed and p.schedules for p in profiles) or set(
        installed
    ) - set(live)
    return {"installed": installed, "live": live, "needs_restart": bool(needs_restart)}
