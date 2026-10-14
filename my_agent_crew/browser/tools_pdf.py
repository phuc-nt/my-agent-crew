"""The browser tool that prints the page of a tab as a PDF in the workspace. It only looks:
nothing on the page changes, so nobody is asked and a script may call it."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from my_agent_crew import texts_browser_files as f
from my_agent_crew import texts_browser_tools as d
from my_agent_crew.browser import downloads as dl
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.kit import BrowserTool, Kit, text_of
from my_agent_crew.browser.saved import file_name
from my_agent_crew.browser.tools_files import MB, kept, put, room, size_said, why
from my_agent_crew.tools.registry import Tool, ToolError

# Printing has no limit of its own in the browser: the call's is the only one.
PDF_SECONDS = 30


def build_pdf(kit: Kit, write_paths: Sequence[str] = ()) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        shown = await room(kit, write_paths)
        seconds = PDF_SECONDS + k.CALL_SECONDS
        async with kit.tab(text_of(args, "tab"), seconds=seconds) as (_session, tab):
            title = await tab.page.title()
            data = await tab.page.pdf(format="A4", print_background=True)
            label = tab.label
        if len(data) > dl.LIMIT_BYTES:
            raise ToolError(f.PDF_TOO_LARGE.format(limit=dl.LIMIT_BYTES / MB))
        name = file_name(text_of(args, "save_as") or title, "page", "pdf")
        try:
            name, size = await put(kit, shown, name, data)
        except OSError as exc:
            raise ToolError(f.PDF_NOT_SAVED.format(error=why(exc))) from exc
        said = f.PDF_SAVED.format(label=label, folder=shown, size=size_said(size))
        return kept(kit, said, shown, f.SAVED_AS.format(path=f"{shown}/{name}"))

    return BrowserTool(
        name=k.PDF,
        description=f.PDF_DESCRIPTION,
        parameters=k.schema(
            (),
            tab=("string", d.PARAM_TAB),
            save_as=("string", f.PARAM_PDF_SAVE_AS),
        ),
        run=run,
        replay_safe=True,
    )
