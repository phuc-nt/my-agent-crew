"""A canvas a delegated agent attaches, carried to the agent that asked.

A child's `FILE: artifact:<id>` line names a canvas in the one store every agent shares, so
there is no file to copy. What the parent lacks is the reach: its reply is held to its own,
and a canvas the child made in the child's conversation is outside it. The line is the child
model's text, so it is held to the child's reach first. A canvas that passes is linked to the
parent's conversation and its line rides on as it is; one that does not becomes the sentence
a file that could not be copied becomes.

The relay reads the lines of an answer the way the channel reads the lines of a reply. Where
the two differed, a line after a line break only one of them knew was an attachment the relay
never looked at.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.channels.telegram_attachments import split_reply
from my_agent_crew.config import Route
from my_agent_crew.llm.types import Message
from my_agent_crew.reply_attachments import reply_lines
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.tools.artifact_scope import in_scope
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from my_agent_crew.tools.delegate_attachments import (
    RELAY_DIR,
    canvas_carrier,
    child_answer,
    dropped_attachments,
    relay_attachments,
)
from tests.canvas_helpers import PLAN, agents_canvas, persons_canvas
from tests.test_tools_delegate import agent, delegation_result

ID, OTHER = "0123456789ab", "ba9876543210"
CHART = b"\x89PNG fake chart"
LS = " "  # a line break `str.splitlines` knows and `split("\n")` does not


def lost(path: str) -> str:
    return texts.DELEGATE_ATTACHMENT_LOST.format(path=path)


class Carrier:
    """Stands in for `canvas_carrier`: carries the ids it is built with and keeps every id it
    was asked about."""

    def __init__(self, *carried: str):
        self.carried = carried
        self.asked: list[str] = []

    def __call__(self, artifact_id: str) -> bool:
        self.asked.append(artifact_id)
        return artifact_id in self.carried


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    """The child's workspace, holding one chart, and the parent's."""
    child, parent = tmp_path / "child", tmp_path / "parent"
    (child / "charts").mkdir(parents=True)
    parent.mkdir()
    (child / "charts" / "sleep.png").write_bytes(CHART)
    return child, parent


def test_a_canvas_line_that_is_carried_rides_on_as_it_is(roots):
    child, parent = roots
    carry = Carrier(ID)
    answer = f"Xong.\nFILE: artifact:{ID}\n  MEDIA: artifact: {ID} \ncuối"
    assert relay_attachments(answer, child, parent, "c1", carry) == answer
    assert carry.asked == [ID, ID]
    assert not (parent / RELAY_DIR).exists()


def test_a_canvas_line_that_is_not_carried_becomes_the_sentence_of_a_lost_file(roots):
    """A line that set out to name a canvas and named none is asked about as "", which no
    carrier carries."""
    child, parent = roots
    carry = Carrier(OTHER)
    answer = f"Xong.\nFILE: artifact:{ID}\nMEDIA: artifact:../x\ncuối"
    out = relay_attachments(answer, child, parent, "c1", carry)
    assert out == f"Xong.\n{lost(f'artifact:{ID}')}\n{lost('artifact:../x')}\ncuối"
    assert carry.asked == [ID, ""]


@pytest.mark.parametrize("name", [f"artifact:{ID}", "artifact:x.pdf"])
def test_a_line_that_opens_as_a_canvas_is_never_looked_up_as_a_file(roots, name):
    """Even with a file of that very name in the child's workspace."""
    child, parent = roots
    (child / name).write_bytes(b"%PDF-1.4\n")
    out = relay_attachments(f"FILE: {name}", child, parent, "c1", Carrier())
    assert out == lost(name)
    assert not (parent / RELAY_DIR).exists()


def test_workspace_files_beside_a_canvas_line_are_copied_as_before(roots):
    child, parent = roots
    answer = f"Xong.\nMEDIA: charts/sleep.png\nFILE: artifact:{ID}\nFILE: gone.pdf"
    out = relay_attachments(answer, child, parent, "c1", Carrier(ID))
    copied = f"{RELAY_DIR}/c1/sleep.png"
    assert out == f"Xong.\nMEDIA: {copied}\nFILE: artifact:{ID}\n{lost('gone.pdf')}"
    assert (parent / copied).read_bytes() == CHART


def test_canvas_lines_are_asked_about_when_parent_and_child_share_a_workspace(roots):
    """Sharing a workspace spares the copying of files and their lines stay as written, the
    one that names no file among them. It says nothing about what the child may reach."""
    child, _ = roots
    carry = Carrier(ID)
    answer = f"MEDIA: charts/sleep.png\nFILE: artifact:{ID}\nFILE: artifact:{OTHER}\nFILE: gone.pdf"
    out = relay_attachments(answer, child, child, "c1", carry)
    assert out == (
        f"MEDIA: charts/sleep.png\nFILE: artifact:{ID}\n{lost(f'artifact:{OTHER}')}\nFILE: gone.pdf"
    )
    assert carry.asked == [ID, OTHER]
    assert not (child / RELAY_DIR).exists()


@pytest.mark.parametrize("answer", ["một\r\nhai" + LS + "ba\n", "một\x0chai", "", "\n"])
def test_an_answer_with_nothing_to_carry_comes_back_as_it_was(roots, answer):
    """A child's answer may be handed to the person word for word, line breaks and all."""
    child, parent = roots
    assert relay_attachments(answer, child, parent, "c1", Carrier()) == answer


def test_a_reply_is_cut_into_lines_at_every_line_break_a_string_knows():
    assert reply_lines("a\r\nb" + LS + "c\x0cd\n") == ["a", "b", "c", "d"]
    assert reply_lines("") == []


def test_a_line_after_any_line_break_is_an_attachment_to_the_channel_and_the_relay(roots):
    """Read by `split("\\n")`, the relay took the three lines below for one line of prose and
    handed them on unlooked at; the channel then sent the chart from the parent's workspace
    and the canvas by the parent's reach."""
    child, parent = roots
    answer = f"Xong.{LS}MEDIA: charts/sleep.png{LS}FILE: artifact:{ID}"
    assert split_reply(answer) == ("Xong.", ["charts/sleep.png"], [f"artifact:{ID}"])
    carry = Carrier()
    out = relay_attachments(answer, child, parent, "c1", carry)
    assert out == f"Xong.\nMEDIA: {RELAY_DIR}/c1/sleep.png\n{lost(f'artifact:{ID}')}"
    assert carry.asked == [ID]


def _said(store: Store, *replies: str):
    conv = store.create()
    store.append(conv.id, Message(role="user", content="việc"))
    for reply in replies:
        store.append(conv.id, Message(role="assistant", content=reply))
    return store.history(conv.id)


def test_the_childs_last_words_are_read_line_by_line_the_same_way(store: Store):
    # The ending attaches twice: both lines join the words, each on a line of its own.
    assert child_answer(_said(store, "Ngủ sớm.", f"MEDIA: a.png{LS}FILE: b.csv")) == (
        "Ngủ sớm.\n\nMEDIA: a.png\nFILE: b.csv"
    )
    # The words already carry the chart, so the ending adds nothing.
    words = f"Ngủ sớm.{LS}MEDIA: a.png"
    assert child_answer(_said(store, words, "MEDIA: a.png")) == words
    # An ending with words of its own is the answer; nothing earlier is fetched for it.
    ending = f"MEDIA: a.png{LS}Ngủ sớm."
    assert child_answer(_said(store, "Đọc brief trước.", ending)) == ending


def _delegated(store: Store, result: str):
    """The history of a turn whose one delegation came back with `result`."""
    conv = store.create()
    store.append(conv.id, Message(role="user", content="q"))
    store.append(conv.id, Message(role="tool", content=result, name=DELEGATE_TOOL_NAME))
    return store.history(conv.id)


def test_a_canvas_line_the_parents_reply_left_out_is_put_back(store: Store):
    """Like the line of a file. The sentence a line became is prose and is not put back."""
    line = f"FILE: artifact:{ID}"
    history = _delegated(store, f"Xong.\n{line}\n{lost(f'artifact:{OTHER}')}")
    assert dropped_attachments(history, "Đã xong.") == [line]
    assert dropped_attachments(history, f"Đã xong.\n{line}") == []


def test_dropped_lines_are_looked_for_line_by_line_the_same_way(store: Store):
    history = _delegated(store, f"kết quả{LS}FILE: artifact:{ID}\nMEDIA: a.png")
    assert dropped_attachments(history, "Xong.") == [f"FILE: artifact:{ID}", "MEDIA: a.png"]
    assert dropped_attachments(history, f"Xong.{LS}FILE: artifact:{ID}") == ["MEDIA: a.png"]


@pytest.fixture
def worker(deps_factory):
    return replace(deps_factory().agent, id="worker")


def family(store: Store):
    """A conversation of the boss and the child it delegated to the worker."""
    parent = store.create(agent_id="boss")
    return parent, store.create(agent_id="worker", root_id=parent.id)


def linked(store: Store, conversation_id: str) -> dict[str, bool]:
    """The canvases linked to a conversation, each with whether its children reach it."""
    return {
        link.artifact_id: link.shared for link in store.artifact_links.links_for(conversation_id)
    }


def test_a_canvas_within_the_childs_reach_is_carried_and_linked_to_the_parent(store, worker):
    """Its own, one linked to its conversation, and one the root of its delegation shares.
    The link gives the parent's other children nothing."""
    parent, child = family(store)
    own, seen = agents_canvas(store, "worker"), persons_canvas(store, PLAN, child.id)
    shared = persons_canvas(store, PLAN)
    store.artifact_links.link(parent.id, shared, shared=True)
    carry = canvas_carrier(store, worker, child, parent)
    assert [carry(own), carry(seen), carry(shared), carry(own)] == [True] * 4
    assert linked(store, parent.id) == {shared: True, own: False, seen: False}


def test_a_canvas_outside_the_childs_reach_is_not_carried_and_links_nothing(store, worker):
    """The parent's own canvas and one the parent keeps to itself among them: what the child
    reaches decides, not what the parent does."""
    parent, child = family(store)
    parents, kept = agents_canvas(store, "boss"), persons_canvas(store, PLAN, parent.id)
    elsewhere = persons_canvas(store, PLAN, store.create(agent_id="worker").id)
    carry = canvas_carrier(store, worker, child, parent)
    assert [carry(parents), carry(kept), carry(elsewhere), carry(ID), carry("")] == [False] * 5
    assert linked(store, parent.id) == {kept: False}


def test_the_master_as_a_child_carries_every_canvas_that_is_there(store, deps_factory):
    """It reaches every id, the id of no canvas too, and that one is still not carried."""
    master = deps_factory().agent
    parent, child = family(store)
    theirs = agents_canvas(store, "ledger")
    carry = canvas_carrier(store, master, child, parent)
    assert carry(theirs) and not carry(ID)
    assert linked(store, parent.id) == {theirs: False}


def test_with_no_conversation_to_link_a_reached_canvas_is_still_carried(store, worker):
    child = store.create(agent_id="worker")
    own = agents_canvas(store, "worker")
    carry = canvas_carrier(store, worker, child, None)
    assert carry(own) and not carry(ID)
    assert store.artifact_links.conversations_for(own) == []


@pytest.fixture
def crew(deps_factory, store: Store) -> Runtime:
    """A boss and a worker that says its task back, the two sharing one workspace."""
    base = deps_factory(routes=(Route("fake", "echo"),))
    agents = {"boss": agent(base, "boss", delegates=("worker",)), "worker": agent(base, "worker")}
    runtime = Runtime(base.settings, store, agents, ActivityHub(store))
    runtime.wire_delegation()
    return runtime


async def test_a_delegated_canvas_reaches_the_parent_with_the_reach_to_send_it(crew):
    store = crew.store
    art = agents_canvas(store, "worker")
    parent = store.create(agent_id="boss", autonomous=True)
    reach = {"agent_id": "boss", "is_master": False, "conversation_id": parent.id, "root_id": ""}
    assert not in_scope(store, art, **reach)
    task = f"Xong.\nFILE: artifact:{art}"
    result = await delegation_result(crew, parent.id, "call-1", task=task, agent="worker")
    assert result.reply == f"(echo) {task}"
    assert result.output.endswith(f"\n\n(echo) {task}")
    assert in_scope(store, art, **reach)
    assert linked(store, parent.id) == {art: False}


async def test_a_delegated_line_for_a_canvas_the_child_cannot_reach_is_said_in_words(crew):
    store = crew.store
    parents = agents_canvas(store, "boss")
    parent = store.create(agent_id="boss", autonomous=True)
    task = f"Xong.\nFILE: artifact:{parents}\nMEDIA: artifact:{ID}\nFILE: artifact:x"
    result = await delegation_result(crew, parent.id, "call-1", task=task, agent="worker")
    told = [lost(f"artifact:{parents}"), lost(f"artifact:{ID}"), lost("artifact:x")]
    assert result.reply == "\n".join(["(echo) Xong.", *told])
    assert result.output.endswith(result.reply)
    assert linked(store, parent.id) == {}
