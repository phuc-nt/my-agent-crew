"""The push key and the subscriptions, kept in the home across restarts."""

from __future__ import annotations

import stat

from my_agent_crew.webpush.store import FILE_NAME, MAX_SUBSCRIPTIONS, PushStore, Subscription


def sub(n: int, auth: str = "a") -> Subscription:
    return Subscription(f"https://push.example/{n}", "p", auth, "https://crew.example")


def test_the_key_is_made_once_and_kept(tmp_path):
    first = PushStore(tmp_path).public_key()
    assert PushStore(tmp_path).public_key() == first
    mode = stat.S_IMODE((tmp_path / FILE_NAME).stat().st_mode)
    assert mode == 0o600


def test_a_device_subscribing_again_replaces_its_row(tmp_path):
    store = PushStore(tmp_path)
    store.add(sub(1))
    store.add(sub(2))
    store.add(sub(1, auth="b"))
    rows = store.subscriptions()
    assert [r.endpoint for r in rows] == ["https://push.example/2", "https://push.example/1"]
    assert rows[1].auth == "b" and rows[1].added_at


def test_subscriptions_keep_the_key_and_the_newest_past_the_cap(tmp_path):
    store = PushStore(tmp_path)
    key = store.public_key()
    for n in range(MAX_SUBSCRIPTIONS + 3):
        store.add(sub(n))
    rows = PushStore(tmp_path).subscriptions()
    assert len(rows) == MAX_SUBSCRIPTIONS
    assert rows[-1].endpoint.endswith(f"/{MAX_SUBSCRIPTIONS + 2}")
    assert PushStore(tmp_path).public_key() == key


def test_a_removed_subscription_is_gone_and_a_second_removal_says_so(tmp_path):
    store = PushStore(tmp_path)
    store.add(sub(1))
    assert store.remove("https://push.example/1") is True
    assert store.remove("https://push.example/1") is False
    assert store.subscriptions() == []


def test_an_unreadable_file_starts_over(tmp_path):
    (tmp_path / FILE_NAME).write_text("{not json")
    store = PushStore(tmp_path)
    assert store.subscriptions() == []
    assert store.public_key()
