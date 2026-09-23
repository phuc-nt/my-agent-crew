import os
import stat
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.env_file import read_env
from my_agent_crew.server.app import create_app
from my_agent_crew.server.credential_catalog import KNOWN
from my_agent_crew.server.credential_checks import run_check
from my_agent_crew.server.runtime_build import build_runtime

SECRET = "sk-or-v1-test-secret-value"


@pytest.fixture
def environ():
    """The routes write to the process environment, as they must for the crew to see
    a key; each test gets it back as it was, minus anything a developer's shell set."""
    saved = dict(os.environ)
    for known in KNOWN:
        os.environ.pop(known.name, None)
    yield os.environ
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def crew(tmp_path: Path, environ):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    app = create_app(runtime, schedule=False)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        yield client, runtime, home


def _item(reply: httpx.Response, name: str) -> dict:
    return next(i for i in reply.json()["items"] if i["name"] == name)


def test_the_list_names_every_known_connection_and_holds_no_secret(crew) -> None:
    client, _, home = crew
    (home / "env").write_text(f"OPENROUTER_API_KEY={SECRET}\nGOODREADS_ID=abc\n")

    reply = client.get("/api/credentials")

    assert reply.status_code == 200
    names = [i["name"] for i in reply.json()["items"]]
    assert names[:2] == ["OPENROUTER_API_KEY", "OLLAMA_BASE_URL"]
    assert "GOODREADS_ID" in names
    key = _item(reply, "OPENROUTER_API_KEY")
    assert key["present"] is True and key["source"] == "file" and "value" not in key
    assert _item(reply, "GOODREADS_ID")["group"] == "other"
    assert SECRET not in reply.text and "abc" not in reply.text


def test_saving_a_key_writes_the_file_and_the_crew_uses_it_at_once(crew) -> None:
    client, runtime, home = crew
    assert "openrouter" not in runtime.providers

    reply = client.put("/api/credentials/OPENROUTER_API_KEY", json={"value": f" {SECRET}\n"})

    assert reply.status_code == 200
    assert reply.json()["restart_required"] is None
    assert SECRET not in reply.text
    assert read_env(home / "env") == {"OPENROUTER_API_KEY": SECRET}
    assert stat.S_IMODE((home / "env").stat().st_mode) == 0o600
    assert "openrouter" in runtime.providers
    assert runtime.settings.openrouter_api_key == SECRET
    assert runtime.default.settings.openrouter_api_key == SECRET


def test_a_host_address_is_echoed_and_must_be_a_url(crew) -> None:
    client, runtime, _ = crew

    bad = client.put("/api/credentials/FIRECRAWL_BASE_URL", json={"value": "localhost:3002"})
    good = client.put(
        "/api/credentials/FIRECRAWL_BASE_URL", json={"value": "http://localhost:3002/"}
    )

    assert bad.status_code == 422
    assert _item(good, "FIRECRAWL_BASE_URL")["value"] == "http://localhost:3002"
    assert runtime.settings.firecrawl_base_url == "http://localhost:3002"


def test_removing_a_key_takes_it_out_of_the_file_and_the_crew(crew) -> None:
    client, runtime, home = crew
    client.put("/api/credentials/OPENROUTER_API_KEY", json={"value": SECRET})

    reply = client.delete("/api/credentials/OPENROUTER_API_KEY")

    assert reply.status_code == 200
    assert _item(reply, "OPENROUTER_API_KEY")["present"] is False
    assert read_env(home / "env") == {}
    assert "OPENROUTER_API_KEY" not in os.environ
    assert "openrouter" not in runtime.providers


def test_a_key_the_server_was_started_with_cannot_be_removed_from_here(crew, environ) -> None:
    client, _, _ = crew
    environ["BRAVE_API_KEY"] = "from-the-shell"

    listed = client.get("/api/credentials")
    reply = client.delete("/api/credentials/BRAVE_API_KEY")

    assert _item(listed, "BRAVE_API_KEY")["source"] == "process"
    assert reply.status_code == 409
    assert environ["BRAVE_API_KEY"] == "from-the-shell"
    assert client.delete("/api/credentials/TAVILY_API_KEY").status_code == 404


def test_removing_a_file_key_keeps_a_different_value_the_process_was_given(crew, environ) -> None:
    client, _, home = crew
    (home / "env").write_text("BRAVE_API_KEY=old-file-value\n")
    environ["BRAVE_API_KEY"] = "from-the-shell"

    client.delete("/api/credentials/BRAVE_API_KEY")

    assert read_env(home / "env") == {}
    assert environ["BRAVE_API_KEY"] == "from-the-shell"


@pytest.mark.parametrize(
    ("name", "status"),
    [("PATH", 422), ("MY_AGENT_HOME", 422), ("DYLD_INSERT_LIBRARIES", 422), ("lower", 422)],
)
def test_names_that_steer_the_process_are_refused(crew, name, status) -> None:
    client, _, home = crew

    reply = client.put(f"/api/credentials/{name}", json={"value": "x"})

    assert reply.status_code == status
    assert not (home / "env").exists()


def test_a_value_that_would_add_a_line_of_shell_is_refused_without_being_repeated(crew) -> None:
    client, _, home = crew

    reply = client.put("/api/credentials/MY_TOKEN", json={"value": "abc\nrm -rf ~"})

    assert reply.status_code == 422
    assert "rm -rf" not in reply.text
    assert not (home / "env").exists()


def test_a_custom_variable_is_listed_under_other(crew) -> None:
    client, _, _ = crew

    reply = client.put("/api/credentials/GOODREADS_USER_ID", json={"value": "12345"})

    item = _item(reply, "GOODREADS_USER_ID")
    assert item["group"] == "other" and item["secret"] is True and item["present"] is True


@pytest.mark.parametrize(
    "headers",
    [{"host": "evil.example"}, {"origin": "http://evil.example"}],
)
def test_a_request_from_another_site_is_refused(crew, headers) -> None:
    client, _, home = crew

    put = client.put("/api/credentials/MY_TOKEN", json={"value": "x"}, headers=headers)
    listed = client.get("/api/credentials", headers=headers)

    assert put.status_code == 403 and listed.status_code == 403
    assert not (home / "env").exists()


def test_a_local_origin_is_accepted(crew) -> None:
    client, _, _ = crew

    reply = client.get("/api/credentials", headers={"origin": "http://localhost:5173"})

    assert reply.status_code == 200


def test_the_master_bot_token_is_listed_with_its_agent(crew) -> None:
    client, _, _ = crew
    client.patch(
        "/api/agents/default",
        json={"profile": {"telegram": {"token_env": "CREW_BOT_TOKEN", "chat_id": 7}}},
    )

    reply = client.put("/api/credentials/CREW_BOT_TOKEN", json={"value": "123:abc"})

    item = _item(reply, "CREW_BOT_TOKEN")
    assert item["group"] == "telegram" and item["agents"] == ["default"]
    assert item["checkable"] is True


def test_a_check_reports_what_the_service_said(crew) -> None:
    client, runtime, _ = crew
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(401)

    runtime.client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    client.put("/api/credentials/OPENROUTER_API_KEY", json={"value": SECRET})

    reply = client.post("/api/credentials/OPENROUTER_API_KEY/check")

    assert reply.status_code == 200
    assert reply.json()["ok"] is False and "401" in reply.json()["detail"]
    assert seen == [f"Bearer {SECRET}"]


def test_a_key_with_no_free_check_says_so(crew) -> None:
    client, _, _ = crew

    assert client.post("/api/credentials/BRAVE_API_KEY/check").status_code == 404
    assert client.post("/api/credentials/OPENROUTER_API_KEY/check").status_code == 409


async def test_a_failed_bot_check_never_shows_the_token() -> None:
    token = "123:very-secret"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        result = await run_check("telegram", token, client)

    assert result["ok"] is False
    assert token not in result["detail"]


async def test_a_working_bot_check_names_the_bot() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"username": "crew_bot"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        result = await run_check("telegram", "123:abc", client)

    assert result["ok"] is True and "@crew_bot" in result["detail"]


def test_ollama_can_be_checked_at_its_default_host_before_anything_is_set(crew) -> None:
    client, _, _ = crew

    reply = client.get("/api/credentials")

    ollama = _item(reply, "OLLAMA_BASE_URL")
    assert ollama["present"] is False and ollama["checkable"] is True
    assert ollama["default"].startswith("http://")
    assert _item(reply, "FIRECRAWL_BASE_URL")["checkable"] is False
    assert _item(reply, "OPENROUTER_API_KEY")["checkable"] is False
