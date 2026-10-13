"""What is checked of an element on the page before anything is done to it, and the doing.

The model names an element by the ref and the name it was shown. Here the page is drawn
again, and the element has to be the one shown still; it has to be of a kind the action is
for; and then the one thing asked is done to it."""

from __future__ import annotations

import asyncio
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew.browser import act as a
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.kit import Kit, one_line
from my_agent_crew.browser.snapshot import Node, address, same_name
from my_agent_crew.browser.tabs import Tab
from my_agent_crew.tools.registry import ToolError

READ_MS = 2_000
CHOOSER_SECONDS = 2.0
NAME_CHARS = 80
FIELDS = "input, textarea, [contenteditable]"
# What Enter in a form presses, and where such a control says what it does.
SUBMITS = "button:not([type]), button[type=submit], input[type=submit], input[type=image]"
SUBMITS_READ = 5
SUBMIT_SAYS = ("value", "aria-label", "title", "alt")


async def current(kit: Kit, tab: Tab, asked: a.Asked) -> tuple[Any, Node]:
    """The element as it is now, once it is known to be the one the model was shown: on the
    same page, of the same kind, under the name given, and stopping for a person for the same
    word as when the gate looked."""
    shown = k.known(tab, asked.ref)
    was = tab.shown.url
    url, fresh = await k.look(kit, tab)
    if url != was or address(tab.page.url) != was:
        raise ToolError(t.PAGE_MOVED)
    node = fresh.nodes.get(asked.ref)
    if node is None or node.role != shown.role:
        raise ToolError(t.REF_GONE.format(ref=asked.ref))
    if not same_name(asked.name, node.name):
        said = one_line(asked.name, NAME_CHARS)
        raise ToolError(t.NAME_MISMATCH.format(ref=asked.ref, name=said))
    words = [a.word_for(kit.ask, asked.kind, asked.name, asked.value, x) for x in (node, shown)]
    if words[0] != words[1]:
        raise ToolError(t.STALE_ASK.format(ref=asked.ref))
    target = tab.page.locator(f"aria-ref={asked.ref}")
    if await target.count() != 1:
        raise ToolError(t.REF_GONE.format(ref=asked.ref))
    return target, node


async def _submit_word(kit: Kit, target: Any) -> str:
    """The word a person is asked for, on a control that sends the form this element is in:
    Enter there is a click on it."""
    controls = target.locator("xpath=ancestor-or-self::form[1]").locator(SUBMITS)
    for n in range(min(await controls.count(), SUBMITS_READ)):
        control = controls.nth(n)
        said = [await control.text_content(timeout=READ_MS)]
        said += [await control.get_attribute(x, timeout=READ_MS) for x in SUBMIT_SAYS]
        for text in said:
            word = kit.ask.find(text or "")
            if word:
                return word
    return ""


async def guard(kit: Kit, page: Any, target: Any, asked: a.Asked, name: str, ms: int) -> None:
    """What the element itself has to be before anything is done to it. The browser would
    pass text given to a label on to the field it labels, and keys given to an element that
    takes none to whatever holds the cursor: either way into a field nobody looked at."""
    kind, ref = asked.kind, asked.ref
    if kind == "fill" and await target.and_(page.locator(FIELDS)).count() != 1:
        raise ToolError(t.ACT_NOT_FIELD.format(ref=ref))
    if kind == "select" and await target.and_(page.locator("select")).count() != 1:
        raise ToolError(t.ACT_NOT_SELECT.format(ref=ref))
    if kind in a.KEYBOARD:
        declared = [
            await target.get_attribute(x, timeout=READ_MS) for x in ("type", "autocomplete")
        ]
        if a.secret_field(*declared, name):
            raise ToolError(t.ACT_SECRET_FIELD)
    if kind in ("type", "press"):
        await target.focus(timeout=ms)
        if await target.and_(page.locator(":focus")).count() != 1:
            raise ToolError(t.ACT_NOT_FOCUSED.format(ref=ref))
    if kind == "press" and a.sends(asked.key):
        word = await _submit_word(kit, target)
        if word:
            raise ToolError(t.ACT_ENTER_SUBMITS.format(word=word))


async def _upload(page: Any, target: Any, asked: a.Asked, ms: int) -> None:
    """A file goes to the chooser the element opens and nowhere else: a click that opens
    none uploads nothing."""
    opened: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

    def take(chooser: Any) -> None:
        if not opened.done():
            opened.set_result(chooser)

    page.on("filechooser", take)
    try:
        await target.click(timeout=ms)
        chooser = await asyncio.wait_for(opened, CHOOSER_SECONDS)
    except TimeoutError as exc:  # the wait here: a click the browser gave up on is its own error
        raise ToolError(t.ACT_NO_CHOOSER.format(ref=asked.ref)) from exc
    finally:
        page.remove_listener("filechooser", take)
    await chooser.set_files(str(asked.file))


async def perform(page: Any, target: Any, asked: a.Asked, ms: int) -> None:
    match asked.kind:
        case "click":
            await target.click(timeout=ms)
        case "type":
            await target.press_sequentially(asked.text, timeout=ms)
        case "fill":
            await target.fill(asked.text, timeout=ms)
        case "press":
            await target.press(asked.key, timeout=ms)
        case "select":
            await target.select_option(label=asked.value, timeout=ms)
        case "hover":
            await target.hover(timeout=ms)
        case "scroll":
            await target.scroll_into_view_if_needed(timeout=ms)
        case _:
            await _upload(page, target, asked, ms)
