"""The queue a busy conversation's messages wait in: order, the limit, and handing over as
one transaction with the message log."""

from __future__ import annotations

import pytest

from my_agent_crew import texts
from my_agent_crew.store import Store
from my_agent_crew.store.queue import FOLLOW_UP, QUEUE_LIMIT, STEER, QueueFull


def user_messages(store: Store, conv_id: str) -> list[str]:
    return [m.message.content for m in store.history(conv_id) if m.message.role == "user"]


def test_add_returns_places_in_line_and_refuses_past_the_limit(store: Store):
    conv = store.create()
    first, position = store.queue.add(conv.id, FOLLOW_UP, "một", "chat")
    assert (first.kind, first.text, first.source, position) == (FOLLOW_UP, "một", "chat", 1)
    assert store.queue.add(conv.id, STEER, "hai", "web")[1] == 2
    for n in range(3, QUEUE_LIMIT + 1):
        store.queue.add(conv.id, FOLLOW_UP, str(n), "chat")
    with pytest.raises(QueueFull) as full:
        store.queue.add(conv.id, FOLLOW_UP, "thừa", "chat")
    assert str(full.value) == texts.QUEUE_FULL.format(limit=QUEUE_LIMIT)
    assert store.queue.count(conv.id) == QUEUE_LIMIT
    # The limit is per conversation.
    assert store.queue.add(store.create().id, FOLLOW_UP, "khác", "chat")[1] == 1


def test_peek_all_keeps_the_order_and_takes_nothing(store: Store):
    conv = store.create()
    for text in ("a", "b", "c"):
        store.queue.add(conv.id, FOLLOW_UP, text, "chat")
    assert [i.text for i in store.queue.peek_all(conv.id)] == ["a", "b", "c"]
    assert [i.to_dict()["text"] for i in store.queue.peek_all(conv.id)] == ["a", "b", "c"]
    assert set(store.queue.peek_all(conv.id)[0].to_dict()) == {"id", "kind", "text"}


def test_deliver_moves_the_rows_into_one_user_message_in_line_order(store: Store):
    conv = store.create()
    ids = [store.queue.add(conv.id, FOLLOW_UP, text, "chat")[0].id for text in ("a", "b", "c")]
    delivered = store.queue.deliver(conv.id, list(reversed(ids)))
    assert [i.text for i in delivered] == ["a", "b", "c"]
    assert store.queue.count(conv.id) == 0
    assert user_messages(store, conv.id) == ["a\n\nb\n\nc"]


def test_deliver_takes_only_the_rows_it_names(store: Store):
    conv = store.create()
    a = store.queue.add(conv.id, FOLLOW_UP, "a", "chat")[0]
    store.queue.add(conv.id, FOLLOW_UP, "b", "chat")
    assert [i.text for i in store.queue.deliver(conv.id, [a.id])] == ["a"]
    assert [i.text for i in store.queue.peek_all(conv.id)] == ["b"]
    # Another conversation's row is not this one's to deliver.
    other = store.create()
    theirs = store.queue.add(other.id, FOLLOW_UP, "x", "chat")[0]
    assert store.queue.deliver(conv.id, [theirs.id]) == []
    assert store.queue.count(other.id) == 1 and user_messages(store, conv.id) == ["a"]


def test_deliver_that_cannot_write_the_message_keeps_the_rows(
    store: Store, monkeypatch: pytest.MonkeyPatch
):
    conv = store.create()
    ids = [store.queue.add(conv.id, FOLLOW_UP, text, "chat")[0].id for text in ("a", "b")]

    def broken(*args, **kwargs):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(store.messages, "append", broken)
    with pytest.raises(RuntimeError):
        store.queue.deliver(conv.id, ids)
    monkeypatch.undo()
    assert [i.text for i in store.queue.peek_all(conv.id)] == ["a", "b"]
    assert user_messages(store, conv.id) == []
    # The rollback left the store usable: the same rows deliver on the next try.
    assert [i.text for i in store.queue.deliver(conv.id, ids)] == ["a", "b"]


def test_deliver_to_a_conversation_that_is_gone_keeps_the_rows(store: Store):
    ids = [store.queue.add("gone", FOLLOW_UP, "a", "chat")[0].id]
    with pytest.raises(KeyError):
        store.queue.deliver("gone", ids)
    assert store.queue.count("gone") == 1


def test_deliver_after_the_rows_were_taken_delivers_nothing(store: Store):
    conv = store.create()
    ids = [store.queue.add(conv.id, FOLLOW_UP, "a", "chat")[0].id]
    assert [i.text for i in store.queue.take_all(conv.id)] == ["a"]
    assert store.queue.deliver(conv.id, ids) == [] and store.queue.deliver(conv.id, []) == []
    assert user_messages(store, conv.id) == []


def test_take_steers_takes_only_the_steers(store: Store):
    conv = store.create()
    store.queue.add(conv.id, FOLLOW_UP, "sau", "chat")
    store.queue.add(conv.id, STEER, "rẽ 1", "chat")
    store.queue.add(conv.id, STEER, "rẽ 2", "chat")
    assert [i.text for i in store.queue.take_steers(conv.id)] == ["rẽ 1", "rẽ 2"]
    assert user_messages(store, conv.id) == ["rẽ 1\n\nrẽ 2"]
    assert [(i.kind, i.text) for i in store.queue.peek_all(conv.id)] == [(FOLLOW_UP, "sau")]
    assert store.queue.take_steers(conv.id) == []
    assert user_messages(store, conv.id) == ["rẽ 1\n\nrẽ 2"]


def test_take_all_empties_the_line_in_order_without_delivering(store: Store):
    conv = store.create()
    for kind, text in ((FOLLOW_UP, "a"), (STEER, "b"), (FOLLOW_UP, "c")):
        store.queue.add(conv.id, kind, text, "chat")
    assert [(i.kind, i.text) for i in store.queue.take_all(conv.id)] == [
        (FOLLOW_UP, "a"),
        (STEER, "b"),
        (FOLLOW_UP, "c"),
    ]
    assert store.queue.count(conv.id) == 0 and user_messages(store, conv.id) == []
    assert store.queue.take_all(conv.id) == []


def test_conversations_with_items_lists_the_longest_waiting_first(store: Store):
    early, late, empty = store.create(), store.create(), store.create()
    store.queue.add(late.id, FOLLOW_UP, "1", "chat")
    store.queue.add(early.id, FOLLOW_UP, "2", "chat")
    store.queue.add(late.id, FOLLOW_UP, "3", "chat")
    assert store.queue.conversations_with_items() == [late.id, early.id]
    store.queue.take_all(late.id)
    assert store.queue.conversations_with_items() == [early.id]
    assert empty.id not in store.queue.conversations_with_items()


def test_deleting_a_conversation_empties_its_line(store: Store):
    conv, kept = store.create(), store.create()
    store.queue.add(conv.id, FOLLOW_UP, "a", "chat")
    store.queue.add(kept.id, FOLLOW_UP, "b", "chat")
    store.delete(conv.id)
    assert store.queue.count(conv.id) == 0 and store.queue.count(kept.id) == 1


def test_the_queue_survives_a_restart(tmp_path):
    path = tmp_path / "agent.sqlite3"
    first = Store(path)
    conv = first.create()
    first.queue.add(conv.id, STEER, "còn chờ", "telegram")
    first.close()
    again = Store(path)
    [item] = again.queue.peek_all(conv.id)
    assert (item.kind, item.text, item.source) == (STEER, "còn chờ", "telegram")
    again.close()
