"""`POST /api/notices`: a host tells the person something, as a finished run of the master's
that the inbox lists and Web Push announces."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts_notice
from my_agent_crew.activity.notices import NOTICE_SOURCE, TEXT_CHARS, TITLE_CHARS
from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.server import create_app
from my_agent_crew.store.runs import DONE


@pytest.fixture
def api(deps_factory):
    deps = deps_factory()
    app = create_app(deps, schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, app.state.runtime


def test_a_notice_is_a_finished_run_of_the_master_with_no_conversation(api):
    client, runtime = api
    text = "Máy Mac im lặng từ 07:00.\n" + "x" * (TEXT_CHARS - 40)

    res = client.post("/api/notices", json={"title": "Máy Mac im lặng", "text": text})

    assert res.status_code == 201
    [run] = runtime.hub.recent()
    assert res.json() == {"run_id": run.id}
    assert run.source.startswith(NOTICE_SOURCE) and run.agent_id == DEFAULT_AGENT_ID
    assert (run.title, run.status, run.conversation_id) == ("Máy Mac im lặng", DONE, None)
    assert run.finished_at is not None
    # Stored whole, so the inbox reads all of it from the run.
    assert runtime.store.runs.get(run.id).summary == text.strip()
    assert runtime.store.list() == []


def test_a_notice_without_a_title_gets_the_default_and_is_trimmed(api):
    client, runtime = api

    client.post("/api/notices", json={"title": "   ", "text": "  Ảnh chụp lỗi.  "})

    [run] = runtime.hub.recent()
    assert (run.title, run.summary) == (texts_notice.DEFAULT_TITLE, "Ảnh chụp lỗi.")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": ""},
        {"text": "   \n"},
        {"text": "x" * (TEXT_CHARS + 1)},
        {"text": "a", "title": "t" * (TITLE_CHARS + 1)},
        {"text": 3},
    ],
)
def test_a_notice_without_words_or_past_its_limits_is_refused(api, body):
    client, runtime = api

    res = client.post("/api/notices", json=body)

    assert res.status_code == 422
    assert runtime.hub.recent() == []
