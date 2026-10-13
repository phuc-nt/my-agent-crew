"""What the browser tools of one agent share: its browser, its settings, and the one way a
call reaches a tab.

No module of the tools imports Playwright. An error of the browser is known by where its
class lives, so a machine without the package still imports all of this and simply builds no
browser tool (`tools.py`)."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew.agent.turn_context import turn_conversation_id
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.browser.pool import BrowserPool, Session
from my_agent_crew.browser.snapshot import Node, Shown, Snapshot, address, read
from my_agent_crew.browser.tabs import JOB_OWNER, Tab
from my_agent_crew.config_browser import BrowserSettings
from my_agent_crew.tools.registry import ToolError

NAVIGATE, SNAPSHOT, TEXT = "browser_navigate", "browser_snapshot", "browser_text"
TABS, SCREENSHOT, ACT = "browser_tabs", "browser_screenshot", "browser_act"
# What `browser: read` brings; `browser: act` adds the last.
READ_TOOLS = (NAVIGATE, SNAPSHOT, TEXT, TABS, SCREENSHOT)
BROWSER_TOOLS = (*READ_TOOLS, ACT)
CALL_SECONDS = 20.0
ERROR_CHARS = 200
# How often an outline is drawn again when the page moved while it was being drawn, and how
# long a page is given to settle after something was done to it.
LOOKS = 3
SETTLE_SECONDS, SETTLE_MS = 0.15, 5_000


def from_browser(exc: BaseException) -> bool:
    return type(exc).__module__.startswith("playwright")


def timed_out(exc: BaseException) -> bool:
    return from_browser(exc) and type(exc).__name__ == "TimeoutError"


def first_line(exc: BaseException) -> str:
    """The first line of an error: what follows it is a log that quotes the page."""
    lines = str(exc).strip().splitlines()
    return (lines[0] if lines else type(exc).__name__)[:ERROR_CHARS]


def one_line(text: str, limit: int) -> str:
    return " ".join(text.split())[:limit]


def text_of(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    return value.strip() if isinstance(value, str) else ""


def flag(args: dict[str, Any], key: str) -> bool:
    return args.get(key) in (True, "true", "True")


def number(args: dict[str, Any], key: str, least: int, default: int, most: int) -> int:
    """A count the model gave, kept inside what the tool allows; anything unread is the
    default."""
    try:
        return max(least, min(most, int(args.get(key))))
    except (TypeError, ValueError):
        return default


def schema(required: tuple[str, ...], **properties: tuple[str, str]) -> dict[str, Any]:
    described = {k: {"type": kind, "description": text} for k, (kind, text) in properties.items()}
    return {"type": "object", "properties": described, "required": list(required)}


@dataclass
class Kit:
    pool: BrowserPool
    agent_id: str
    # The agent's own: how far it may go, its hosts and the words that stop for a person.
    settings: BrowserSettings
    workspace: Path
    # What the registry cuts a tool's answer at: a page is sized to fit under it whole.
    limit: int
    # The chain pictures go to, when the machine has one.
    vision: Any = None
    ask: AskWords = field(init=False)

    def __post_init__(self) -> None:
        self.ask = AskWords(self.settings.ask_patterns)

    def owner(self) -> str:
        """Whose tabs this call sees: its conversation's, or the one a script job has."""
        return turn_conversation_id() or JOB_OWNER

    @contextlib.asynccontextmanager
    async def tab(
        self,
        label: str = "",
        *,
        seconds: float = CALL_SECONDS,
        make: bool = False,
        last: bool = False,
    ) -> AsyncIterator[tuple[Session, Tab]]:
        """The caller's tab for the length of one call, alone on it, with the browser kept
        up meanwhile. `make` opens the tab when the caller has none of that label; `last`
        takes no label to mean the tab of the caller's last call and no other. Whatever the
        browser raises leaves as words the model can act on; a call that outlasts `seconds`
        is given up."""
        owner = self.owner()
        try:
            async with asyncio.timeout(seconds):
                try:
                    await self.pool.session(self.agent_id)
                except Exception as exc:  # noqa: BLE001 - whatever kept the browser from starting
                    raise ToolError(t.BROWSER_DOWN.format(error=first_line(exc))) from exc
                async with self.pool.hold(self.agent_id) as session:
                    tabs = session.tabs
                    if make:
                        tab = tabs.find(owner, label) or await tabs.open(owner, label)
                    else:
                        tab = tabs.get(owner, label, last=last)
                    async with tab.lock:
                        tabs.touch(tab)
                        yield session, tab
        except ToolError:
            raise
        except TimeoutError as exc:
            raise ToolError(t.PAGE_STUCK.format(seconds=round(seconds))) from exc
        except Exception as exc:
            if not from_browser(exc):
                raise
            raise ToolError(t.BROWSER_FAILED.format(error=first_line(exc))) from exc


async def settle(page: Any) -> None:
    """Give a page that was just acted on a moment to start going where it goes, and wait
    until the page it lands on can be read."""
    await asyncio.sleep(SETTLE_SECONDS)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=SETTLE_MS)
    except Exception as exc:
        if not from_browser(exc):
            raise


async def look(kit: Kit, tab: Tab) -> tuple[str, Snapshot]:
    """The page as it is now, and the address it was read at. A page that moved while its
    outline was drawn leaves the outline of either page or none, so it is drawn again; the
    address kept is the one from before, and an action checks the page is still there."""
    for last in (n == LOOKS - 1 for n in range(LOOKS)):
        url = address(tab.page.url)
        try:
            outline = await tab.page.aria_snapshot(mode="ai")
        except Exception as exc:
            if last or not from_browser(exc) or timed_out(exc):
                raise
            await settle(tab.page)
            continue
        if address(tab.page.url) == url:
            break
    return url, read(outline, kit.ask)


def show(tab: Tab, url: str, snapshot: Snapshot) -> None:
    """Keep what the model is about to be given: an action is checked against it."""
    tab.shown = Shown(url, snapshot.nodes)


def known(tab: Tab, ref: str) -> Node:
    """The element as the model was last shown it. A ref it was never given finds nothing,
    which is also what keeps a made-up one out of a selector."""
    if tab.shown is None:
        raise ToolError(t.NO_SNAPSHOT)
    node = tab.shown.nodes.get(ref)
    if node is None:
        raise ToolError(t.REF_UNKNOWN.format(ref=one_line(ref, 40)))
    return node
