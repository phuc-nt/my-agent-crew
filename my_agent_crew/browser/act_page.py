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
from my_agent_crew.browser.snapshot import Node, address, read, same_name
from my_agent_crew.browser.tabs import Tab
from my_agent_crew.tools.registry import ToolError

READ_MS = 2_000
CHOOSER_SECONDS = 2.0
NAME_CHARS = 80
FIELDS = "input, textarea, [contenteditable]"
# What Enter in a form presses: a button of any type but the two that send nothing (a type
# left out, left empty or misspelt is a submit button's), and the two inputs that send.
SUBMITS = (
    "button:not([type=reset i]):not([type=button i])",
    "input[type=submit i]",
    "input[type=image i]",
)
SUBMITS_READ = 5
# Where a control says what it does beside what is drawn of it: all there is of a hidden one.
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


def _quoted(value: str) -> str:
    """A value as a string of a selector, whatever a page wrote in it."""
    return '"' + "".join(c if c.isalnum() else f"\\{ord(c):x} " for c in value) + '"'


def _submits(tied: str) -> str:
    return ", ".join(control + tied for control in SUBMITS)


async def _says(kit: Kit, page: Any, control: Any) -> str:
    """The ask word on one control: in what it holds and declares, or in what the browser
    draws of it, which is what a click on it is judged by."""
    said = [await control.text_content(timeout=READ_MS)]
    said += [await control.get_attribute(x, timeout=READ_MS) for x in SUBMIT_SAYS]
    word = next((found for text in said if (found := kit.ask.find(text or ""))), "")
    if not word:
        word = read(await control.aria_snapshot(mode="ai", timeout=READ_MS), kit.ask).word
        # Drawing one element makes the browser forget the refs of the others: the page is
        # drawn again, which gives every element that did not change the ref it had.
        await page.aria_snapshot(mode="ai")
    return word


async def _submit_word(kit: Kit, page: Any, target: Any) -> str:
    """The word a person is asked for, on a control that sends the form this element belongs
    to: Enter there is a click on it. An element belongs to the form it stands in, or to the
    one its `form` attribute names; so do the controls, wherever on the page they stand."""
    whole = target.locator("xpath=ancestor-or-self::*[last()]")
    named = await target.get_attribute("form", timeout=READ_MS)
    if named is None:
        form = target.locator("xpath=ancestor-or-self::form[1]")
    else:
        form = whole.locator(f"form[id={_quoted(named)}]").first
    if await form.count() != 1:
        return ""
    sending = [form.locator(_submits(":not([form])"))]
    called = await form.get_attribute("id", timeout=READ_MS)
    if called:
        sending.append(whole.locator(_submits(f"[form={_quoted(called)}]")))
    for controls in sending:
        for n in range(min(await controls.count(), SUBMITS_READ)):
            word = await _says(kit, page, controls.nth(n))
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
        declared = {x: await target.get_attribute(x, timeout=READ_MS) for x in a.DECLARED}
        if a.secret_field(declared, name):
            raise ToolError(t.ACT_SECRET_FIELD)
    if kind in ("type", "press"):
        await target.focus(timeout=ms)
        if await target.and_(page.locator(":focus")).count() != 1:
            raise ToolError(t.ACT_NOT_FOCUSED.format(ref=ref))
    if kind == "press" and a.sends(asked.key):
        word = await _submit_word(kit, page, target)
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
