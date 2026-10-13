"""The browser tools one agent is given.

None where the machine has no browser to start, and none where the agent's own file leaves
the browser off. An agent that reads pages gets the six tools that open, look and keep a
copy; one that acts gets the two that do something to a page beside them. The `browser` key
decides this and nothing else does: its `tools:` list neither brings one nor takes one away."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from my_agent_crew.browser.kit import Kit
from my_agent_crew.browser.navigate import build_navigate
from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.browser.screenshot import build_screenshot
from my_agent_crew.browser.tools_act import build_act
from my_agent_crew.browser.tools_files import build_download, build_pdf
from my_agent_crew.browser.tools_read import build_snapshot, build_tabs, build_text
from my_agent_crew.config_browser import BrowserSettings
from my_agent_crew.script.limits import RAW_LIMIT
from my_agent_crew.tools.registry import Tool


def build_browser_tools(
    pool: BrowserPool | None,
    agent_id: str,
    settings: BrowserSettings,
    workspace: Path,
    limit: int,
    *,
    vision: Any = None,
    write_paths: Sequence[str] = (),
) -> list[Tool]:
    """`settings` are the agent's own; `limit` is what its registry cuts an answer at;
    `vision` the chain its pictures are read by, when the machine has one; `write_paths` the
    folders its files are held to."""
    if pool is None or not settings.reads:
        return []
    # A script reads an answer through a registry of its own and keeps this much of it: an
    # answer sized to an agent's cap above that would be cut there, fence and all.
    kit = Kit(pool, agent_id, settings, workspace, min(limit, RAW_LIMIT), vision)
    tools = [
        build_navigate(kit),
        build_snapshot(kit),
        build_text(kit),
        build_tabs(kit),
        build_screenshot(kit, write_paths),
        build_pdf(kit, write_paths),
    ]
    acting = [build_act(kit), build_download(kit, write_paths)]
    return [*tools, *acting] if settings.acts else tools
