"""The one browser tool that does something to a page.

Whether a person is asked first is read from what the model was shown of the tab, never from
the page as it is now: the gate asks that question several times for one call, also after a
person answered, and the answer has to be the same each time. What was shown cannot change
while a turn waits, and the action refuses a page that is no longer the one shown
(`act_page`)."""

from __future__ import annotations

from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser import act as a
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.act_page import NAME_CHARS, current, guard, perform
from my_agent_crew.browser.kit import BrowserTool, Kit, one_line, text_of, timed_out
from my_agent_crew.browser.policy import host_allowed, host_of
from my_agent_crew.browser.report import page_report
from my_agent_crew.browser.tabs import Tab
from my_agent_crew.tools.registry import Tool, ToolError

ACT_SECONDS = (1, 8, 30)
HOST_CHARS = 80


def bound(kit: Kit, label: str) -> Tab | None:
    """The tab an action is for: the one named, or the one this conversation's last call was
    on. Never another, and never a browser started to find out."""
    session = kit.pool.running(kit.agent_id)
    if session is None:
        return None
    owner = kit.owner()
    return session.tabs.find(owner, label) if label else session.tabs.last(owner)


def build_act(kit: Kit) -> Tool:
    hosts = kit.settings.hosts

    def ask(args: dict[str, Any]) -> str | None:
        """Why this call stops for a person, None when it need not. It only reads."""
        kind, ref, name = (text_of(args, key) for key in ("kind", "ref", "name"))
        tab = bound(kit, text_of(args, "tab"))
        shown = tab.shown if tab else None
        url = shown.url if shown else tab.page.url if tab else ""
        host = host_of(url) or one_line(url, HOST_CHARS) or "—"
        said = one_line(name, NAME_CHARS)
        if kind == "upload":
            path = one_line(text_of(args, "path"), a.PATH_CHARS)
            return t.ASK_UPLOAD.format(path=path, host=host, name=said)
        node = shown.nodes.get(ref) if shown else None
        if node is None or kind not in a.KINDS:
            return None  # nothing will be done: the call refuses by itself
        if hosts and not host_allowed(host_of(url), hosts):
            return t.ASK_OUTSIDE_HOSTS.format(kind=kind, host=host)
        word = a.word_for(kit.ask, kind, name, text_of(args, "value"), node)
        return t.ASK_WORD.format(kind=kind, name=said, host=host, word=word) if word else None

    async def run(args: dict[str, Any]) -> str:
        asked = a.read(args, kit.workspace)
        wait = k.number(args, "timeout_s", *ACT_SECONDS)
        done = ""
        try:
            seconds = wait + k.CALL_SECONDS
            async with kit.tab(text_of(args, "tab"), seconds=seconds, last=True) as (session, tab):
                target, node = await current(kit, tab, asked)
                mark = session.proxy.refused_total
                before = {x.id for x in session.tabs.of(tab.owner)}
                try:
                    await guard(kit, tab.page, target, asked, node.name, wait * 1000)
                    await perform(tab.page, target, asked, wait * 1000)
                except Exception as exc:
                    if not timed_out(exc):
                        raise
                    raise ToolError(t.ACT_TIMEOUT.format(ref=asked.ref, seconds=wait)) from exc
                done = t.ACT_DONE.format(kind=asked.kind, ref=asked.ref)
                closed = t.ACT_TAB_CLOSED.format(kind=asked.kind, ref=asked.ref, label=tab.label)
                page = tab.page
                await k.settle(page)
                if page.is_closed():
                    return closed
                return await page_report(kit, session, tab, head=done, mark=mark, before=before)
        except ToolError as exc:
            if not done:
                raise
            # Done is done: a page that cannot be read afterwards is no reason to do it twice.
            return closed if page.is_closed() else "\n".join([done, t.ACT_UNSEEN.format(error=exc)])

    return BrowserTool(
        name=k.ACT,
        description=d.ACT_DESCRIPTION,
        parameters=k.schema(
            ("kind", "ref", "name"),
            kind=("string", d.PARAM_KIND),
            ref=("string", d.PARAM_REF),
            name=("string", d.PARAM_NAME),
            text=("string", d.PARAM_ACT_TEXT),
            key=("string", d.PARAM_KEY),
            value=("string", d.PARAM_VALUE),
            path=("string", d.PARAM_PATH),
            tab=("string", d.PARAM_ACT_TAB),
            timeout_s=("integer", d.PARAM_ACT_TIMEOUT),
        ),
        run=run,
        requires_approval=True,
        ask_when=ask,
    )
