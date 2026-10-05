"""What `config.yaml` may say of an MCP server and what it may not: an address worth
sending a key to, keys that only ever come from the environment, how far each tool is let
in, and which ones the owner says only read (`mcp/config.py`). And how an agent names the
servers it uses (`agents/profile_yaml.py`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.config import Settings, load_settings
from my_agent_crew.mcp.config import (
    CODEMODE,
    DEFERRED,
    DIRECT,
    HIDDEN,
    McpServer,
    MissingEnv,
    matches,
    parse_servers,
)

URL = "https://mcp.notion.com/mcp"


def one(**settings) -> McpServer:
    [server] = parse_servers({"notion": {"url": URL, **settings}})
    return server


def test_a_server_needs_only_an_address_and_starts_out_deferred_and_asking():
    server = one()

    assert (server.name, server.url, server.exposure) == ("notion", URL, DEFERRED)
    assert server.headers == () and server.read_only == () and server.timeout == 60.0
    # Nothing is taken to only read until the owner says so.
    assert not server.reads_only("search")
    assert parse_servers(None) == ()


def test_every_setting_of_a_server_is_read():
    server = one(
        description=" Sổ tay của nhóm ",
        headers={"Authorization": "Bearer ${NOTION_KEY}", "X-Team": "${TEAM}"},
        exposure="direct",
        tool_exposure={"delete-*": "hidden", "delete-draft": "deferred"},
        read_only=["search", "get-*"],
        timeout=30,
    )

    assert server.description == "Sổ tay của nhóm"
    assert server.exposure == DIRECT and server.timeout == 30.0
    assert server.env_names() == ("NOTION_KEY", "TEAM")
    assert server.reads_only("search") and server.reads_only("get-page")
    assert not server.reads_only("search-and-replace")


@pytest.mark.parametrize(
    ("tool", "level"),
    [
        ("delete-draft", DEFERRED),  # its own name wins over the pattern written before it
        ("delete-page", HIDDEN),
        ("run-query", CODEMODE),  # the first pattern that fits, not the last
        ("search", DIRECT),  # nothing names it: the server's own level
    ],
)
def test_a_tools_level_is_its_own_name_then_the_first_pattern_then_the_servers(tool, level):
    server = one(
        exposure="direct",
        tool_exposure={
            "delete-*": "hidden",
            "delete-draft": "deferred",
            "run-*": "codemode",
            "*-query": "hidden",
        },
    )

    assert server.exposure_of(tool) == level


def test_a_star_stands_for_any_run_and_nothing_else_is_a_pattern():
    assert matches("get-*", "get-page") and matches("*", "anything")
    assert matches("*-page-*", "get-page-content")
    assert not matches("get-*", "forget-page")
    # A dot in a tool's name is a dot, not "any character".
    assert matches("a.b", "a.b") and not matches("a.b", "axb")


def test_a_header_is_filled_from_the_environment_each_time_it_is_asked_for():
    server = one(headers={"Authorization": "Bearer ${NOTION_KEY}", "X-Both": "${TEAM}-${TEAM}"})
    env = {"NOTION_KEY": "first", "TEAM": "ops"}

    assert server.request_headers(env) == {"Authorization": "Bearer first", "X-Both": "ops-ops"}
    env["NOTION_KEY"] = "second"
    assert server.request_headers(env)["Authorization"] == "Bearer second"


def test_a_header_whose_variable_is_unset_or_empty_is_named_not_sent_blank():
    server = one(headers={"Authorization": "Bearer ${NOTION_KEY}", "X-Team": "${TEAM}"})

    with pytest.raises(MissingEnv) as failure:
        server.request_headers({"TEAM": ""})

    assert failure.value.names == ["NOTION_KEY", "TEAM"]


@pytest.mark.parametrize(
    ("settings", "problem"),
    [
        ({"url": None}, "url is required"),
        ({"url": "http://mcp.notion.com/mcp"}, "url must be https"),
        ({"url": "ftp://mcp.notion.com/mcp"}, "url must be https"),
        ({"url": "https://owner:secret@mcp.notion.com/mcp"}, "plain address"),
        ({"url": "https://owner@mcp.notion.com/mcp"}, "plain address"),
        ({"url": "https://:secret@mcp.notion.com/mcp"}, "plain address"),
        ({"url": "https://mcp.notion.com/mcp#frag"}, "plain address"),
        ({"url": "https:///mcp"}, "plain address"),
        ({"url": "https://[::1/mcp"}, "does not parse"),
        # A key written into the file is a key in a backup, a diff and a screenshot.
        ({"headers": {"Authorization": "Bearer sk-live-123"}}, "from the environment"),
        ({"headers": {"Authorization": ""}}, "from the environment"),
        ({"headers": {"Authorization": 7}}, "from the environment"),
        ({"headers": {"Mcp-Session-Id": "${X}"}}, "cannot be set"),
        ({"headers": {"content-type": "${X}"}}, "cannot be set"),
        ({"headers": {"Bad Header": "${X}"}}, "cannot be set"),
        ({"headers": ["Authorization"]}, "headers must map"),
        ({"exposure": "always"}, "exposure must be one of"),
        ({"tool_exposure": {"search": "sometimes"}}, "tool_exposure.search must be one of"),
        ({"tool_exposure": ["search"]}, "tool_exposure must map"),
        # A bare string would be read as a list of one-letter patterns.
        ({"read_only": "search"}, "read_only must be a list"),
        ({"read_only": ["search", ""]}, "read_only must be a list"),
        ({"timeout": 0}, "timeout must be seconds"),
        ({"timeout": 601}, "timeout must be seconds"),
        ({"timeout": True}, "timeout must be seconds"),
        ({"timeout": "30"}, "timeout must be seconds"),
        ({"command": "npx notion-mcp"}, "unknown keys ['command']"),
    ],
)
def test_a_server_written_wrongly_stops_the_start_and_says_what_is_wrong(settings, problem):
    with pytest.raises(ValueError, match="config.yaml: mcp_servers.notion: ") as failure:
        parse_servers({"notion": {"url": URL, **settings}})

    assert problem in str(failure.value)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_plain_http_is_allowed_only_for_a_server_on_this_machine(host):
    [server] = parse_servers({"local": {"url": f"http://{host}:3000/mcp"}})

    assert server.url == f"http://{host}:3000/mcp"
    with pytest.raises(ValueError, match="url must be https"):
        parse_servers({"lan": {"url": "http://192.168.1.20:3000/mcp"}})


@pytest.mark.parametrize("name", ["", "-notion", "_notion", "no tion", "n" * 33, "nốt"])
def test_a_servers_name_is_one_a_tool_and_a_variable_can_be_named_after(name):
    with pytest.raises(ValueError, match="a name is letters, digits"):
        parse_servers({name: {"url": URL}})


@pytest.mark.parametrize("raw", [["notion"], "notion", {"notion": URL}, {"notion": None}])
def test_a_list_or_a_bare_address_is_not_a_server(raw):
    with pytest.raises(ValueError, match="config.yaml: mcp_servers"):
        parse_servers(raw)


def test_two_servers_whose_sign_ins_would_share_a_variable_are_refused():
    """Each keeps its tokens under `MCP_<NAME>_…`; `my-notes` and `MY_NOTES` are one name
    there, and one would sign the other out."""
    with pytest.raises(ValueError, match="differ only by case") as failure:
        parse_servers({"my-notes": {"url": URL}, "MY_NOTES": {"url": URL}, "other": {"url": URL}})

    assert "my-notes" in str(failure.value) and "other" not in str(failure.value)
    assert one().env_key == "NOTION"
    [dashed] = parse_servers({"my-notes": {"url": URL}})
    assert dashed.env_key == "MY_NOTES"


def write_config(home: Path, text: str) -> dict[str, str]:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(text, encoding="utf-8")
    return {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}


def test_the_crews_servers_are_read_from_config_yaml(tmp_path: Path):
    env = write_config(
        tmp_path / "home",
        "mcp_servers:\n"
        "  notion:\n"
        "    url: https://mcp.notion.com/mcp\n"
        "    read_only: [search]\n"
        "  tracker:\n"
        "    url: https://tracker.example/mcp\n"
        "    headers:\n"
        "      Authorization: Bearer ${TRACKER_KEY}\n",
    )

    settings = load_settings(env=env)

    assert [server.name for server in settings.mcp_servers] == ["notion", "tracker"]
    assert settings.mcp_servers[0].reads_only("search")
    assert settings.mcp_servers[1].env_names() == ("TRACKER_KEY",)
    assert load_settings(env=write_config(tmp_path / "bare", "language: vi\n")).mcp_servers == ()


def test_a_key_written_into_config_yaml_stops_the_start(tmp_path: Path):
    env = write_config(
        tmp_path / "home",
        "mcp_servers:\n"
        "  tracker:\n"
        "    url: https://tracker.example/mcp\n"
        "    headers:\n"
        "      Authorization: Bearer sk-live-123\n",
    )

    with pytest.raises(ValueError, match="mcp_servers.tracker: header Authorization"):
        load_settings(env=env)


def test_an_agent_names_the_servers_it_uses_and_has_none_until_it_does(
    settings: Settings, tmp_path: Path
):
    named = parse_profile("coach", tmp_path / "coach", {"mcp": ["notion", "tracker"]}, settings)
    bare = parse_profile("coach", tmp_path / "coach", {}, settings)

    assert named.mcp == ("notion", "tracker") and named.to_dict()["mcp"] == ["notion", "tracker"]
    assert bare.mcp == () and bare.to_dict()["mcp"] == []
    with pytest.raises(ValueError, match="agent coach: mcp must be a list of names"):
        parse_profile("coach", tmp_path / "coach", {"mcp": "notion"}, settings)
