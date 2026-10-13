"""The tabs of one agent's browser: whose each is, when it was last used and what its page
last showed the model.

A tab belongs to the conversation that opened it, and no other conversation sees or acts on
it. A turn with no conversation (a scheduled script) shares one owner of its own."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew.browser.snapshot import Shown
from my_agent_crew.tools.registry import ToolError

LABEL = re.compile(r"[a-z0-9][a-z0-9_-]{0,23}")
JOB_OWNER = "job"
# A tab nobody used for this long is closed, while the browser itself stays up for others.
COLD_SECONDS = 30 * 60
DIALOGS_KEPT = 5
DIALOG_CHARS = 300


@dataclass
class Tab:
    id: int
    label: str
    owner: str
    page: Any
    used: float
    # What the model was last given of this page: an action is checked against it.
    shown: Shown | None = None
    # What the page's dialogs said since the model was last told.
    dialogs: list[str] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Tabs:
    def __init__(self, context: Any, limit: int, clock: Callable[[], float]) -> None:
        self._context = context
        self._limit = limit
        self._clock = clock
        self._tabs: dict[int, Tab] = {}
        self._ids = 0
        self._opening = asyncio.Lock()
        self._answers: set[asyncio.Future[Any]] = set()

    def all(self) -> list[Tab]:
        return list(self._tabs.values())

    def of(self, owner: str) -> list[Tab]:
        """An owner's tabs, the one last used first."""
        mine = [tab for tab in self._tabs.values() if tab.owner == owner]
        return sorted(mine, key=lambda tab: (tab.used, tab.id), reverse=True)

    def find(self, owner: str, label: str = "") -> Tab | None:
        """The owner's tab of that label, or the one it used last when no label is given."""
        mine = self.of(owner)
        if not label:
            return mine[0] if mine else None
        wanted = label.strip().casefold()
        return next((tab for tab in mine if tab.label == wanted), None)

    def get(self, owner: str, label: str = "") -> Tab:
        tab = self.find(owner, label)
        if tab is not None:
            return tab
        mine = ", ".join(tab.label for tab in self.of(owner))
        if not mine:
            raise ToolError(t.NO_TAB)
        raise ToolError(t.UNKNOWN_TAB.format(label=label, labels=mine))

    def touch(self, tab: Tab) -> None:
        tab.used = self._clock()

    async def open(self, owner: str, label: str = "") -> Tab:
        wanted = label.strip().casefold()
        if wanted and not LABEL.fullmatch(wanted):
            raise ToolError(t.BAD_LABEL.format(label=label))
        async with self._opening:  # two turns opening at once must not both take the last place
            if len(self._tabs) >= self._limit:
                idle = [x for x in self._tabs.values() if x.owner != owner and not x.lock.locked()]
                if not idle:
                    raise ToolError(t.TOO_MANY_TABS.format(count=len(self._tabs)))
                await self.close(min(idle, key=lambda tab: (tab.used, tab.id)))
            return self._adopt(await self._context.new_page(), owner, wanted)

    async def close(self, tab: Tab) -> None:
        self._tabs.pop(tab.id, None)
        try:
            await tab.page.close()
        except Exception:  # noqa: BLE001 - a page already gone is closed
            pass

    async def close_cold(self) -> int:
        now = self._clock()
        cold = [
            tab
            for tab in self._tabs.values()
            if now - tab.used >= COLD_SECONDS and not tab.lock.locked()
        ]
        for tab in cold:
            await self.close(tab)
        return len(cold)

    def _adopt(self, page: Any, owner: str, label: str = "") -> Tab:
        taken = {tab.label for tab in self._tabs.values() if tab.owner == owner}
        number = 0
        while not label or label in taken:  # a label the owner already uses is not given twice
            number += 1
            label = f"t{number}"
        self._ids += 1
        tab = Tab(self._ids, label, owner, page, self._clock())
        self._tabs[tab.id] = tab
        page.on("close", lambda _page: self._tabs.pop(tab.id, None))
        page.on("crash", lambda _page: self._later(self.close(tab)))
        page.on("dialog", lambda dialog: self._dialog(tab, dialog))
        page.on("popup", lambda popup: self._popup(tab, popup))
        return tab

    def _popup(self, opener: Tab, popup: Any) -> None:
        """A window a page opens is its owner's next tab, or nothing over the limit."""
        if len(self._tabs) >= self._limit:
            self._later(popup.close())
        else:
            self._adopt(popup, opener.owner)

    def _dialog(self, tab: Tab, dialog: Any) -> None:
        """No dialog is ever answered yes: it is told to the model and sent away. One that
        asks whether to leave the page is let go, or no navigation would ever end."""
        tab.dialogs.append(f"{dialog.type}: {dialog.message}"[:DIALOG_CHARS])
        del tab.dialogs[:-DIALOGS_KEPT]
        self._later(dialog.accept() if dialog.type == "beforeunload" else dialog.dismiss())

    def _later(self, work: Any) -> None:
        async def quietly() -> None:
            try:
                await work
            except Exception:  # noqa: BLE001 - the page or dialog went away first
                pass

        task = asyncio.ensure_future(quietly())
        self._answers.add(task)
        task.add_done_callback(self._answers.discard)
