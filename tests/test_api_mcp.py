"""The crew's MCP servers as the web reaches them: how each stands, trying one again,
signing in and out, the keys they read and the agents that name them
(`server/routes_mcp.py`, `server/credential_catalog.py`, `server/routes_agents_edit.py`)."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts_mcp as t
from my_agent_crew.config import load_settings
from my_agent_crew.env_file import env_path, read_env
from my_agent_crew.mcp.schema_fold import fold
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.texts_credentials import CROSS_SITE_REQUEST
from tests.mcp_fakes import AUTH, MCP_URL, REDIRECT, TOOLS, FakeMcp, public
from tests.mcp_schema_fakes import chars, parameters

ACCESS, REFRESH, CLIENT, ISSUER = (
    "MCP_NOTION_ACCESS_TOKEN",
    "MCP_NOTION_REFRESH_TOKEN",
    "MCP_NOTION_CLIENT_ID",
    "MCP_NOTION_ISSUER",
)
NOTION = f"mcp_servers:\n  notion:\n    url: {MCP_URL}\n    description: Sổ tay của nhóm\n"
TRACKER = (
    f"mcp_servers:\n  tracker:\n    url: {MCP_URL}\n    read_only: [search]\n"
    "    headers:\n      Authorization: Bearer ${TRACKER_KEY}\n"
)
SEARCH, CREATE = "mcp__notion__search", "mcp__notion__create_page"
# `search` is said to only read, which is what makes it a script's to call, and is opened for
# scripts, which is what lists it in the description of the script tool.
SCRIPTED = NOTION + "    read_only: [search]\n    tool_exposure:\n      search: codemode\n"


@dataclass
class Crew:
    client: TestClient
    runtime: Runtime
    home: Path
    fake: FakeMcp

    def server(self, name: str = "notion") -> dict:
        rows = self.client.get("/api/mcp").json()["servers"]
        return next(row for row in rows if row["name"] == name)

    def tools_of(self, agent_id: str) -> list[str]:
        return [name for name in self.runtime.deps_for(agent_id).tools.names() if "mcp__" in name]

    def sign_in(self) -> None:
        url = self.client.post("/api/mcp/notion/login").json()["authorize_url"]
        code, state = self.fake.approve(url)
        self.client.get(
            "/api/mcp/oauth/callback",
            params={"code": code, "state": state},
            follow_redirects=False,
        )


@pytest.fixture
def environ() -> Iterator[None]:
    """A sign-in and a saved key are written to the process environment, as they must be
    for the crew to use them; each test gets it back as it was."""
    saved = dict(os.environ)
    for name in (ACCESS, REFRESH, CLIENT, ISSUER, "TRACKER_KEY"):
        os.environ.pop(name, None)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def crew_with(tmp_path: Path, environ) -> Iterator[Callable[..., Crew]]:
    def build(config: str, fake: FakeMcp) -> Crew:
        home = tmp_path / "home"
        home.mkdir()
        (home / "config.yaml").write_text(config, encoding="utf-8")
        env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
        runtime = build_runtime(load_settings(env=env), client=fake.client())
        runtime.mcp.resolver = public
        app = create_app(runtime, schedule=False)
        client = stack.enter_context(TestClient(app, base_url="http://127.0.0.1:8765"))
        return Crew(client, runtime, home, fake)

    with ExitStack() as stack:
        yield build


def test_a_server_is_listed_as_it_stands_before_and_after_it_is_tried(crew_with) -> None:
    fake = FakeMcp()
    fake.required = "the-key-itself"
    crew = crew_with(TRACKER, fake)
    os.environ["TRACKER_KEY"] = "the-key-itself"

    before = crew.server("tracker")
    reply = crew.client.post("/api/mcp/tracker/reconnect")

    assert before == {
        "name": "tracker",
        "url": MCP_URL,
        "description": "",
        "status": "idle",
        "error": "",
        "exposure": "deferred",
        "signed_in": False,
        "uses_key": True,
        "env": ["TRACKER_KEY"],
        "agents": [],
        "skipped": [],
        "tools": [],
    }
    assert reply.status_code == 200
    [row] = reply.json()["servers"]
    assert (row["status"], row["error"]) == ("connected", "")
    assert [(tool["remote"], tool["requires_approval"]) for tool in row["tools"]] == [
        ("search", False),  # the owner's `read_only` says it only reads
        ("create-page", True),
    ]
    assert "the-key-itself" not in reply.text


def test_a_tool_told_to_the_model_folded_says_so_on_its_row(crew_with) -> None:
    schema = parameters()
    wide = {"name": "query", "description": "Rows that pass.", "inputSchema": schema}
    crew = crew_with(NOTION, FakeMcp([wide, *TOOLS]))

    [tried] = crew.client.post("/api/mcp/notion/reconnect").json()["servers"]
    row = crew.server()

    assert row == tried and row["skipped"] == []
    assert [(tool["remote"], tool["folded"]) for tool in row["tools"]] == [
        ("query", {"from": chars(schema), "to": chars(fold(schema))}),
        ("search", None),
        ("create-page", None),
    ]
    assert chars(schema) > 50_000 > chars(fold(schema))


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/mcp/nope/reconnect"),
        ("post", "/api/mcp/nope/login"),
        ("delete", "/api/mcp/nope/login"),
    ],
)
def test_a_server_the_crew_does_not_have_is_not_found(crew_with, method, path) -> None:
    crew = crew_with(NOTION, FakeMcp())

    reply = crew.client.request(method, path)

    assert reply.status_code == 404
    assert reply.json()["detail"] == t.MCP_UNKNOWN_SERVER.format(name="nope")
    assert crew.fake.fetched == []


def test_a_key_the_server_refuses_says_so_and_the_right_one_is_tried_from_the_keys_page(
    crew_with,
) -> None:
    fake = FakeMcp()
    fake.required = "the-right-key"
    crew = crew_with(TRACKER, fake)

    missing = crew.client.post("/api/mcp/tracker/reconnect").json()["servers"][0]
    assert (missing["status"], missing["error"]) == (
        "failed",
        t.MCP_MISSING_ENV.format(names="TRACKER_KEY"),
    )

    listed = crew.client.get("/api/credentials").json()["items"]
    key = next(item for item in listed if item["name"] == "TRACKER_KEY")
    assert (key["group"], key["servers"], key["present"]) == ("mcp", ["tracker"], False)
    assert key["secret"] is True and key["editable"] is True and "value" not in key

    saved = crew.client.put("/api/credentials/TRACKER_KEY", json={"value": "a-wrong-key"})
    assert saved.status_code == 200 and "a-wrong-key" not in saved.text
    # Whoever waits to try the servers that are down is told a key changed.
    assert crew.runtime.mcp.wake.is_set()
    refused = crew.client.post("/api/mcp/tracker/reconnect").json()["servers"][0]
    assert (refused["status"], refused["error"]) == ("failed", t.MCP_KEY_REFUSED)

    crew.client.put("/api/credentials/TRACKER_KEY", json={"value": "the-right-key"})
    assert crew.client.post("/api/mcp/tracker/reconnect").json()["servers"][0]["status"] == (
        "connected"
    )


def test_an_agent_names_a_server_from_its_editor_and_holds_its_tools_at_once(crew_with) -> None:
    crew = crew_with(NOTION, FakeMcp())
    crew.client.post("/api/mcp/notion/reconnect")
    crew.client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    assert crew.tools_of("coder") == [] and crew.server()["agents"] == []

    reply = crew.client.patch("/api/agents/coder", json={"profile": {"mcp": ["notion"]}})

    assert reply.status_code == 200 and reply.json()["profile"]["mcp"] == ["notion"]
    # Behind the tools of its own, the last of which is the one that runs its scripts.
    assert reply.json()["profile"]["tools"][-4:] == ["tool_search", "tool_script", SEARCH, CREATE]
    assert crew.tools_of("coder") == [SEARCH, CREATE] and crew.tools_of("default") == []
    manifest = (crew.home / "agents" / "coder" / "agent.yaml").read_text(encoding="utf-8")
    assert "mcp:\n- notion\n" in manifest or "mcp:\n  - notion\n" in manifest
    assert crew.server()["agents"] == ["coder"]
    # The agent's page says where each tool comes from and how far it is let in.
    shown = crew.client.get("/api/agents/coder").json()["tools"]
    assert [tool for tool in shown if tool["name"] == CREATE] == [
        {
            "name": CREATE,
            "description": t.MCP_DESCRIPTION.format(server="notion", description="Make a page."),
            "requires_approval": True,
            "server": "notion",
            "exposure": "deferred",
        }
    ]

    # The search that finds them is the agent's too, and says what it came with.
    [search] = [tool for tool in shown if tool["name"] == "tool_search"]
    assert search["with_mcp"] is True and search["requires_approval"] is False
    assert "notion (Sổ tay của nhóm)" in search["description"]
    listed = {tool["name"]: tool for tool in crew.client.get("/api/tools").json()}
    assert listed["tool_search"] == {**search, "agents": ["coder"], "optional": False}
    assert [name for name, tool in listed.items() if "with_mcp" in tool] == ["tool_search"]

    cleared = crew.client.patch("/api/agents/coder", json={"profile": {"mcp": []}})

    assert cleared.status_code == 200 and crew.tools_of("coder") == []
    assert crew.server()["agents"] == []
    # With no server left to search, the search goes too. The script tool is the agent's
    # whatever its servers.
    assert "tool_search" not in cleared.json()["profile"]["tools"]
    assert cleared.json()["profile"]["tools"][-1] == "tool_script"
    assert "tool_search" not in [tool["name"] for tool in crew.client.get("/api/tools").json()]


def shown_of(crew: Crew, agent_id: str) -> dict[str, dict]:
    """An agent's tools as its page shows them, by name."""
    return {
        tool["name"]: tool for tool in crew.client.get(f"/api/agents/{agent_id}").json()["tools"]
    }


def test_an_agent_that_names_no_server_holds_the_script_tool(crew_with) -> None:
    crew = crew_with(NOTION, FakeMcp())
    crew.client.post("/api/mcp/notion/reconnect")
    crew.client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    writes = {"tools": ["workspace_write"]}
    crew.client.post("/api/agents", json={"agent_id": "scribe", "profile": writes})

    rows = {row["id"]: row["tools"] for row in crew.client.get("/api/agents").json()}

    assert crew.server()["agents"] == []
    # Last of each agent's tools; the master's hand-out tool is ahead of it.
    assert rows["coder"][-1] == "tool_script" and rows["coder"].count("tool_script") == 1
    assert rows["default"][-2:] == ["delegate", "tool_script"]
    # An agent with no tool that only reads has no use for a script.
    assert rows["scribe"] == ["workspace_write"]
    script = shown_of(crew, "coder")["tool_script"]
    assert script["with_reads"] is True and "with_mcp" not in script
    assert script["requires_approval"] is False
    assert (
        "\n- workspace_read(path: string, offset?: integer, limit?: integer)\n"
        in (script["description"])
    )
    assert "Công cụ MCP" not in script["description"]
    # The crew's list names every agent that holds it, and marks it apart from the search.
    listed = {tool["name"]: tool for tool in crew.client.get("/api/tools").json()}
    assert listed["tool_script"]["agents"] == ["coder", "default"]
    assert listed["tool_script"]["with_reads"] is True
    assert listed["tool_script"]["optional"] is False
    assert [name for name, tool in listed.items() if "with_reads" in tool] == ["tool_script"]
    assert [name for name, tool in listed.items() if "with_mcp" in tool] == []


def test_the_script_tool_of_an_agent_names_the_tool_its_server_opened_for_scripts(
    crew_with,
) -> None:
    crew = crew_with(SCRIPTED, FakeMcp())
    crew.client.post("/api/mcp/notion/reconnect")
    crew.client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    alone = shown_of(crew, "coder")["tool_script"]

    reply = crew.client.patch("/api/agents/coder", json={"profile": {"mcp": ["notion"]}})

    held = reply.json()["profile"]["tools"]
    assert held[-4:] == ["tool_search", "tool_script", SEARCH, CREATE]
    shown = shown_of(crew, "coder")
    script = shown["tool_script"]
    assert script["with_reads"] is True and script["requires_approval"] is False
    line = f"- {SEARCH}(query: string): [MCP notion] Find pages by words."
    assert line in script["description"] and line not in alone["description"]
    assert (shown[SEARCH]["exposure"], shown[SEARCH]["requires_approval"]) == ("codemode", False)
    assert (shown[CREATE]["exposure"], shown[CREATE]["requires_approval"]) == ("deferred", True)
    # Only the search comes with a server: the script tool is every agent's that reads, and
    # the one that names no server is told of none of its tools.
    listed = {tool["name"]: tool for tool in crew.client.get("/api/tools").json()}
    assert [name for name, tool in listed.items() if "with_mcp" in tool] == ["tool_search"]
    assert listed["tool_script"]["agents"] == ["coder", "default"]
    assert SEARCH not in shown_of(crew, "default")["tool_script"]["description"]

    cleared = crew.client.patch("/api/agents/coder", json={"profile": {"mcp": []}})

    # With no server left to read from, the search goes and the script tool says what it
    # said before.
    tools = cleared.json()["profile"]["tools"]
    assert "tool_search" not in tools and tools[-1] == "tool_script"
    assert shown_of(crew, "coder")["tool_script"] == alone
    names = [tool["name"] for tool in crew.client.get("/api/tools").json()]
    assert "tool_script" in names and "tool_search" not in names


def test_an_agent_may_not_be_given_a_server_the_crew_does_not_have(crew_with) -> None:
    crew = crew_with(NOTION, FakeMcp())
    crew.client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    path = crew.home / "agents" / "coder" / "agent.yaml"
    before = path.read_text(encoding="utf-8")

    reply = crew.client.patch("/api/agents/coder", json={"profile": {"mcp": ["notion", "jira"]}})

    assert reply.status_code == 422
    assert reply.json()["detail"] == t.MCP_AGENT_UNKNOWN_SERVER.format(name="jira")
    assert path.read_text(encoding="utf-8") == before
    assert crew.runtime.deps_for("coder").agent.mcp == ()
    made = crew.client.post("/api/agents", json={"agent_id": "new", "profile": {"mcp": ["jira"]}})
    assert made.status_code == 422 and "new" not in crew.runtime.agents


def test_a_file_that_names_a_server_since_removed_does_not_hold_up_other_edits(crew_with) -> None:
    crew = crew_with(NOTION, FakeMcp())
    crew.client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    path = crew.home / "agents" / "coder" / "agent.yaml"
    path.write_text("mcp: [jira]\n", encoding="utf-8")  # written by hand

    reply = crew.client.patch("/api/agents/coder", json={"profile": {"name": "Thợ code"}})

    assert reply.status_code == 200 and reply.json()["profile"]["mcp"] == ["jira"]
    assert crew.tools_of("coder") == []


def test_trying_a_server_again_hands_its_tools_to_the_agents_that_name_it(crew_with) -> None:
    fake = FakeMcp()
    crew = crew_with(NOTION, fake)
    crew.client.post("/api/agents", json={"agent_id": "coder", "profile": {"mcp": ["notion"]}})
    assert crew.tools_of("coder") == []  # nothing has asked the server anything yet

    crew.client.post("/api/mcp/notion/reconnect")
    assert crew.tools_of("coder") == [SEARCH, CREATE]

    fake.tools = fake.tools[:1]
    crew.client.post("/api/mcp/notion/reconnect")
    assert crew.tools_of("coder") == [SEARCH]


def test_signing_in_from_the_web_ends_with_the_server_connected_and_no_token_shown(
    crew_with,
) -> None:
    crew = crew_with(NOTION, FakeMcp(oauth=True))
    client = crew.client
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"mcp": ["notion"]}})
    asked = client.post("/api/mcp/notion/reconnect").json()["servers"][0]
    assert (asked["status"], asked["signed_in"], asked["tools"]) == ("signed_out", False, [])

    started = client.post("/api/mcp/notion/login")

    assert started.status_code == 200 and set(started.json()) == {"authorize_url"}
    url = started.json()["authorize_url"]
    assert url.startswith(f"{AUTH}/authorize?")
    # The person is sent back to the address they opened the crew on.
    assert crew.fake.registered[0]["redirect_uris"] == [REDIRECT]
    code, state = crew.fake.approve(url)
    back = client.get(
        "/api/mcp/oauth/callback",
        params={"code": code, "state": state},
        # They arrive from the other site: the one API address that may be reached so.
        headers={"Sec-Fetch-Site": "cross-site"},
        follow_redirects=False,
    )

    assert (back.status_code, back.headers["location"]) == (303, "/#/manage/connections")
    row = crew.server()
    assert (row["status"], row["signed_in"], row["uses_key"]) == ("connected", True, False)
    assert crew.tools_of("coder") == [SEARCH, CREATE]
    kept = read_env(env_path(crew.home))
    assert kept == {ACCESS: "access-1", REFRESH: "refresh-1", CLIENT: "client-1", ISSUER: AUTH}
    assert os.environ[ACCESS] == "access-1"
    listed = client.get("/api/credentials")
    names = [item["name"] for item in listed.json()["items"]]
    # A sign-in is kept and dropped on this screen, not retyped as a key on the other.
    assert ACCESS not in names and REFRESH not in names and ISSUER not in names
    assert CLIENT in names
    for reply in (client.get("/api/mcp"), listed, client.get("/api/agents/coder")):
        assert "access-1" not in reply.text and "refresh-1" not in reply.text


def test_signing_out_drops_the_tokens_and_takes_the_tools_back(crew_with) -> None:
    crew = crew_with(NOTION, FakeMcp(oauth=True))
    crew.client.post("/api/agents", json={"agent_id": "coder", "profile": {"mcp": ["notion"]}})
    crew.client.post("/api/mcp/notion/reconnect")
    crew.sign_in()
    assert crew.tools_of("coder") == [SEARCH, CREATE]

    reply = crew.client.delete("/api/mcp/notion/login")

    [row] = reply.json()["servers"]
    assert (row["status"], row["signed_in"], row["tools"]) == ("signed_out", False, [])
    assert crew.tools_of("coder") == []
    assert read_env(env_path(crew.home)) == {CLIENT: "client-1"}
    assert ACCESS not in os.environ and REFRESH not in os.environ


@pytest.mark.parametrize(
    ("params", "said"),
    [
        ({"error": "access_denied"}, t.MCP_OAUTH_DENIED.format(error="access_denied")),
        ({}, t.MCP_OAUTH_NO_CODE),
        ({"code": "made-up"}, t.MCP_OAUTH_TOKEN.format(error="HTTP 400 invalid_grant")),
    ],
    ids=["the person said no", "no code", "a code the server does not know"],
)
def test_a_sign_in_that_fails_still_lands_on_the_screen_that_says_why(
    crew_with, params, said
) -> None:
    crew = crew_with(NOTION, FakeMcp(oauth=True))
    crew.client.post("/api/mcp/notion/reconnect")
    url = crew.client.post("/api/mcp/notion/login").json()["authorize_url"]
    _, state = crew.fake.approve(url)

    back = crew.client.get(
        "/api/mcp/oauth/callback", params={**params, "state": state}, follow_redirects=False
    )

    assert (back.status_code, back.headers["location"]) == (303, "/#/manage/connections")
    row = crew.server()
    assert (row["status"], row["error"], row["signed_in"]) == ("signed_out", said, False)


def test_the_callback_hands_on_who_says_the_code_is_theirs(crew_with) -> None:
    crew = crew_with(NOTION, FakeMcp(oauth=True))
    crew.client.post("/api/mcp/notion/reconnect")
    url = crew.client.post("/api/mcp/notion/login").json()["authorize_url"]
    code, state = crew.fake.approve(url)
    elsewhere = "https://login.elsewhere.test"

    back = crew.client.get(
        "/api/mcp/oauth/callback",
        params={"code": code, "state": state, "iss": elsewhere},
        follow_redirects=False,
    )

    assert (back.status_code, back.headers["location"]) == (303, "/#/manage/connections")
    row = crew.server()
    said = t.MCP_OAUTH_ISSUER.format(got=elsewhere, expected=AUTH)
    assert (row["status"], row["error"], row["signed_in"]) == ("signed_out", said, False)
    assert crew.fake.token_requests == [] and read_env(env_path(crew.home)) == {}


def test_a_callback_nobody_was_waiting_for_changes_nothing(crew_with) -> None:
    crew = crew_with(NOTION, FakeMcp(oauth=True))
    crew.client.post("/api/mcp/notion/reconnect")
    fetched = len(crew.fake.fetched)

    for params in ({"code": "x", "state": "made-up"}, {"code": "x"}, {}):
        back = crew.client.get("/api/mcp/oauth/callback", params=params, follow_redirects=False)
        assert back.status_code == 303

    row = crew.server()
    assert (row["status"], row["error"]) == ("signed_out", "")
    assert len(crew.fake.fetched) == fetched and read_env(env_path(crew.home)) == {}


@pytest.mark.parametrize("host", ["192.168.1.20:8765", "100.64.0.7:8765", "10.0.0.2"])
def test_a_sign_in_starts_only_from_the_machine_the_crew_runs_on(crew_with, host) -> None:
    """The person is sent back to the address they came from, and an authorization server
    sends a public client's code only to a loopback one."""
    crew = crew_with(NOTION, FakeMcp(oauth=True))
    crew.client.post("/api/mcp/notion/reconnect")
    fetched = len(crew.fake.fetched)

    reply = crew.client.post("/api/mcp/notion/login", headers={"Host": host})

    assert reply.status_code == 409 and reply.json()["detail"] == t.MCP_LOGIN_LOCAL_ONLY
    assert len(crew.fake.fetched) == fetched and crew.fake.registered == []


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1:9000", "[::1]:8765"])
def test_any_name_of_this_machine_will_do_and_is_where_the_person_comes_back_to(
    crew_with, host
) -> None:
    crew = crew_with(NOTION, FakeMcp(oauth=True))
    crew.client.post("/api/mcp/notion/reconnect")

    reply = crew.client.post("/api/mcp/notion/login", headers={"Host": host})

    assert reply.status_code == 200
    assert crew.fake.registered[0]["redirect_uris"] == [f"http://{host}/api/mcp/oauth/callback"]


@pytest.mark.parametrize(
    ("config", "fake", "said"),
    [
        (TRACKER.replace("tracker", "notion"), FakeMcp(oauth=True), t.MCP_LOGIN_HEADER_KEY),
        (NOTION, FakeMcp(), t.MCP_LOGIN_NOT_ASKED),
    ],
    ids=["a server with a key in the file", "a server that asks for no sign-in"],
)
def test_a_sign_in_that_cannot_start_says_why(crew_with, config, fake, said) -> None:
    crew = crew_with(config, fake)
    crew.client.post("/api/mcp/notion/reconnect")

    reply = crew.client.post("/api/mcp/notion/login")

    assert reply.status_code == 409 and reply.json()["detail"] == said
    assert fake.registered == []


def test_only_the_way_back_from_a_sign_in_may_be_reached_from_another_site(crew_with) -> None:
    crew = crew_with(NOTION, FakeMcp(oauth=True))
    elsewhere = {"Sec-Fetch-Site": "cross-site"}

    for method, path in (
        ("get", "/api/mcp"),
        ("post", "/api/mcp/notion/login"),
        ("post", "/api/mcp/notion/reconnect"),
        ("delete", "/api/mcp/notion/login"),
        ("get", "/api/mcp/oauth/callback/"),
    ):
        reply = crew.client.request(method, path, headers=elsewhere, follow_redirects=False)
        assert (reply.status_code, reply.json()["detail"]) == (403, CROSS_SITE_REQUEST), path

    assert crew.fake.fetched == []
    back = crew.client.get("/api/mcp/oauth/callback", headers=elsewhere, follow_redirects=False)
    assert back.status_code == 303
