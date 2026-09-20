"""The memory the agent reads is the memory the person can edit, over HTTP."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import Route
from my_agent_crew.memory import agent_store, user_store
from my_agent_crew.server import create_app
from my_agent_crew.store.memory_proposals import AGENT_MEMORY, USER_FACT, USER_FORGET

FACT = {"description": "Ngủ trước 23h", "type": "preference", "body": "Ngủ sớm mỗi ngày."}


@pytest.fixture
def deps(deps_factory):
    return deps_factory(routes=(Route("fake", "echo"),))


@pytest.fixture
def client(deps):
    with TestClient(create_app(deps, schedule=False)) as c:
        yield c


# --- the shared user scope ---------------------------------------------------------------


def test_user_memory_starts_empty_and_user_md_round_trips(client):
    body = client.get("/api/memory/user").json()
    assert body == {"user_md": "", "facts": [], "index_md": ""}

    saved = client.put("/api/memory/user", json={"user_md": "Phúc, làm sản phẩm."})
    assert saved.status_code == 200 and saved.json()["user_md"] == "Phúc, làm sản phẩm."
    assert client.get("/api/memory/user").json()["user_md"] == "Phúc, làm sản phẩm."


def test_a_fact_written_from_the_web_says_so(client, deps):
    body = client.put("/api/memory/user/facts/ngu-som", json=FACT).json()
    assert body["name"] == "ngu-som" and body["written_by"] == "web" and body["source"] == "web"

    listed = client.get("/api/memory/user").json()
    assert [f["name"] for f in listed["facts"]] == ["ngu-som"]
    assert "ngu-som.md" in listed["index_md"]
    assert user_store.list_facts(deps.settings.user_dir)[0].body == FACT["body"]


def test_saving_the_same_name_updates_in_place(client):
    client.put("/api/memory/user/facts/ngu-som", json=FACT)
    client.put("/api/memory/user/facts/ngu-som", json={**FACT, "body": "Đổi ý: 22h."})

    facts = client.get("/api/memory/user").json()["facts"]
    assert len(facts) == 1 and facts[0]["body"] == "Đổi ý: 22h."


def test_deleting_a_fact_removes_it_from_the_index(client):
    client.put("/api/memory/user/facts/ngu-som", json=FACT)
    assert client.delete("/api/memory/user/facts/ngu-som").status_code == 204

    body = client.get("/api/memory/user").json()
    assert body["facts"] == [] and "ngu-som" not in body["index_md"]


def test_deleting_a_fact_that_was_never_there_is_a_404(client):
    assert client.delete("/api/memory/user/facts/khong-co").status_code == 404


@pytest.mark.parametrize("name", ["Ngu Som", "ngu_som", "a" * 61])
def test_a_name_that_is_not_a_slug_is_refused(client, name):
    """The name becomes a file name, so the API must refuse anything but a slug."""
    assert client.put(f"/api/memory/user/facts/{name}", json=FACT).status_code == 422
    assert client.delete(f"/api/memory/user/facts/{name}").status_code == 422


def test_a_name_that_walks_out_of_the_folder_never_reaches_the_handler(client, deps):
    """A slash makes it a different path, so routing refuses it before any write happens."""
    assert client.put("/api/memory/user/facts/../escape", json=FACT).status_code == 405
    assert not (deps.settings.user_dir.parent / "escape.md").exists()


def test_an_unknown_fact_type_is_refused(client):
    assert (
        client.put("/api/memory/user/facts/x", json={**FACT, "type": "gossip"}).status_code == 422
    )


# --- one agent's own memory --------------------------------------------------------------


def test_agent_memory_round_trips(client, deps):
    agent_id = deps.profile.id
    assert client.get(f"/api/agents/{agent_id}/memory").json() == {
        "memory_md": "",
        "notes": [],
        "note_count": 0,
    }

    body = client.put(f"/api/agents/{agent_id}/memory", json={"memory_md": "Sếp thích trà."}).json()
    assert body["memory_md"] == "Sếp thích trà."
    assert deps.profile.memory_file.read_text(encoding="utf-8") == "Sếp thích trà."


def test_notes_are_listed_newest_first_and_round_trip(client, deps):
    agent_id = deps.profile.id
    for day, text in (("2026-09-18", "cũ"), ("2026-09-20", "mới")):
        client.put(f"/api/agents/{agent_id}/memory/notes/{day}", json={"body": text})

    listed = client.get(f"/api/agents/{agent_id}/memory").json()
    assert [n["day"] for n in listed["notes"]] == ["2026-09-20", "2026-09-18"]
    assert listed["note_count"] == 2

    note = client.get(f"/api/agents/{agent_id}/memory/notes/2026-09-20").json()
    assert note == {"day": "2026-09-20", "body": "mới"}


@pytest.mark.parametrize("day", ["hom-nay", "2026-9-20", "2026-09-20.md"])
def test_a_day_that_is_not_a_date_is_refused(client, deps, day):
    agent_id = deps.profile.id
    assert client.get(f"/api/agents/{agent_id}/memory/notes/{day}").status_code == 422
    put = client.put(f"/api/agents/{agent_id}/memory/notes/{day}", json={"body": "x"})
    assert put.status_code == 422


def test_an_unknown_agent_is_a_404(client):
    assert client.get("/api/agents/nobody/memory").status_code == 404
    assert client.put("/api/agents/nobody/memory", json={"memory_md": "x"}).status_code == 404
    assert client.get("/api/agents/nobody/memory/notes/2026-09-20").status_code == 404


# --- search ------------------------------------------------------------------------------


def test_search_spans_both_scopes_and_labels_each_hit(client, deps):
    client.put("/api/memory/user/facts/ca-phe", json={**FACT, "description": "Thích cà phê"})
    client.put(
        f"/api/agents/{deps.profile.id}/memory", json={"memory_md": "- Sếp thích cà phê sữa"}
    )

    hits = client.get("/api/memory/search", params={"q": "cà phê"}).json()["hits"]
    assert [h["scope"] for h in hits] == ["user", "agent"]
    assert hits[0]["file"] == "user/ca-phe.md" and hits[0]["agent_id"] == ""
    assert hits[1]["agent_id"] == deps.profile.id and hits[1]["file"] == "MEMORY.md"


def test_search_can_be_narrowed_to_one_agent(client, deps):
    client.put("/api/memory/user/facts/ca-phe", json={**FACT, "description": "Thích cà phê"})
    client.put(f"/api/agents/{deps.profile.id}/memory", json={"memory_md": "- cà phê sữa"})

    hits = client.get(
        "/api/memory/search", params={"q": "cà phê", "agent_id": deps.profile.id}
    ).json()["hits"]
    assert [h["scope"] for h in hits] == ["user", "agent"]


def test_an_empty_query_returns_nothing_rather_than_everything(client):
    assert client.get("/api/memory/search", params={"q": "  "}).json()["hits"] == []


def test_searching_an_unknown_agent_is_a_404(client):
    assert (
        client.get("/api/memory/search", params={"q": "x", "agent_id": "nobody"}).status_code == 404
    )


# --- proposals ---------------------------------------------------------------------------


def test_approving_a_proposal_writes_the_fact(client, deps):
    proposal = deps.store.proposals.create(
        agent_id=deps.profile.id, kind=USER_FACT, name="ngu-som", body="Ngủ sớm.", type="preference"
    )

    listed = client.get("/api/memory/proposals").json()["proposals"]
    assert [p["id"] for p in listed] == [proposal.id]

    decided = client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": True})
    assert decided.status_code == 200 and decided.json()["status"] == "approved"
    assert [f["name"] for f in client.get("/api/memory/user").json()["facts"]] == ["ngu-som"]
    assert client.get("/api/memory/proposals").json()["proposals"] == []


def test_rejecting_a_proposal_writes_nothing(client, deps):
    proposal = deps.store.proposals.create(
        agent_id=deps.profile.id, kind=USER_FACT, name="ngu-som", body="Ngủ sớm.", type="preference"
    )

    decided = client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": False})
    assert decided.json()["status"] == "rejected"
    assert client.get("/api/memory/user").json()["facts"] == []


def test_approving_an_agent_memory_proposal_appends_to_that_agents_file(client, deps):
    proposal = deps.store.proposals.create(
        agent_id=deps.profile.id, kind=AGENT_MEMORY, body="Đã xong vòng 1."
    )

    client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": True})
    assert (
        "Đã xong vòng 1." in client.get(f"/api/agents/{deps.profile.id}/memory").json()["memory_md"]
    )


def test_approving_a_forget_removes_the_fact(client, deps):
    client.put("/api/memory/user/facts/ngu-som", json=FACT)
    proposal = deps.store.proposals.create(
        agent_id=deps.profile.id, kind=USER_FORGET, name="ngu-som"
    )

    client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": True})
    assert client.get("/api/memory/user").json()["facts"] == []


def test_deciding_the_same_proposal_twice_is_a_conflict(client, deps):
    """A double click must not apply the same write again."""
    proposal = deps.store.proposals.create(
        agent_id=deps.profile.id, kind=USER_FACT, name="ngu-som", body="x", type="preference"
    )
    client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": True})

    again = client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": True})
    assert again.status_code == 409


def test_deciding_a_proposal_that_does_not_exist_is_a_404(client):
    assert client.post("/api/memory/proposals/nope", json={"approve": True}).status_code == 404


def test_resolved_proposals_are_still_listable_for_the_record(client, deps):
    proposal = deps.store.proposals.create(
        agent_id=deps.profile.id, kind=USER_FACT, name="ngu-som", body="x", type="preference"
    )
    client.post(f"/api/memory/proposals/{proposal.id}", json={"approve": False})

    all_of_them = client.get("/api/memory/proposals", params={"status": "all"}).json()["proposals"]
    assert [p["status"] for p in all_of_them] == ["rejected"]


# --- what the rest of the UI needs -------------------------------------------------------


def test_stats_carries_the_pending_count_for_the_tab_badge(client, deps):
    assert client.get("/api/stats").json()["pending_proposals"] == 0

    deps.store.proposals.create(agent_id=deps.profile.id, kind=USER_FACT, name="x", body="y")
    assert client.get("/api/stats").json()["pending_proposals"] == 1


def test_settings_points_at_the_shared_user_directory(client, deps):
    assert client.get("/api/settings").json()["users_dir"] == str(deps.settings.users_dir)


# --- consolidation over HTTP -------------------------------------------------------------


def test_asking_for_a_consolidation_returns_at_once_and_runs_it(client, deps):
    """The rewrite can take a model call, so the request does not wait for it."""
    agent_store.write_memory_md(deps.agent.memory_file, "- Sep thich tra.")
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Sep ngu truoc 23h.")
    stamp = deps.agent.memory_file.stat().st_mtime + 10
    os.utime(deps.agent.memory_dir / "2026-09-19.md", (stamp, stamp))

    response = client.post(f"/api/agents/{deps.agent.id}/memory/consolidate")
    assert response.status_code == 202
    assert response.json()["agent_id"] == deps.agent.id


def test_a_second_consolidation_while_one_runs_is_a_conflict(client, deps):
    app_state = client.app.state.runtime
    app_state.consolidating.add(deps.agent.id)
    assert client.post(f"/api/agents/{deps.agent.id}/memory/consolidate").status_code == 409


def test_consolidating_an_unknown_agent_is_a_404(client):
    assert client.post("/api/agents/nobody/memory/consolidate").status_code == 404
