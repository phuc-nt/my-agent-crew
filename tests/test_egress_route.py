"""`GET /api/activity/egress`: the hosts called over a window of days, most called first,
current to the last call, and saying which ways out it cannot see."""

from __future__ import annotations

from datetime import timedelta

from my_agent_crew.egress import COUNTER


def day(app, ago: int = 0) -> str:
    return (app.runtime.settings.today() - timedelta(days=ago)).isoformat()


async def test_the_report_adds_up_the_window_and_sorts_by_calls_then_host(served):
    app = served([])
    counts = {
        (day(app), "b.test"): 3,
        (day(app, 2), "b.test"): 2,
        (day(app, 6), "a.test"): 5,
        (day(app, 1), "c.test"): 5,
        (day(app, 7), "old.test"): 9,
        (day(app, 7), "b.test"): 40,
    }
    app.runtime.store.egress.add(counts, day(app))

    answer = await app.client.get("/api/activity/egress")

    assert answer.status_code == 200
    assert answer.json() == {
        "days": 7,
        "since": day(app, 6),
        "hosts": [
            {"host": "a.test", "calls": 5, "days": 1, "last_day": day(app, 6)},
            {"host": "b.test", "calls": 5, "days": 2, "last_day": day(app)},
            {"host": "c.test", "calls": 5, "days": 1, "last_day": day(app, 1)},
        ],
        "not_seen": ["shell", "hooks"],
    }


async def test_days_widens_and_narrows_the_window_and_is_refused_outside_its_bounds(served):
    app = served([])
    app.runtime.store.egress.add({(day(app), "a.test"): 1, (day(app, 89), "far.test"): 2}, day(app))

    one = (await app.client.get("/api/activity/egress", params={"days": 1})).json()
    widest = (await app.client.get("/api/activity/egress", params={"days": 90})).json()

    assert (one["days"], one["since"]) == (1, day(app))
    assert [row["host"] for row in one["hosts"]] == ["a.test"]
    assert (widest["days"], widest["since"]) == (90, day(app, 89))
    assert [row["host"] for row in widest["hosts"]] == ["far.test", "a.test"]
    for outside in (0, 91, -1, "x"):
        refused = await app.client.get("/api/activity/egress", params={"days": outside})
        assert refused.status_code == 422


async def test_the_report_holds_a_call_made_a_moment_ago(served):
    app = served([])
    try:
        COUNTER.count("Fresh.Test")
        COUNTER.count("not a host/with?path")

        hosts = (await app.client.get("/api/activity/egress")).json()["hosts"]

        assert hosts == [
            {"host": "fresh.test", "calls": 1, "days": 1, "last_day": day(app)},
            {"host": "invalid", "calls": 1, "days": 1, "last_day": day(app)},
        ]
    finally:
        COUNTER.unbind(app.runtime.store.egress.add)


async def test_a_crew_that_called_nothing_reports_no_host(served):
    app = served([])
    data = (await app.client.get("/api/activity/egress")).json()
    assert data["hosts"] == [] and data["not_seen"] == ["shell", "hooks"]
