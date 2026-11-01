"""The facts over HTTP: a hand edit stands as the person's word, versions are readable,
and a retract differs from a purge."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import Route
from my_agent_crew.memory import fact_recall, user_store
from my_agent_crew.server import create_app

FACT = {"description": "Thích trà", "type": "preference", "body": "Trà xanh"}


@pytest.fixture
def deps(deps_factory):
    return deps_factory(routes=(Route("fake", "echo"),))


@pytest.fixture
def client(deps):
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as c:
        yield c


def test_a_hand_edit_is_the_operators_word_and_carries_its_validity(client):
    body = client.put(
        "/api/memory/user/facts/do-uong", json={**FACT, "valid_until": "2099-01-01"}
    ).json()
    assert body["basis"] == "operator" and body["valid_until"] == "2099-01-01"

    bad = client.put("/api/memory/user/facts/do-uong", json={**FACT, "valid_from": "mai"})
    assert bad.status_code == 422


def test_the_listing_says_state_recalls_and_history(client, deps):
    user_dir = deps.settings.user_dir
    client.put("/api/memory/user/facts/do-uong", json=FACT)
    client.put("/api/memory/user/facts/do-uong", json={**FACT, "body": "Cà phê"})
    client.put("/api/memory/user/facts/sap-toi", json={**FACT, "valid_from": "2099-01-01"})
    fact_recall.bump(user_store.facts_dir(user_dir), ["do-uong"], datetime(2026, 9, 1))

    facts = {f["name"]: f for f in client.get("/api/memory/user").json()["facts"]}

    assert facts["do-uong"]["version"] == 2 and facts["do-uong"]["history_count"] == 1
    assert facts["do-uong"]["recalls"] == 1 and facts["do-uong"]["state"] == "current"
    assert facts["sap-toi"]["state"] == "pending" and facts["sap-toi"]["holds_today"] is None
    assert facts["do-uong"]["holds_today"] is None


def test_a_change_that_starts_later_shows_the_version_that_holds_today(client):
    client.put("/api/memory/user/facts/cong-ty", json={**FACT, "body": "Công ty A"})
    client.put(
        "/api/memory/user/facts/cong-ty",
        json={**FACT, "body": "Công ty B", "valid_from": "2099-01-01"},
    )

    (fact,) = client.get("/api/memory/user").json()["facts"]

    assert fact["state"] == "pending" and fact["body"] == "Công ty B"
    assert fact["holds_today"]["body"] == "Công ty A"
    assert fact["holds_today"]["valid_until"] == "2098-12-31"


def test_history_lists_the_versions_newest_first(client):
    client.put("/api/memory/user/facts/do-uong", json=FACT)
    client.put("/api/memory/user/facts/do-uong", json={**FACT, "body": "Cà phê"})
    client.put("/api/memory/user/facts/do-uong", json={**FACT, "body": "Nước lọc"})

    versions = client.get("/api/memory/user/facts/do-uong/history").json()["versions"]

    assert [v["body"] for v in versions] == ["Cà phê", "Trà xanh"]
    assert {v["why"] for v in versions} == {"superseded"}


def test_delete_retracts_and_purge_erases(client):
    client.put("/api/memory/user/facts/do-uong", json=FACT)

    assert client.delete("/api/memory/user/facts/do-uong").status_code == 204
    listed = client.get("/api/memory/user").json()
    assert listed["facts"] == [] and [r["name"] for r in listed["retracted"]] == ["do-uong"]
    assert client.delete("/api/memory/user/facts/do-uong").status_code == 404

    assert client.delete("/api/memory/user/facts/do-uong?purge=true").status_code == 204
    assert client.get("/api/memory/user").json()["retracted"] == []
    assert client.get("/api/memory/user/facts/do-uong/history").json()["versions"] == []
    assert client.delete("/api/memory/user/facts/do-uong?purge=true").status_code == 404
