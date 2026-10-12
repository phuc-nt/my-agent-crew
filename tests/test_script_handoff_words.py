"""The web thread knows the message a script job opens a turn with by the server's own
words: the two marker lines (`web/src/lib/script-handoff.ts`) and the whole sentence over
them (`scriptHandoff.fence` in `web/src/i18n/vi.ts`). It leaves that sentence out of the
bubble, so it takes no other. Nothing at runtime reads both sides: reworded on the server
alone, every handed-on message would fall back to raw text and nothing else would fail."""

from __future__ import annotations

import re
from pathlib import Path

from my_agent_crew import texts_script_job as words
from my_agent_crew.scheduler.script_job import handed_on

WEB = Path(__file__).resolve().parents[1] / "web" / "src"
SPLITTER = WEB / "lib" / "script-handoff.ts"
STRINGS = WEB / "i18n" / "vi.ts"


def web_marker(name: str) -> str:
    """A marker line as the web holds it, taken from its source."""
    source = SPLITTER.read_text(encoding="utf-8")
    found = re.findall(rf'^const {name} = "([^"\\]+)";$', source, re.MULTILINE)
    assert len(found) == 1, f"{name} is no longer a one-line string constant in {SPLITTER.name}"
    return found[0]


def web_sentence() -> str:
    """The sentence the web takes for the server's, with its two placeholders."""
    source = STRINGS.read_text(encoding="utf-8")
    found = re.findall(r'^    fence: "([^"\\]+)",$', source, re.MULTILINE)
    assert len(found) == 1, f"scriptHandoff.fence is no longer a one-line string in {STRINGS.name}"
    return found[0]


def test_the_web_holds_the_two_marker_lines_as_the_server_writes_them():
    assert web_marker("OPENING") == words.JOB_PRINTED_OPEN
    assert web_marker("CLOSING") == words.JOB_PRINTED_CLOSE


def test_the_web_holds_the_sentence_over_the_output_word_for_word():
    assert web_sentence() == words.JOB_PRINTED_FENCE


def test_the_web_fills_the_sentence_into_the_line_the_server_writes():
    """The web puts each marker in once, where the server formats the sentence. A brace or
    a second mention on the server's side would part the two with the words still equal."""
    lines = handed_on("Tóm tắt các đơn mới.", "2 đơn mới").split("\n")
    opening, closing = lines[-3], lines[-1]
    # The number is read off the closing line the way the web reads it: sixteen hex digits.
    shape = re.escape(web_marker("CLOSING")).replace(re.escape("{nonce}"), "([0-9a-f]{16})")
    told = re.fullmatch(shape, closing)
    assert told is not None
    assert opening == web_marker("OPENING").replace("{nonce}", told.group(1))
    filled = web_sentence().replace("{opening}", opening, 1).replace("{closing}", closing, 1)
    assert lines[-4] == filled
    assert lines[:-4] == ["Tóm tắt các đơn mới.", ""]
