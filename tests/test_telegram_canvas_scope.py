"""Which canvases a reply may send to the chat.

A line naming a canvas is the model's text, so it is held to what the agent's canvas tools
would let it read: the master reaches every canvas, anyone else the ones it made, the ones
linked to the conversation and the ones the root of its delegation shares. A canvas out of
reach is answered with the sentence of one that is not there, so a reply cannot be used to
find out which ids exist.

A canvas imported from a workspace file is that file under another name. The list of formats
a `FILE:` line may send exists so a reply cannot mail out a key file; importing the file first
must not be a way round it.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew import texts
from my_agent_crew.config import Route
from my_agent_crew.store.artifact_models import USER
from tests.canvas_helpers import PLAN, PNG, agents_canvas, persons_canvas

ID = "0123456789ab"


@pytest.fixture
def crew(make_channel, deps_factory, tmp_path):
    """A channel whose master shares the bot, and the store, with the coach."""
    master = deps_factory(routes=(Route("fake", "echo"),))
    coach = deps_factory(routes=(Route("fake", "echo"),), home=tmp_path / "coach-home")
    coach.profile = replace(coach.agent, id="coach", name="HLV")
    channel = make_channel(master)
    channel.agents["coach"] = coach
    return channel


def missing(artifact_id: str) -> str:
    return texts.TELEGRAM_CANVAS_MISSING.format(id=artifact_id)


def imported(store, source: str, kind: str = "code", agent_id: str = "default") -> str:
    """A text canvas recorded as imported from `source`."""
    author = f"agent:{agent_id}"
    return store.artifacts.create(
        "Nhập", kind, agent_id, author, "", "x = 1\n", None, "", source
    ).id


async def test_a_canvas_out_of_reach_reads_as_one_that_is_not_there(crew, fake):
    store = crew.store
    conv = store.create(agent_id="coach")
    theirs, persons = agents_canvas(store, "ledger"), persons_canvas(store, PLAN)
    reply = f"FILE: artifact:{theirs}\nFILE: artifact:{persons}\nFILE: artifact:{ID}"
    await crew.outbound("coach").send(reply, conv.id)
    assert fake.sent == [missing(theirs), missing(persons), missing(ID)]
    assert fake.uploads == []


async def test_an_agent_sends_what_it_made_whatever_became_of_the_conversation(crew, fake):
    """A brief delivered with no conversation named, and a reply whose conversation was
    deleted while it was on its way, still carry the canvases the agent itself made."""
    store = crew.store
    mine = agents_canvas(store, "coach")
    gone = store.create(agent_id="coach")
    store.delete(gone.id)
    await crew.outbound("coach").send(f"FILE: artifact:{mine}")
    await crew.outbound("coach").send(f"FILE: artifact:{mine}", gone.id)
    assert [upload.name for upload in fake.uploads] == ["Kế hoạch.md", "Kế hoạch.md"]
    assert fake.sent == []


async def test_a_linked_canvas_is_sent_for_its_conversation_alone(crew, fake):
    store = crew.store
    conv, other = store.create(agent_id="coach"), store.create(agent_id="coach")
    art = persons_canvas(store, PLAN, conv.id)
    out = crew.outbound("coach")
    await out.send(f"FILE: artifact:{art}", conv.id)
    assert [upload.data for upload in fake.uploads] == [PLAN.encode()] and fake.sent == []
    await out.send(f"FILE: artifact:{art}", other.id)
    await out.send(f"FILE: artifact:{art}")
    store.delete(conv.id)
    await out.send(f"FILE: artifact:{art}", conv.id)
    assert fake.sent == [missing(art)] * 3 and len(fake.uploads) == 1


async def test_what_the_root_of_a_delegation_shares_reaches_its_child(crew, fake):
    store = crew.store
    root = store.create()
    child = store.create(agent_id="coach", root_id=root.id)
    shared, kept = persons_canvas(store, PLAN), persons_canvas(store, "riêng\n")
    store.artifact_links.link(root.id, shared, shared=True)
    store.artifact_links.link(root.id, kept)
    await crew.outbound("coach").send(f"FILE: artifact:{kept}\nFILE: artifact:{shared}", child.id)
    assert fake.sent == [missing(kept)]
    assert [upload.data for upload in fake.uploads] == [PLAN.encode()]


async def test_the_master_sends_a_canvas_of_any_agent_and_any_conversation(crew, fake):
    store = crew.store
    elsewhere = store.create(agent_id="coach")
    theirs, persons = agents_canvas(store, "ledger"), persons_canvas(store, PLAN, elsewhere.id)
    await crew.outbound().send(f"FILE: artifact:{theirs}\nFILE: artifact:{persons}")
    assert [upload.name for upload in fake.uploads] == ["Kế hoạch.md", "Ghi chú của người.md"]
    assert fake.sent == []


@pytest.mark.parametrize("kind", ["code", "markdown"])
@pytest.mark.parametrize(
    "source",
    [
        "workspace:default/notes/key",
        "workspace:default/.env",
        "workspace:default/secrets.env",
        "workspace:coach/keys/id_rsa.PEM",
    ],
)
async def test_a_canvas_imported_from_a_file_no_reply_could_send_is_not_sent(
    crew, fake, source, kind
):
    """`kind: code` imports any text file, a key file among them. Its suffix names neither a
    format a `FILE:` line sends nor a kind of canvas, so the canvas made from it stays."""
    art = imported(crew.store, source, kind)
    await crew.outbound().send(f"FILE: artifact:{art}")
    assert fake.sent == [texts.TELEGRAM_CANVAS_SOURCE.format(id=art)]
    assert fake.uploads == []


@pytest.mark.parametrize(
    "source",
    [
        "workspace:default/a.py",
        "workspace:default/a.csv",
        "workspace:default/Báo cáo.PDF",
        "workspace:default/notes/plan.MD",
        "https://example.com/notes/key",
        "",
    ],
)
async def test_a_canvas_imported_from_a_file_of_a_known_kind_or_a_link_is_sent(crew, fake, source):
    """A suffix a `FILE:` line would send, a suffix that names a kind of canvas, a link, and
    a canvas that was never imported."""
    art = imported(crew.store, source)
    await crew.outbound().send(f"FILE: artifact:{art}")
    assert [(upload.name, upload.data) for upload in fake.uploads] == [("Nhập.txt", b"x = 1\n")]
    assert fake.sent == []


async def test_a_picture_is_sent_whatever_its_file_was_called(crew, fake):
    """Importing a picture takes only bytes that are one, so its name guards nothing."""
    store = crew.store
    art = store.artifacts.create(
        "Ảnh chụp", "image", "", USER, "", None, PNG, "", "workspace:default/shots/latest"
    ).id
    await crew.outbound().send(f"MEDIA: artifact:{art}")
    assert [(upload.method, upload.data) for upload in fake.uploads] == [("sendPhoto", PNG)]
    assert fake.sent == []


async def test_reach_is_checked_before_where_a_canvas_came_from(crew, fake):
    """The sentence about a source would say that the canvas exists."""
    store = crew.store
    art = imported(store, "workspace:ledger/notes/key", agent_id="ledger")
    await crew.outbound("coach").send(f"FILE: artifact:{art}")
    assert fake.sent == [missing(art)] and fake.uploads == []
