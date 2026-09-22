"""The vault over HTTP: what the Wiki tab can read, change and start."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import Route
from my_agent_crew.memory import wiki_links, wiki_store
from my_agent_crew.memory.wiki_compile import JOB_SOURCE
from my_agent_crew.memory.wiki_store import Page
from my_agent_crew.server import create_app

LONG = "Hạn nộp hồ sơ là thứ tư, đã dời một lần từ thứ hai tuần trước, nhớ kỹ."


@pytest.fixture
def deps(deps_factory):
    return deps_factory(routes=(Route("fake", "echo"),))


@pytest.fixture
def app(deps):
    return create_app(deps, schedule=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def app_rt(app):
    return app.state.runtime


@pytest.fixture
def url(deps):
    return f"/api/agents/{deps.agent.id}/memory/wiki"


def page(deps, slug="han-eco", title="Hạn Eco", body=LONG, **kw):
    kw.setdefault("sources", ["note:x"])
    return wiki_store.write_page(
        deps.agent.memory_dir,
        Page(slug=slug, kind="entities", title=title, body=body, **kw),
    )


def test_an_empty_vault_is_an_empty_list_not_an_error(client, url):
    """An agent that has never compiled still has a Wiki tab, and it must open."""
    body = client.get(url).json()
    assert body == {"pages": [], "kinds": list(wiki_store.KINDS), "count": 0}


def test_the_list_is_a_table_of_contents_without_the_bodies(client, url, deps):
    """Sending every body would make opening the tab cost the whole vault."""
    page(deps)
    [listed] = client.get(url).json()["pages"]
    assert listed["slug"] == "han-eco" and listed["title"] == "Hạn Eco"
    assert "body" not in listed
    assert client.get(f"{url}/pages/han-eco").json()["body"] == LONG


def test_a_query_narrows_the_list_the_way_the_agent_would_search(client, url, deps):
    page(deps)
    page(deps, slug="so-sach", title="Sổ sách", body="Chuyện sổ sách hằng tháng, ghi cho đủ.")
    found = client.get(url, params={"q": "hồ sơ"}).json()
    assert [p["slug"] for p in found["pages"]] == ["han-eco"]


def test_a_missing_page_is_a_404_rather_than_an_empty_one(client, url):
    assert client.get(f"{url}/pages/khong-co").status_code == 404
    assert client.put(f"{url}/pages/khong-co", json={"body": "x"}).status_code == 404


def test_an_edit_changes_only_the_fields_that_were_sent(client, url, deps):
    """A UI that shows the body alone must not silently drop the sources it never showed."""
    page(deps, questions=["Đã ký chưa?"])
    saved = client.put(f"{url}/pages/han-eco", json={"body": "Lời mới, đủ dài để giữ lại."})
    assert saved.status_code == 200
    body = saved.json()
    assert body["sources"] == ["note:x"] and body["questions"] == ["Đã ký chưa?"]
    assert body["title"] == "Hạn Eco"
    assert wiki_links.authored_body(body["body"]) == "Lời mới, đủ dài để giữ lại."


def test_an_edited_link_is_reflected_on_the_page_it_points_at(client, url, deps):
    """An edited `[[link]]` changes what the *other* page says it is linked from, and a
    backlink that only appears after the next compile is a vault describing yesterday."""
    page(deps)
    page(deps, slug="so-sach", title="Sổ sách", body="Chuyện sổ sách hằng tháng, ghi cho đủ.")

    client.put(f"{url}/pages/so-sach", json={"body": f"[[Hạn Eco]] {LONG}"})

    target = client.get(f"{url}/pages/han-eco").json()
    assert "so-sach" in wiki_links.split_managed(target["body"])[1]


def test_deleting_a_page_leaves_the_pages_that_linked_to_it_readable(client, url, deps):
    page(deps)
    page(deps, slug="so-sach", title="Sổ sách", body=f"[[Hạn Eco]] {LONG}")
    client.put(f"{url}/pages/so-sach", json={"body": f"[[Hạn Eco]] {LONG}"})

    assert client.delete(f"{url}/pages/han-eco").status_code == 200

    assert client.get(f"{url}/pages/han-eco").status_code == 404
    left = client.get(f"{url}/pages/so-sach").json()
    # The edge is gone from the generated block, but the author's link stays: it is now a
    # to-do for the next compile, not a mistake to clean away.
    assert "han-eco" not in wiki_links.split_managed(left["body"])[1]
    assert "[[Hạn Eco]]" in wiki_links.authored_body(left["body"])


def test_the_report_says_what_is_wrong_and_what_is_still_unknown(client, url, deps):
    page(
        deps, slug="trong", title="Trống", body="Trang này chẳng có nguồn nào cả, thật.", sources=[]
    )
    page(deps, questions=["Đã ký chưa?"])

    body = client.get(f"{url}/report").json()
    assert {"slug": "trong", "kind": "unsourced", "detail": "Trống"} in body["problems"]
    assert body["questions"] == [{"slug": "han-eco", "question": "Đã ký chưa?"}]


def test_a_compile_cannot_start_while_the_rewrite_is_running(client, url, deps, app_rt):
    """Both read the same notes and write the same folder; two at once would race."""
    app_rt.consolidating.add(deps.agent.id)
    assert client.post(f"{url}/compile").status_code == 409


def test_a_compile_starts_and_answers_before_it_finishes(client, url):
    started = client.post(f"{url}/compile")
    assert started.status_code == 202 and started.json()["run_source"] == JOB_SOURCE


def test_an_unknown_agent_has_no_vault_to_read_or_compile(client):
    assert client.get("/api/agents/nobody/memory/wiki").status_code == 404
    assert client.post("/api/agents/nobody/memory/wiki/compile").status_code == 404
