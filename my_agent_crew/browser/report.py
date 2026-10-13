"""What a browser tool tells the model of a page.

Whatever a page has a say in (its address, its title, its dialogs, the hosts it reached for,
its outline) is put between two fence lines made for this one answer, under a line saying it
is data. Outside the fence stand only words of this program and what the model itself said.
A page is sized so the whole answer stays under the registry's cap: an answer cut by the
registry would lose its closing fence."""

from __future__ import annotations

import re
import secrets

from my_agent_crew import texts_browser as t
from my_agent_crew.browser.kit import Kit, look, one_line, show
from my_agent_crew.browser.pool import Session
from my_agent_crew.browser.snapshot_view import LIST, view
from my_agent_crew.browser.tabs import Tab

URL_CHARS, TITLE_CHARS, HOST_CHARS, DIALOG_CHARS = 300, 200, 80, 300
HOSTS_TOLD = 5
# What a host name is made of. A name is said outside the fence, so nothing else is kept.
NOT_HOST = re.compile(r"[^a-z0-9._:\[\]-]")
# Left for the notes written once the outline is sized, and never less than this of outline.
NOTE_ROOM, LEAST_ROOM = 300, 500


def fence() -> tuple[str, str, str]:
    """The line that says what the fence is, and the two lines of the fence itself. The
    number in them is made anew each time: a page cannot write a line that closes it."""
    nonce = secrets.token_hex(8)
    opening, closing = t.PAGE_OPEN.format(nonce=nonce), t.PAGE_CLOSE.format(nonce=nonce)
    return t.PAGE_FENCE.format(opening=opening, closing=closing), opening, closing


def fenced(body: str) -> str:
    said, opening, closing = fence()
    return "\n".join([said, opening, body, closing])


def room(limit: int, *written: str) -> int:
    """What is left under the cap for a page's own text, beside everything else an answer
    holds and its fence."""
    used = sum(len(part) + 1 for part in (*written, *fence()))
    return max(LEAST_ROOM, limit - used - NOTE_ROOM)


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
    reached for and what it opened since are told."""
    url, snapshot = await look(kit, tab)
    show(tab, url, snapshot)
    title = await tab.page.title()
    label = t.PAGE_HEAD.format(label=tab.label, status=status) if status else ""
    outside = [head, label or t.PAGE_HEAD_PLAIN.format(label=tab.label)]
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
    seen = view(snapshot, room(kit.limit, *outside, *inside), listed=listed, query=query)
    if seen.shown < seen.total:
        outside.append(t.PAGE_CUT.format(shown=seen.shown, total=seen.total))
    elif seen.kind == LIST and not listed:
        outside.append(t.PAGE_LISTED.format(shown=seen.shown, total=seen.total))
    nothing = t.PAGE_NO_MATCH.format(query=one_line(query, 80)) if query.strip() else t.PAGE_EMPTY
    body = "\n".join([*inside, "", seen.text or nothing])
    return "\n".join([*(line for line in outside if line), fenced(body)])
