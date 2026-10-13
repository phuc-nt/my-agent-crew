"""The browser tool that sends a tab to an address.

The address is checked before a tab is opened and every connection the page then makes is
checked again by the proxy. A hop the proxy refused ends the call with the tab left blank:
the model is never shown a page that was reached by way of a private address. Which
address that was, and what the browser wrote of a page it could not open, a page may have
chosen: both are told inside a fence."""

from __future__ import annotations

import asyncio
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.fence import driver_error, failure
from my_agent_crew.browser.kit import BrowserTool, Kit, from_browser, one_line, text_of, timed_out
from my_agent_crew.browser.network import always_refused, check_url
from my_agent_crew.browser.policy import host_allowed, host_of
from my_agent_crew.browser.pool import Session
from my_agent_crew.browser.proxy import MARK
from my_agent_crew.browser.report import URL_CHARS, page_report, told
from my_agent_crew.browser.tabs import Tab
from my_agent_crew.tools.registry import Tool, ToolError

# How long a page is given to load: least, default, most.
LOAD_SECONDS = (5, 20, 60)
BLANKS, BLANK_PAUSE = 3, 0.2


async def _blank(tab: Tab) -> None:
    """A tab whose page was refused shows nothing, the refusal included. The browser may
    still be putting up an error page of its own, which pushes the blank one aside once."""
    for _ in range(BLANKS):
        try:
            return await tab.page.goto("about:blank", timeout=5_000)
        except Exception as exc:
            if not from_browser(exc):
                raise
            await asyncio.sleep(BLANK_PAUSE)


def _refusal(limit: int, hosts: list[str]) -> ToolError:
    return failure(limit, t.NAV_REFUSED, t.PAGE_REFUSED.format(hosts=told(hosts)))


async def _go(session: Session, tab: Tab, url: str, wait: int, mark: int, limit: int) -> int | None:
    """Send the tab to `url`; the status its page answered with. A hop the proxy refused on
    the way (the address itself was checked before) ends the call and leaves the tab blank."""
    try:
        response = await tab.page.goto(url, wait_until="domcontentloaded", timeout=wait * 1000)
    except Exception as exc:
        if not from_browser(exc):
            raise
        refused = session.proxy.refused_since(mark)
        await _blank(tab)
        if timed_out(exc):
            raise ToolError(t.NAV_SLOW.format(seconds=wait)) from exc
        if refused:
            raise _refusal(limit, refused) from exc
        raise driver_error(limit, t.NAV_FAILED, exc) from exc
    if response is None or MARK not in response.headers or response.status < 400:
        return response.status if response else None
    # The proxy's own answer: no site was reached, or the one reached was not let through.
    reached = tab.page.url
    refused = session.proxy.refused_since(mark) or [host_of(reached) or host_of(url)]
    await _blank(tab)
    if response.status == 403:
        raise _refusal(limit, refused)
    if response.status == 502:
        where = t.PAGE_URL.format(url=one_line(reached, URL_CHARS))
        raise failure(limit, t.NAV_UNREACHABLE, where)
    raise ToolError(t.NAV_FAILED.format(error=f"HTTP {response.status}"))


def build_navigate(kit: Kit) -> Tool:
    hosts = kit.settings.hosts

    def doomed(args: dict[str, Any]) -> bool:
        """An address the call refuses whatever a person says. Nobody is asked about one: a
        yes would change nothing, so the call goes straight to its refusal."""
        return always_refused(text_of(args, "url"), kit.pool.allow)

    def outside(args: dict[str, Any]) -> str | None:
        """An agent given hosts stops for a person before it opens any other."""
        host = host_of(text_of(args, "url"))
        if hosts and host and not host_allowed(host, hosts) and not doomed(args):
            return t.ASK_NAV_OUTSIDE.format(host=host)
        return None

    def routine(args: dict[str, Any]) -> bool:
        return doomed(args) or host_allowed(host_of(text_of(args, "url")), hosts)

    async def run(args: dict[str, Any]) -> str:
        # The browser is given the address as it was read here, never as it was written.
        url = await check_url(text_of(args, "url"), kit.pool.resolver, kit.pool.allow)
        wait = k.number(args, "timeout_s", *LOAD_SECONDS)
        label, seconds = text_of(args, "tab"), wait + k.CALL_SECONDS
        async with kit.tab(label, seconds=seconds, make=True) as (session, tab):
            mark = session.proxy.refused_total
            before = {other.id for other in session.tabs.of(tab.owner)}
            tab.shown = None
            status = await _go(session, tab, url, wait, mark, kit.limit)
            return await page_report(kit, session, tab, status=status, mark=mark, before=before)

    return BrowserTool(
        name=k.NAVIGATE,
        description=d.NAVIGATE_DESCRIPTION,
        parameters=k.schema(
            ("url",),
            url=("string", d.PARAM_URL),
            tab=("string", d.PARAM_NAV_TAB),
            timeout_s=("integer", d.PARAM_NAV_TIMEOUT),
        ),
        run=run,
        requires_approval=True,
        ask_when=outside,
        allow_when=routine,
    )
