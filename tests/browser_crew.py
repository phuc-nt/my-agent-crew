"""A crew home on disk for the tests of the browser as the server holds it, and the server
built from it."""

from __future__ import annotations

from pathlib import Path

from my_agent_crew.browser.install import Installed
from my_agent_crew.config import load_settings
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_runtime

# A machine that has the pinned Chromium.
HERE = Installed(True, "153.0.8010.12")
ON = "browser_enabled: true\n"


def crew_home(root: Path, config: str = ON, master: str = "", **agents: str) -> dict[str, str]:
    """Writes a crew home under `root` with these agents, each by the lines of its own file,
    and gives the environment that reads it."""
    home = root / "home"
    home.mkdir()
    (home / "config.yaml").write_text(config, encoding="utf-8")
    if master:
        (home / "agent.yaml").write_text(master, encoding="utf-8")
    for agent_id, own in agents.items():
        folder = home / "agents" / agent_id
        folder.mkdir(parents=True)
        (folder / "agent.yaml").write_text(f"name: {agent_id}\n{own}", encoding="utf-8")
    return {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}


def built(env: dict[str, str]) -> Runtime:
    """The crew of that home. It reads the environment it is given and not the machine's."""
    return build_runtime(load_settings(env=env), env=dict(env))


def browser_tools(rt: Runtime, agent_id: str) -> list[str]:
    return [name for name in rt.deps_for(agent_id).tools.names() if name.startswith("browser_")]
