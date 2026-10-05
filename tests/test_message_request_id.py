"""A send named by its sender is taken once (`Inbound.repeated`, `routes_chat.py`): made
again under the same name, by a sender that never heard the first answer, it starts no
second turn and stores no second message. The repeat is shown what became of the first:
its place in line while it still waits, otherwise the conversation as it stands and the
turn under way. A name is used up only by a message that was taken: one a refusal turned
away, or Stop withdrew from the queue, can be sent again under it."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.inbound import Inbound
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message
from my_agent_crew.server.routes_turn import sse_frames
from my_agent_crew.store.queue import QUEUE_LIMIT
from tests.canvas_helpers import PLAN, persons_canvas
from tests.queue_helpers import Served, settle_loop, until
from tests.test_hosted_turns_api import GUARDED, WORK, history, kinds, rest, shown
from tests.test_server_api import parse_sse

NAME = "send-0001"
OTHER = "send-0002"


def send(app: Served, text: str, name: str = NAME, **more: Any) -> Any:
    return app.client.post(app.messages, json={"text": text, "request_id": name, **more})


async def heard(response: Any) -> list[dict[str, Any]]:
    answered: httpx.Response = await asyncio.wait_for(response, 2)
    assert answered.status_code == 200, answered.text
    return parse_sse(answered.text)


def said(app: Served) -> list[str]:
    return [content for role, content in history(app) if role == "user"]


async def test_a_send_made_again_while_its_turn_runs_joins_that_turn(served):
    app = served(WORK)
    first = asyncio.create_task(send(app, "làm đi"))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    again = asyncio.create_task(send(app, "làm đi"))
    await settle_loop()
    assert app.runtime.store.queue.count(app.conv.id) == 0  # not a second message in line
    app.slow.release.set()
    assert kinds(await heard(first))[-1] == "done"
    opening, *followed = await heard(again)
    assert (opening["type"], opening["running"]) == ("watching", True)
    assert shown(opening["detail"])[0] == ("user", "làm đi")
    assert kinds(followed)[-2:] == ["assistant_message", "done"]
    await until(lambda: app.statuses() == ["done"])
    assert said(app) == ["làm đi"] and app.slow.runs == 1


async def test_a_send_made_again_after_its_turn_ended_starts_nothing(served):
    app = served([completion("xin chào")])
    assert kinds(await heard(send(app, "chào")))[-1] == "done"
    [opening] = await heard(send(app, "chào"))
    assert (opening["type"], opening["running"]) == ("watching", False)
    assert shown(opening["detail"]) == [("user", "chào"), ("assistant", "xin chào")]
    assert app.statuses() == ["done"] and said(app) == ["chào"]
    assert not app.runtime.hub.busy.busy(app.conv.id)


async def test_a_send_made_again_while_it_waits_keeps_its_one_place_in_line(served):
    app = served([*WORK, completion("trả lời 2")])
    first = asyncio.create_task(app.client.post(app.messages, json={"text": "việc 1"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    [queued] = await heard(send(app, "tin 2"))
    [behind] = await heard(send(app, "tin 3", OTHER))
    assert (queued["type"], queued["position"], behind["position"]) == ("queued", 1, 2)
    assert await heard(send(app, "tin 2")) == [queued]
    assert await heard(send(app, "tin 3", OTHER)) == [behind]
    assert [i.text for i in app.runtime.store.queue.peek_all(app.conv.id)] == ["tin 2", "tin 3"]

    app.slow.release.set()
    assert kinds(await heard(first))[-1] == "done"
    await until(lambda: app.statuses() == ["done", "done"])
    # Delivered: each of the sends the one message came from is known to have been taken.
    for name in (NAME, OTHER):
        [opening] = await heard(send(app, "tin 2", name))
        assert (opening["type"], opening["running"]) == ("watching", False)
    assert said(app) == ["việc 1", "tin 2\n\ntin 3"]
    assert app.runtime.store.queue.count(app.conv.id) == 0


async def test_a_message_stop_withdrew_can_be_sent_again_under_its_name(served):
    app = served(WORK)
    first = asyncio.create_task(app.client.post(app.messages, json={"text": "việc 1"}))
    await asyncio.wait_for(app.slow.started.wait(), 2)
    assert kinds(await heard(send(app, "tin 2"))) == ["queued"]
    stopped = (await app.client.post(app.stop)).json()
    assert [c["text"] for c in stopped["cleared"]] == ["tin 2"] and stopped["cancelled"]
    await asyncio.gather(first, return_exceptions=True)
    await until(lambda: app.statuses() == ["error"])
    # Nothing of it reached the log, so the person sending it again is a new send.
    assert kinds(await heard(send(app, "tin 2")))[-1] == "done"
    assert said(app) == ["việc 1", "tin 2"]


async def test_a_turn_stopped_before_its_first_step_leaves_its_name_unused(served):
    app = served([completion("xin chào")])
    inbound = app.runtime.inbound
    inbound.stream_hosted(app.conv.id, "chào", NAME)
    assert inbound.host.cancel(app.conv.id)  # Stop, in the same step: nothing was stored
    await settle_loop()
    assert history(app) == [] and inbound.repeated(app.conv.id, NAME) is None
    # And the turn that never began is not left there for a tab to watch for ever.
    assert app.runtime.hub.turns.join(app.conv.id) is None


async def test_a_send_refused_while_a_decision_is_awaited_leaves_its_name_unused(served):
    app = served([completion(tool_calls=[GUARDED]), completion("xong"), completion("nghe rồi")])
    *_, pause = await heard(app.client.post(app.messages, json={"text": "làm đi"}))
    assert pause["type"] == "approval_required"
    assert (await send(app, "tin")).status_code == 409
    url = f"{app.detail}/approvals/{pause['approval_id']}"
    assert kinds(await heard(app.client.post(url, json={"approve": True})))[-1] == "done"
    assert kinds(await heard(send(app, "tin")))[-1] == "done"
    assert said(app) == ["làm đi", "tin"]


async def test_a_send_refused_by_a_full_queue_leaves_its_name_unused(served):
    app = served([completion("nghe rồi")])
    app.runtime.hub.busy.claim(app.conv.id)
    for n in range(QUEUE_LIMIT):
        assert (await app.client.post(app.messages, json={"text": f"tin {n}"})).status_code == 200
    assert (await send(app, "thừa")).status_code == 429
    app.runtime.store.queue.take_all(app.conv.id)
    app.runtime.hub.busy.release(app.conv.id)
    assert kinds(await heard(send(app, "thừa")))[-1] == "done"
    assert said(app) == ["thừa"]


async def test_sends_with_no_name_are_each_a_send_of_their_own(served):
    app = served([completion("một"), completion("hai"), completion("ba")])
    for name in ("", ""):
        assert kinds(await heard(send(app, "chào", name)))[-1] == "done"
    assert kinds(await heard(app.client.post(app.messages, json={"text": "chào"})))[-1] == "done"
    assert said(app) == ["chào", "chào", "chào"]


async def test_a_name_is_its_own_conversations(served):
    app = served([completion("một"), completion("hai")])
    other = app.runtime.store.create("Cuộc khác", agent_id=app.conv.agent_id)
    assert kinds(await heard(send(app, "chào")))[-1] == "done"
    there = app.client.post(
        f"/api/conversations/{other.id}/messages", json={"text": "chào", "request_id": NAME}
    )
    assert kinds(await heard(there))[-1] == "done"
    assert [m.message.content for m in app.runtime.store.history(other.id)] == ["chào", "hai"]
    missing = await app.client.post(
        "/api/conversations/nope/messages", json={"text": "chào", "request_id": NAME}
    )
    assert (missing.status_code, missing.json()["detail"]) == (404, "conversation not found")


@pytest.mark.parametrize("name", ["có dấu", "a b", "a/b", "x" * 65])
async def test_a_name_that_is_not_a_plain_token_is_refused(served, name):
    app = served([completion("xin chào")])
    assert (await send(app, "chào", name)).status_code == 422
    assert history(app) == [] and app.statuses() == []


async def test_a_name_may_be_sixty_four_characters(served):
    app = served([completion("xin chào")])
    name = "aZ09_-" * 10 + "abcd"
    assert kinds(await heard(send(app, "chào", name)))[-1] == "done"
    assert kinds(await heard(send(app, "chào", name))) == ["watching"]


async def test_the_same_send_twice_before_the_turn_takes_a_step_is_one_turn(served):
    app = served([completion("xin chào")])
    inbound = app.runtime.inbound
    first = inbound.stream_hosted(app.conv.id, "chào", NAME)
    # Same step of the loop: the turn has stored nothing yet, and is known all the same.
    again = inbound.repeated(app.conv.id, NAME)
    assert history(app) == [] and again is not None
    assert inbound.repeated(app.conv.id, OTHER) is None
    followed = await rest(sse_frames(app.runtime.default, app.conv.id, again))
    assert followed[0]["type"] == "watching" and kinds(followed)[-1] == "done"
    assert kinds(await rest(sse_frames(app.runtime.default, app.conv.id, first)))[-1] == "done"
    await until(lambda: app.statuses() == ["done"])
    assert said(app) == ["chào"]
    # The turn is over and no longer answers for the name; the log does.
    await until(lambda: not inbound.host.answering(app.conv.id, NAME))
    assert inbound.repeated(app.conv.id, NAME) is not None


async def test_a_send_is_known_to_a_server_started_afterwards(served):
    app = served([completion("xin chào")])
    assert kinds(await heard(send(app, "chào")))[-1] == "done"
    restarted = Inbound(app.runtime.inbound.agents, ActivityHub(app.runtime.store))
    again = restarted.repeated(app.conv.id, NAME)
    assert again is not None
    [opening] = await rest(sse_frames(app.runtime.default, app.conv.id, again))
    assert (opening["type"], opening["running"]) == ("watching", False)
    assert restarted.repeated(app.conv.id, OTHER) is None


async def test_a_send_made_again_while_its_call_waits_for_a_decision_shows_the_wait(served):
    app = served([completion(tool_calls=[GUARDED]), completion("xong")])
    *_, pause = await heard(send(app, "làm đi"))
    assert pause["type"] == "approval_required"
    [opening] = await heard(send(app, "làm đi"))  # not the 409 a new message would get
    assert (opening["type"], opening["running"]) == ("watching", False)
    assert opening["detail"]["pending_approval"]["id"] == pause["approval_id"]
    assert said(app) == ["làm đi"] and app.guarded.runs == 0


async def test_a_send_made_again_leaves_the_open_canvas_as_it_is(served):
    app = served([completion("xin chào")])
    store = app.runtime.store
    art = persons_canvas(store, PLAN)
    opened = {"artifact_id": art, "selection": None}
    assert kinds(await heard(send(app, "chào", canvas=opened)))[-1] == "done"
    assert store.artifact_links.focus(app.conv.id).artifact_id == art
    closed = {"artifact_id": None, "selection": None}
    assert (await app.client.put(f"{app.detail}/canvas", json=closed)).status_code == 200
    # The repeat carries what the tab had open when it first sent: old news by now.
    assert kinds(await heard(send(app, "chào", canvas=opened))) == ["watching"]
    assert store.artifact_links.focus(app.conv.id) is None
    # A selection a new message would be refused for is not looked at either.
    unfit = {"version": 9, "text": "chạy 5 km", "line_start": 2, "line_end": 2}
    picked = {"artifact_id": art, "selection": unfit}
    assert (await send(app, "khác", OTHER, canvas=picked)).status_code == 422
    assert kinds(await heard(send(app, "chào", canvas=picked))) == ["watching"]
    assert said(app) == ["chào"]


def test_a_name_is_stored_with_its_message_or_not_at_all(store):
    conv = store.create()
    said = Message(role="user", content="chào")
    store.append(conv.id, said, request_id=NAME)
    assert store.messages.took(conv.id, NAME) and not store.messages.took(conv.id, OTHER)
    assert not store.messages.took(store.create().id, NAME)
    # A message that could not be written leaves no name behind to turn its sender away.
    with pytest.raises(KeyError):
        store.append("gone", said, request_id=NAME)
    assert not store.messages.took("gone", NAME)
    # A nameless message, and the loop's own, store none.
    store.append(conv.id, said)
    store.append(conv.id, Message(role="assistant", content="xin chào"))
    rows = store.messages._conn.execute("SELECT request_id FROM message_requests").fetchall()
    assert [row[0] for row in rows] == [NAME]


def test_deleting_a_conversation_forgets_the_sends_it_took(store):
    conv, kept = store.create(), store.create()
    for owner in (conv, kept):
        store.append(owner.id, Message(role="user", content="chào"), request_id=NAME)
    store.delete(conv.id)
    assert not store.messages.took(conv.id, NAME) and store.messages.took(kept.id, NAME)
