"""A script and the canvas: listing is a read like any other, but a page read is not a script's
to make. Reading a version to its end is what tells a rewrite that the agent has seen what the
person wrote, and the model is handed only what a script prints."""

from textwrap import dedent

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.agent.turn_context import (
    CHAT,
    set_tool_call_id,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.artifacts.tag import TAG_RE
from my_agent_crew.script.scope import SCRIPT_TOOL, callable_tools
from my_agent_crew.script.tool import script_tool
from my_agent_crew.store import Store
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.tools.artifact import build_artifact_tools
from my_agent_crew.tools.registry import ToolRegistry

CAP = 8000
LINES = 400


def body(word: str) -> str:
    return "".join(f"{word} {number:05d}\n" for number in range(1, LINES + 1))


@pytest.fixture
def canvas():
    """A canvas the agent made and read whole, which the person then saved a version of."""
    store = Store(":memory:")
    registry = ToolRegistry(build_artifact_tools(store, "coach", False, CAP), CAP)
    registry.register(script_tool(lambda: registry, []))
    conv = store.create()
    set_turn_source(CHAT)
    set_turn_conversation(conv.id)
    set_tool_call_id("c1")
    return store, registry, conv


async def made_then_saved_by_the_person(store, registry) -> str:
    made = await registry.execute(
        "artifact_create", {"title": "Kế hoạch", "kind": "markdown", "content": body("dòng")}
    )
    art = TAG_RE.match(made.output)[1]
    store.artifacts.write(art, body("người sửa"), USER, "")
    return art


def test_a_script_may_list_canvases_but_not_read_one(canvas):
    _, registry, _ = canvas

    may = [tool.name for tool in callable_tools(registry)]

    assert may == ["artifact_list"]


async def test_a_script_cannot_page_a_canvas_and_is_told_to_read_it_directly(canvas):
    store, registry, conv = canvas
    art = await made_then_saved_by_the_person(store, registry)
    set_tool_call_id("c2")
    source = f"""
        for first in range(1, {LINES + 1}, 100):
            tools.artifact_read(id="{art}", from_line=first, lines=100)
        print("đã đọc hết")
        """

    ran = await registry.execute(SCRIPT_TOOL, {"script": dedent(source)})

    refused = t.SCRIPT_NOT_FROM_SCRIPT.format(name="artifact_read", instead="gọi trực tiếp")
    assert not ran.ok
    assert refused in ran.output
    assert "đã đọc hết" not in ran.output
    assert ran.calls == ()


async def test_a_script_leaves_the_persons_version_unseen_so_a_rewrite_is_still_refused(canvas):
    store, registry, conv = canvas
    art = await made_then_saved_by_the_person(store, registry)
    seen_before = store.artifact_links.get(conv.id, art).seen_version
    set_tool_call_id("c2")
    source = f"""
        try:
            for first in range(1, {LINES + 1}, 100):
                tools.artifact_read(id="{art}", from_line=first, lines=100)
        except Exception:
            pass
        print(len(tools.artifact_list()))
        """
    await registry.execute(SCRIPT_TOOL, {"script": dedent(source)})

    set_tool_call_id("c3")
    rewrite = await registry.execute("artifact_rewrite", {"id": art, "content": "bản của model\n"})

    assert store.artifact_links.get(conv.id, art).seen_version == seen_before == 1
    assert not rewrite.ok
    head = store.artifacts.head(art)
    assert (head.version, head.content) == (2, body("người sửa"))


async def test_the_agent_reading_the_canvas_itself_to_its_end_may_rewrite_it(canvas):
    store, registry, conv = canvas
    art = await made_then_saved_by_the_person(store, registry)

    for first in range(1, LINES + 1, 100):
        set_tool_call_id(f"r{first}")
        page = await registry.execute(
            "artifact_read", {"id": art, "from_line": first, "lines": 100}
        )
        assert page.ok
    set_tool_call_id("c3")
    rewrite = await registry.execute("artifact_rewrite", {"id": art, "content": "bản của model\n"})

    assert rewrite.ok
    assert store.artifacts.head(art).version == 3
