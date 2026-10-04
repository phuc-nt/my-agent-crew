"""Changes a canvas note tells in one line naming who made them, never as a diff: a picture
has no text to diff, and a version imported from a file may be a whole built page. Neither
makes the new version seen, so the agent still has to read the canvas before writing over
it."""

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.artifact_models import IMPORT_NOTE, USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_AUTHORS,
    ARTIFACT_VERSION_CONFLICT,
    CANVAS_NOTE_BUMP,
    CANVAS_NOTE_READ,
)
from tests.canvas_helpers import PLAN, SWIM, call, created, framed, noted, say, seen, turn

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(32))
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(range(32))


@pytest.fixture(autouse=True)
def fresh_turn():
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def _bump(title: str, art: str, head: int, groups: str) -> str:
    bump = CANVAS_NOTE_BUMP.format(title=title, id=art, head=head)
    return " ".join([bump, ARTIFACT_AUTHORS.format(groups=groups), CANVAS_NOTE_READ])


def test_a_picture_that_changed_is_told_in_one_line_and_stays_unseen(store: Store):
    """The person's own plain write would be diffed on a text canvas. A picture has no text:
    a diff of nothing would tell the agent nothing and still count the new picture as seen."""
    conv = turn(store)
    art = store.artifacts.create("Ảnh bìa", "image", "", USER, "", data=PNG).id
    store.artifact_links.mark_seen(conv.id, art, 1)
    store.artifacts.write(art, None, USER, "", data=JPEG)
    assert say(store, conv) == framed(_bump("Ảnh bìa", art, 2, "v2 người"))
    assert (seen(store, conv, art), noted(store, conv, art)) == (1, 2)
    assert say(store, conv) == ""


async def test_a_reimport_from_the_web_is_told_in_one_line_and_stays_unseen(store: Store):
    """The person pressed re-import: the version is theirs, but its text is the file's, so it
    is named as an import instead of being diffed into the prompt."""
    conv = turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, SWIM, USER, "", base_version=1, note=IMPORT_NOTE)
    assert say(store, conv) == framed(_bump("Kế hoạch", art, 2, "v2 người nhập từ tệp"))
    assert (seen(store, conv, art), noted(store, conv, art)) == (1, 2)
    rewrite = await call(store, "artifact_rewrite", {"id": art, "content": "# Kế hoạch\nnghỉ\n"})
    refused = TOOL_FAILED.format(error=ARTIFACT_VERSION_CONFLICT.format(head=2) + "\n")
    assert rewrite.output.startswith(refused)
    assert say(store, conv) == ""
