"""Reading a chat message as the answer to a question the agent asked.

A question with choices is shown as a numbered list, because an ordinary chat message has
no radio button. So "2" is a real answer and has to become the second choice's words
before the agent sees it — the agent asked in words and must be answered in words, or
every later reading of that answer would have to know the ordering too.

Only a bare number counts. "2 nhưng dời sang thứ sáu" is someone writing a sentence that
happens to start with a digit, and rewriting that as just "không" would throw away the
part they actually cared about.
"""

from __future__ import annotations

from my_agent_crew.store.models import Approval


def answer_text(text: str, approval: Approval) -> str:
    """What the person said, with a bare choice number resolved to that choice's words.

    Anything else is passed through untouched, including a number outside the range: the
    person may simply have meant the number."""
    stripped = text.strip()
    if not approval.options or not stripped.isdigit():
        return stripped
    index = int(stripped)
    if 1 <= index <= len(approval.options):
        return approval.options[index - 1]
    return stripped
