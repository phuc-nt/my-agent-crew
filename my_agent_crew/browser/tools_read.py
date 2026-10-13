"""The browser tools that read a page a tab already shows. None of them acts on it."""

from __future__ import annotations

import asyncio
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.kit import (
    BrowserTool,
    Kit,
    from_browser,
    one_line,
    text_of,
    timed_out,
)
from my_agent_crew.browser.report import URL_CHARS, fenced, page_report, room
from my_agent_crew.browser.snapshot import address
from my_agent_crew.browser.tabs import Tab
from my_agent_crew.tools.registry import Tool, ToolError

# How long `wait_for` waits for its text.
WAIT_SECONDS = 30
TITLE_SECONDS, TITLE_CHARS, QUERY_CHARS = 2, 100, 80
LEAST_TEXT, ALL = 200, 10**9


def build_snapshot(kit: Kit) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        wanted, head = text_of(args, "wait_for"), ""
        seconds = k.CALL_SECONDS + (WAIT_SECONDS if wanted else 0)
        async with kit.tab(text_of(args, "tab"), seconds=seconds) as (session, tab):
            if wanted:
                # Words the page keeps hidden somewhere are not the words awaited.
                shown = tab.page.get_by_text(wanted).filter(visible=True).first
                try:
                    await shown.wait_for(timeout=WAIT_SECONDS * 1000)
                except Exception as exc:
                    if not timed_out(exc):
                        raise
                    said = one_line(wanted, QUERY_CHARS)
                    head = t.WAIT_TIMEOUT.format(text=said, seconds=WAIT_SECONDS)
            listed, query = k.flag(args, "interactive"), text_of(args, "query")
            return await page_report(kit, session, tab, head=head, listed=listed, query=query)

    return BrowserTool(
        name=k.SNAPSHOT,
        description=d.SNAPSHOT_DESCRIPTION,
        parameters=k.schema(
            (),
            tab=("string", d.PARAM_TAB),
            interactive=("boolean", d.PARAM_INTERACTIVE),
            query=("string", d.PARAM_QUERY),
            wait_for=("string", d.PARAM_WAIT_FOR),
        ),
        run=run,
        replay_safe=True,
    )


def build_text(kit: Kit) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        ref = text_of(args, "ref")
        async with kit.tab(text_of(args, "tab")) as (_session, tab):
            if ref:
                k.known(tab, ref)
                if address(tab.page.url) != tab.shown.url:
                    raise ToolError(t.PAGE_MOVED)
            target = tab.page.locator(f"aria-ref={ref}" if ref else "body")
            if ref and await target.count() != 1:
                raise ToolError(t.REF_GONE.format(ref=ref))
            text = (await target.first.inner_text()).strip() if await target.count() else ""
            outside = [t.PAGE_HEAD_PLAIN.format(label=tab.label)]
            where = t.PAGE_URL.format(url=one_line(tab.page.url, URL_CHARS))
        most = min(k.number(args, "max_chars", LEAST_TEXT, ALL, ALL), room(kit.limit, where))
        if len(text) > most:
            outside.append(t.TEXT_CUT.format(shown=most, total=len(text)))
        return "\n".join([*outside, fenced("\n".join([where, "", text[:most] or t.TEXT_EMPTY]))])

    return BrowserTool(
        name=k.TEXT,
        description=d.TEXT_DESCRIPTION,
        parameters=k.schema(
            (),
            tab=("string", d.PARAM_TAB),
            ref=("string", d.PARAM_TEXT_REF),
            max_chars=("integer", d.PARAM_MAX_CHARS),
        ),
        run=run,
        replay_safe=True,
    )


async def _title(tab: Tab) -> str:
    """A tab's title, "" for a page too busy to say: a stuck tab is still listed."""
    try:
        return await asyncio.wait_for(tab.page.title(), TITLE_SECONDS)
    except Exception as exc:
        if not (from_browser(exc) or isinstance(exc, TimeoutError)):
            raise
        return ""


def build_tabs(kit: Kit) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        """Never starts a browser: an agent whose browser is down has no tab to list."""
        close, owner = text_of(args, "close"), kit.owner()
        session, said = kit.pool.running(kit.agent_id), []
        if close:
            tab = session.tabs.find(owner, close) if session else None
            if tab is None:
                said.append(t.TAB_NOT_OPEN.format(label=one_line(close, 40)))
            else:
                await session.tabs.close(tab)
                said.append(t.TAB_CLOSED.format(label=tab.label))
        mine = session.tabs.of(owner) if session else []
        if not mine:
            return "\n".join([*said, t.TABS_NONE])
        lines = [
            t.TAB_LINE.format(
                label=tab.label,
                url=one_line(tab.page.url, URL_CHARS),
                title=one_line(await _title(tab), TITLE_CHARS),
            )
            for tab in mine
        ]
        return "\n".join([*said, fenced("\n".join(lines))])

    return BrowserTool(
        name=k.TABS,
        description=d.TABS_DESCRIPTION,
        parameters=k.schema((), close=("string", d.PARAM_CLOSE)),
        run=run,
        replay_safe=True,
    )
