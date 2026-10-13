"""A crew home on disk for the tests of the browser as the server holds it, and the server
built from it."""

from __future__ import annotations

from pathlib import Path

from my_agent_crew.browser.console import OPEN
from my_agent_crew.browser.install import Installed
from my_agent_crew.config import load_settings
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_runtime

# A machine that has the pinned Chromium.
HERE = Installed(True, "153.0.8010.12")
ON = "browser_enabled: true\n"


class Screen:
    """The machine's screen as a test says it is, in place of asking the machine: a test that
    asked would pass at one desk and fail where nobody is signed in."""

    def __init__(self, state: str = OPEN) -> None:
        self.state = state

    def __call__(self) -> str:
        return self.state


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
