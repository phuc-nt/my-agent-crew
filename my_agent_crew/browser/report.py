"""What a browser tool tells the model of a page.

Whatever a page has a say in (its address, its title, its dialogs, the hosts it reached for,
its outline) is put between two fence lines made for this one answer, under a line saying it
is data. Outside the fence stand only words of this program and what the model itself said.
The outline is sized so the whole answer stays under the agent's cap (`fence.py`)."""

from __future__ import annotations

import re

from my_agent_crew import texts_browser as t
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser.fence import answer, room
from my_agent_crew.browser.kit import Kit, look, one_line, show
from my_agent_crew.browser.pool import Session
from my_agent_crew.browser.snapshot_view import LIST, added, view
from my_agent_crew.browser.tabs import Tab

URL_CHARS, TITLE_CHARS, HOST_CHARS, DIALOG_CHARS = 300, 200, 80, 300
HOSTS_TOLD = 5
# What a host name is made of. A page chooses the names it reaches for: they are told inside
# a fence, on one line, so nothing that could end a line or be read as words is kept.
NOT_HOST = re.compile(r"[^a-z0-9._:\[\]-]")


def told(hosts: list[str]) -> str:
    """Hosts a page reached for, each once, as few as fit a line."""
    names = dict.fromkeys(NOT_HOST.sub("", host.lower())[:HOST_CHARS] for host in hosts)
    return ", ".join(name for name in list(names)[:HOSTS_TOLD] if name)


async def page_report(
    kit: Kit,
    session: Session,
    tab: Tab,
    *,
    head: str = "",
    status: int | None = None,
    mark: int | None = None,
    before: set[int] | None = None,
    listed: bool = False,
    query: str = "",
) -> str:
    """The tab as it is now, kept as what the model was shown. `mark` is where the proxy's
    count of refusals stood before the call, `before` the caller's tabs then: what the page
    reached for and what it opened since are told, and what is on it now that was not on it
    when the model was last shown it is marked."""
    url, snapshot = await look(kit, tab)
    fresh = added(tab.shown, url, snapshot)
    show(tab, url, snapshot)
    title = await tab.page.title()
    label = t.PAGE_HEAD.format(label=tab.label, status=status) if status else ""
    outside = [*([head] if head else []), label or t.PAGE_HEAD_PLAIN.format(label=tab.label)]
    if before is not None:
        opened = sorted(x.label for x in session.tabs.of(tab.owner) if x.id not in before)
        outside += [t.PAGE_NEW_TABS.format(labels=", ".join(opened))] if opened else []
    inside = [
        t.PAGE_URL.format(url=one_line(tab.page.url, URL_CHARS)),
        t.PAGE_TITLE.format(title=one_line(title, TITLE_CHARS)),
    ]
    refused = session.proxy.refused_since(mark) if mark is not None else []
    inside += [t.PAGE_REFUSED.format(hosts=told(refused))] if refused else []
    inside += [t.PAGE_DIALOG.format(text=one_line(said, DIALOG_CHARS)) for said in tab.dialogs]
    tab.dialogs.clear()
    budget = room(kit.limit, *outside, *inside)
    seen = view(snapshot, budget, listed=listed, query=query, fresh=fresh)
    if seen.shown < seen.total:
        outside.append(t.PAGE_CUT.format(shown=seen.shown, total=seen.total))
    elif seen.kind == LIST and not listed:
        outside.append(t.PAGE_LISTED.format(shown=seen.shown, total=seen.total))
    outside += [d.PAGE_NEW.format(count=seen.new)] if seen.new else []
    nothing = t.PAGE_NO_MATCH.format(query=one_line(query, 80)) if query.strip() else t.PAGE_EMPTY
    # A page with lines that none of fit says so above, not that it is empty.
    body = "\n".join([*inside, "", seen.text or ("" if seen.total else nothing)])
    return answer(kit.limit, outside, body)
