"""A script that did not run to its end fails with what it had printed and then why it ended:
a reply with no opening the web could know it by, since a script prints what it likes. So the
tool says it on a line of its own before anything else (`script/tool.py`), and the web reads
that line, for that tool alone (`web/src/lib/tool-reply.ts`). This holds what the web reads to
the tool's own words, and shows a turn storing each kind of failure under them."""

from __future__ import annotations

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.llm.fake import completion
from my_agent_crew.script.tool import SCRIPT_TOOL
from tests.test_mcp_turns import say
from tests.test_script_turns import PRINTED, SOURCE, running, scripting, the_result
from tests.test_tool_reply_openings import web_constant, web_failed

# Each ends a script another way: stopped at a call it may not make, an error nothing caught,
# not a script at all, refused before it ran.
ENDED_EARLY = {
    "stopped": "print('trước')\ntools.mcp__notion__create_page(title='Báo cáo')\nprint('sau')",
    "raised": "print(tools.mcp__notion__search(query='kế hoạch'))\nundefined_name",
    "unreadable": "print('trước'",
    "refused": "import os\nprint('trước')",
}


def stored_results(app) -> list[tuple[str | None, str]]:
    """Each tool result the thread holds, as the tool's name and what it said: all the web
    has of a call once the page is loaded again."""
    held = [stored.message for stored in app.runtime.store.history(app.conv.id)]
    return [(message.name, message.content) for message in held if message.role == "tool"]


def test_the_web_reads_a_script_that_did_not_end_by_the_tools_own_words():
    said = web_constant("SCRIPT_FAILED")
    assert web_constant("SCRIPT") == SCRIPT_TOOL
    assert said == t.SCRIPT_FAILED
    # It stands on a line of its own with nothing filled in, so the whole of it is read.
    assert "{" not in t.SCRIPT_FAILED and "\n" not in t.SCRIPT_FAILED
    # Neither it nor a failure any tool may meet opens like the other.
    assert not any(said.startswith(other) or other.startswith(said) for other in web_failed())


@pytest.mark.parametrize("source", ENDED_EARLY.values(), ids=ENDED_EARLY.keys())
async def test_a_turn_stores_a_script_that_did_not_end_under_the_line_the_web_reads(served, source):
    script = [completion(tool_calls=[running(source)]), completion("Để tôi sửa.")]
    app, _ = await scripting(served, script)

    result = the_result(await say(app))

    assert (result["name"], result["ok"]) == (web_constant("SCRIPT"), False)
    opening, _, rest = result["output"].partition("\n")
    assert opening == web_constant("SCRIPT_FAILED") and rest.strip()  # then what and why
    assert stored_results(app) == [(SCRIPT_TOOL, result["output"])]


async def test_a_turn_stores_a_script_that_ran_to_its_end_without_that_line(served):
    script = [completion(tool_calls=[running(SOURCE)]), completion("Có hai trang.")]
    app, _ = await scripting(served, script)

    result = the_result(await say(app))

    assert (result["ok"], result["output"]) == (True, PRINTED)
    assert not result["output"].startswith(web_constant("SCRIPT_FAILED"))
    assert stored_results(app) == [(SCRIPT_TOOL, PRINTED)]
