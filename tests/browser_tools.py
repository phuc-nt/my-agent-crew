"""What the tests of the browser tools share: one browser for a whole test module, the local
servers it may reach, a kit on it, and a way to run a test as a conversation of its own."""

from __future__ import annotations

import dataclasses
import functools
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from my_agent_crew import texts_browser_fence as f
from my_agent_crew.agent.turn_context import reading_as
from my_agent_crew.browser.kit import Kit
from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.config_browser import BrowserSettings
from tests.browser_servers import Page, Site, local_names

FENCE = re.compile(r"^<<<TRANG ([0-9a-f]{16})\n(.*)\nTRANG \1>>>\Z", re.S | re.M)
# A fence wherever it stands in what a registry answered, with a note after it or none.
WHOLE = re.compile(r"^<<<TRANG ([0-9a-f]{16})\n(.*?)\nTRANG \1>>>$", re.S | re.M)


@dataclasses.dataclass
class World:
    pool: BrowserPool
    site: Site  # what the browser may reach
    intranet: Site  # a private service: the real rule refuses it
    ports: set[int]  # every local port the browser may reach
    workspace: Path

    def kit(self, agent: str = "coach", *, limit: int = 20_000, **own: Any) -> Kit:
        """The tools' view for one agent, which may act unless told otherwise."""
        vision = own.pop("vision", None)
        settings = dataclasses.replace(self.pool.settings, **{"mode": "act", **own})
        return Kit(self.pool, agent, settings, self.workspace, limit, vision)

    def tab(self, owner: str, label: str = "", agent: str = "coach"):
        return self.pool.peek(agent, owner, label)


@asynccontextmanager
async def world(
    root: Path, pages: dict[str, Page], resolver: Any = local_names, **settings: Any
) -> AsyncIterator[World]:
    site, intranet = Site(pages), Site({"/": "<title>Nội bộ</title>bí mật", "/x.png": "bí mật"})
    ports = {site.port}
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    pool = BrowserPool(
        root / "browser",
        BrowserSettings(enabled=True, **settings),
        resolver=resolver,
        allow=lambda _address, port: port in ports,
    )
    try:
        yield World(pool, site, intranet, ports, workspace)
    finally:
        await pool.stop_all()
        site.close()
        intranet.close()


def talking(conversation: str):
    """Run a test as one conversation, so its tabs are its own in the browser its module
    shares."""

    def wrap(test):
        @functools.wraps(test)
        async def run(*args, **kwargs):
            with reading_as(conversation):
                return await test(*args, **kwargs)

        return run

    return wrap


def parts(answer: str) -> tuple[str, str]:
    """What an answer says outside its fence and what it holds inside."""
    match = FENCE.search(answer)
    assert match, answer
    return answer[: match.start()], match.group(2)


def under(answer: str) -> tuple[str, str]:
    """A tool's own words, and what it fenced under them. Between the two stands the line
    that says what the fence is, and nothing else."""
    match = FENCE.search(answer)
    assert match, answer
    opening = f.PAGE_OPEN.format(nonce=match.group(1))
    closing = f.PAGE_CLOSE.format(nonce=match.group(1))
    said = f.PAGE_FENCE.format(opening=opening, closing=closing) + "\n"
    outside = answer[: match.start()]
    assert outside.endswith(said), answer
    return outside.removesuffix(said).removesuffix("\n"), match.group(2)


def kept(output: str) -> tuple[str, str | None]:
    """What an answer says outside a fence once a registry had it, and what it still holds
    inside one: None for an answer with no fence. A fence that opens and is not closed, or
    the line that tells of one with none under it, is no answer at all."""
    if "<<<TRANG" not in output:
        return output, None
    match = WHOLE.search(output)
    assert match, output
    return output[: match.start()] + output[match.end() :], match.group(2)


def ref_of(answer: str, name: str) -> str:
    """The ref the outline in an answer gives the element of that name."""
    match = re.search(rf'"{re.escape(name)}"[^\n]*\[ref=(\w+)\]', answer)
    assert match, (name, answer)
    return match.group(1)
