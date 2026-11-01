"""What each provider has cost: the ledger per provider, OpenRouter's own key report and
`GET /api/spend`, which the header polls."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from my_agent_crew.llm.types import Message
from my_agent_crew.server import create_app, provider_spend, routes_spend
from my_agent_crew.store import Store
from my_agent_crew.store.side_calls import SideCall

SAIGON = ZoneInfo("Asia/Ho_Chi_Minh")
KEY_INFO = {
    "data": {
        "label": "sk-or-v1-abc...",
        "usage": 12.5,
        "usage_daily": 0.4,
        "usage_weekly": 2,
        "usage_monthly": 6.25,
        "limit": 20,
        "limit_remaining": 7.5,
        "limit_reset": "monthly",
    }
}


@pytest.fixture(autouse=True)
def fresh_reports():
    provider_spend.forget_reports()
    yield
    provider_spend.forget_reports()


def billed(store: Store) -> Store:
    conv = store.create()

    def reply(stamp: str, provider: str, cost: float | None) -> None:
        msg = Message(role="assistant", content="ok")
        store.messages.append(conv.id, msg, stamp, provider, "m", cost, 10, 2)

    reply("2026-10-31T10:00:00+00:00", "anthropic", 9.0)  # last month in Saigon
    reply("2026-10-31T18:30:00+00:00", "anthropic", 0.5)  # 1 Nov, 01:30 in Saigon
    reply("2026-11-02T03:00:00+00:00", "anthropic", 0.25)
    reply("2026-11-02T04:00:00+00:00", "openrouter", None)
    store.side_calls.record(
        SideCall("a", "title", "openrouter", "m", 0.01), "2026-11-02T05:00:00+00:00"
    )
    return store


def test_by_provider_totals_only_the_calls_since_the_stamp(store: Store):
    totals = billed(store).usage.by_provider("2026-11-01T00:00:00+00:00")
    assert set(totals) == {"anthropic", "openrouter"}
    assert totals["anthropic"]["calls"] == 1 and totals["anthropic"]["cost_usd"] == 0.25
    assert totals["openrouter"]["calls"] == 2
    assert totals["openrouter"]["unknown_cost_calls"] == 1
    assert totals["openrouter"]["cost_usd"] == pytest.approx(0.01)


def test_ledger_rows_cut_month_and_day_in_the_persons_zone(store: Store):
    rows = provider_spend.ledger_rows(billed(store).usage, date(2026, 11, 2), SAIGON, [])
    assert [r["provider"] for r in rows] == ["anthropic", "openrouter"]
    claude, router = rows
    assert claude["month_usd"] == pytest.approx(0.75) and claude["today_usd"] == 0.25
    assert router == {
        "provider": "openrouter",
        "today_usd": 0.01,
        "month_usd": 0.01,
        "calls": 2,
        "unknown_cost_calls": 1,
    }


def test_a_provider_with_a_key_shows_before_its_first_call(store: Store):
    rows = provider_spend.ledger_rows(store.usage, date(2026, 11, 2), SAIGON, ["openrouter"])
    assert rows == [
        {
            "provider": "openrouter",
            "today_usd": 0.0,
            "month_usd": 0.0,
            "calls": 0,
            "unknown_cost_calls": 0,
        }
    ]


def client_answering(*replies: httpx.Response | Exception) -> tuple[httpx.AsyncClient, list]:
    seen: list[httpx.Request] = []
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


async def test_the_openrouter_report_keeps_the_money_fields():
    client, seen = client_answering(httpx.Response(200, json=KEY_INFO))
    report = await provider_spend.openrouter_report(client, "sk-test")
    assert report == {
        "usage": 12.5,
        "usage_daily": 0.4,
        "usage_weekly": 2.0,
        "usage_monthly": 6.25,
        "limit": 20.0,
        "limit_remaining": 7.5,
        "limit_reset": "monthly",
    }
    assert seen[0].headers["authorization"] == "Bearer sk-test"
    assert str(seen[0].url) == provider_spend.OPENROUTER_KEY_URL


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(401, json={"error": "no"}),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"data": "odd"}),
        httpx.ConnectError("down"),
    ],
)
async def test_a_report_that_cannot_be_read_is_none(answer):
    client, _ = client_answering(answer)
    assert await provider_spend.openrouter_report(client, "sk-test") is None


async def test_the_report_is_asked_once_a_minute():
    now = [100.0]
    client, seen = client_answering(
        httpx.Response(200, json=KEY_INFO), httpx.Response(200, json={"data": {"usage": 1}})
    )
    first = await provider_spend.cached_openrouter_report(client, "k", lambda: now[0])
    now[0] += provider_spend.REPORT_SECONDS - 1
    assert await provider_spend.cached_openrouter_report(client, "k", lambda: now[0]) == first
    now[0] += 1
    later = await provider_spend.cached_openrouter_report(client, "k", lambda: now[0])
    assert len(seen) == 2 and later is not None and later["usage"] == 1.0


def test_the_route_reports_the_ledger_and_openrouters_figures(deps_factory, monkeypatch):
    asked: list[str] = []

    async def report(client, key, clock=None):
        asked.append(key)
        return {"usage_monthly": 6.25}

    monkeypatch.setattr(provider_spend, "cached_openrouter_report", report)
    deps = deps_factory(openrouter_api_key="sk-or", anthropic_api_key="sk-ant")
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        body = client.get("/api/spend").json()
    today = deps.settings.today().isoformat()
    assert body["day"] == today and body["month"] == today[:7]
    assert [r["provider"] for r in body["providers"]] == ["anthropic", "openrouter"]
    assert body["openrouter"] == {"usage_monthly": 6.25}
    assert asked == ["sk-or"]


def test_without_an_openrouter_key_there_is_no_report(deps_factory):
    deps = deps_factory(openrouter_api_key=None, anthropic_api_key=None)
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        body = client.get("/api/spend").json()
    assert body["openrouter"] is None and body["providers"] == []
    assert routes_spend.router.routes[0].path == "/spend"
