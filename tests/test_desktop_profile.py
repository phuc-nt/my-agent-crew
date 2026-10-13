"""The desktop's settings: where the machine's file or the environment puts the helper's
socket, what one agent says in its own file, and that a save from the web is read back as
what was asked."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from my_agent_crew.agents import load_profiles
from my_agent_crew.agents.profile import PROFILE_KEYS
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.config import Settings, load_settings
from my_agent_crew.config_desktop import DesktopSettings, socket_path
from my_agent_crew.config_yaml import YAML_KEYS
from my_agent_crew.desktop.kit import DESKTOP_TOOLS
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime

QUOTE_IT = 'put "on" in quotes'
APPS_REFUSAL = "computer_apps must be a list of application names or bundle ids"


def test_a_machine_looks_for_the_helper_under_its_own_home(tmp_path: Path):
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})

    assert settings.desktop == DesktopSettings()
    assert (settings.desktop.mode, settings.desktop.apps, settings.desktop.on) == ("off", (), False)
    assert socket_path(settings.home, settings.desktop) == settings.home / "desktop" / "sock"


def test_the_file_names_the_socket_and_the_environment_wins(tmp_path: Path):
    home = {"MY_AGENT_HOME": str(tmp_path)}
    (tmp_path / "config.yaml").write_text("desktop_socket: /tmp/dh-a/sock\n", encoding="utf-8")

    from_file = load_settings(env=home)
    from_env = load_settings(env={**home, "MY_AGENT_DESKTOP_SOCKET": " /tmp/dh-b/sock "})

    assert "desktop_socket" in YAML_KEYS
    assert from_file.desktop == DesktopSettings(socket="/tmp/dh-a/sock")
    assert socket_path(from_file.home, from_file.desktop) == Path("/tmp/dh-a/sock")
    assert from_env.desktop == DesktopSettings(socket="/tmp/dh-b/sock")


def test_a_socket_left_blank_is_the_one_under_the_home(tmp_path: Path):
    home = {"MY_AGENT_HOME": str(tmp_path)}
    (tmp_path / "config.yaml").write_text("desktop_socket: ''\n", encoding="utf-8")

    assert load_settings(env=home).desktop == DesktopSettings()
    assert load_settings(env={**home, "MY_AGENT_DESKTOP_SOCKET": "  "}).desktop == DesktopSettings()


@pytest.mark.parametrize(
    ("line", "said"),
    [
        ("desktop_socket: desktop/sock", "desktop_socket must be an absolute path"),
        ("desktop_socket: 7", "desktop_socket must be a path"),
        ("desktop_socket: [/tmp/sock]", "desktop_socket must be a path"),
        (f"desktop_socket: /tmp/{'d' * 99}", "longer than the 103 bytes a socket path may have"),
        ("desktop_enabled: true", "unknown keys ['desktop_enabled']"),
        ("computer: on", "unknown keys ['computer']"),
    ],
)
def test_a_desktop_setting_nobody_knows_stops_the_start(tmp_path: Path, line: str, said: str):
    (tmp_path / "config.yaml").write_text(line + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as refusal:
        load_settings(env={"MY_AGENT_HOME": str(tmp_path)})

    assert said in str(refusal.value)


def test_a_socket_path_of_exactly_the_longest_length_is_taken(tmp_path: Path):
    longest = "/tmp/" + "d" * 98

    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_DESKTOP_SOCKET": longest}

    assert len(longest.encode()) == 103
    assert load_settings(env=env).desktop.socket == longest


def parsed(settings: Settings, tmp_path: Path, text: str) -> DesktopSettings:
    """What the start reads from an `agent.yaml` written by hand."""
    raw = yaml.safe_load(text) or {}
    return parse_profile("coach", tmp_path / "agents" / "coach", raw, settings).settings.desktop


def test_an_agent_uses_the_desktop_only_where_its_own_file_says_so(settings, tmp_path):
    silent = parsed(settings, tmp_path, "name: Coach\n")
    looks = parsed(settings, tmp_path, 'computer: "on"\n')
    acts = parsed(settings, tmp_path, "computer: 'on'\ncomputer_apps: [Notes, com.apple.Safari]\n")

    assert (silent.mode, silent.on, silent.apps) == ("off", False, ())
    assert (looks.mode, looks.on, looks.apps) == ("on", True, ())
    assert (acts.mode, acts.on, acts.apps) == ("on", True, ("Notes", "com.apple.Safari"))
    assert {"computer", "computer_apps"} <= PROFILE_KEYS


def test_the_machines_socket_is_the_agents_too(settings, tmp_path):
    machine = replace(settings, desktop=DesktopSettings(socket="/tmp/dh-a/sock"))

    assert parsed(machine, tmp_path, 'computer: "on"\n').socket == "/tmp/dh-a/sock"


def test_the_mode_is_never_inherited_from_the_settings_an_agent_starts_from(settings, tmp_path):
    base = replace(settings, desktop=DesktopSettings(mode="on", apps=("Notes",)))

    silent = parsed(base, tmp_path, "name: Coach\n")

    assert (silent.mode, silent.apps) == ("off", ())


@pytest.mark.parametrize("word", ["off", "no", "false", "Off", "~", "", '"off"'])
def test_a_bare_yaml_off_means_off(settings, tmp_path, word):
    assert parsed(settings, tmp_path, f"computer: {word}\n").mode == "off"


@pytest.mark.parametrize("word", ["on", "yes", "true", "On", "YES"])
def test_a_bare_yaml_on_is_refused_and_told_how_to_write_the_word(settings, tmp_path, word):
    with pytest.raises(ValueError) as refusal:
        parsed(settings, tmp_path, f"computer: {word}\n")

    assert "agent coach: computer must be off or on" in str(refusal.value)
    assert QUOTE_IT in str(refusal.value)


@pytest.mark.parametrize(
    "text",
    [
        "computer: act\n",
        "computer: read\n",
        "computer: [on]\n",
        "computer: 1\n",
        'computer: "On"\n',
    ],
)
def test_a_mode_nobody_knows_is_refused(settings, tmp_path, text):
    with pytest.raises(ValueError) as refusal:
        parsed(settings, tmp_path, text)

    assert str(refusal.value) == "agent coach: computer must be off or on"


@pytest.mark.parametrize(
    "apps",
    [
        "Notes",
        "7",
        "{Notes: true}",
        "[7]",
        "[Notes, '']",
        "[Notes, '   ']",
        "[[Notes]]",
        "[true]",
        '["Notes\\nSafari"]',
        f"[{'n' * 201}]",
    ],
)
def test_an_application_list_holds_only_names(settings, tmp_path, apps):
    with pytest.raises(ValueError) as refusal:
        parsed(settings, tmp_path, f'computer: "on"\ncomputer_apps: {apps}\n')

    assert f"agent coach: {APPS_REFUSAL}" in str(refusal.value)


def test_a_name_is_kept_as_written_once_and_without_the_blanks_around_it(settings, tmp_path):
    apps = "[' Notes ', Notes, notes, 'Ngân hàng', com.apple.Notes, 'Notes']"

    read = parsed(settings, tmp_path, f'computer: "on"\ncomputer_apps: {apps}\n')

    assert read.apps == ("Notes", "notes", "Ngân hàng", "com.apple.Notes")


@pytest.mark.parametrize("apps", ["[]", "~", ""])
def test_an_empty_application_list_is_no_application(settings, tmp_path, apps):
    assert parsed(settings, tmp_path, f'computer: "on"\ncomputer_apps: {apps}\n').apps == ()


def test_a_name_of_exactly_the_longest_length_is_taken(settings, tmp_path):
    name = "n" * 200

    assert parsed(settings, tmp_path, f"computer_apps: [{name}]\n").apps == (name,)


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env), env=dict(env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        client.post("/api/agents", json={"agent_id": "coach", "profile": {"name": "Coach"}})
        yield client, runtime, home


def read_at_start(home: Path) -> dict:
    return yaml.safe_load((home / "agents" / "coach" / "agent.yaml").read_text(encoding="utf-8"))


def desktop_tools(runtime, agent_id: str = "coach") -> list[str]:
    return [name for name in runtime.deps_for(agent_id).tools.names() if name in DESKTOP_TOOLS]


def test_an_agent_is_told_with_its_two_keys(crew):
    client, _, _ = crew

    told = client.get("/api/agents/coach").json()
    listed = {agent["id"]: agent for agent in client.get("/api/agents").json()}

    assert (told["computer"], told["computer_apps"]) == ("off", [])
    assert (listed["coach"]["computer"], listed["default"]["computer_apps"]) == ("off", [])


def test_a_save_from_the_web_is_what_the_next_start_reads(crew):
    client, runtime, home = crew
    assert desktop_tools(runtime) == []

    reply = client.patch(
        "/api/agents/coach",
        json={"profile": {"computer": "on", "computer_apps": ["Notes", "com.apple.Safari"]}},
    )

    assert reply.status_code == 200, reply.text
    profile = reply.json()["profile"]
    assert (profile["computer"], profile["computer_apps"]) == ("on", ["Notes", "com.apple.Safari"])
    assert reply.json()["restart_required"] == []
    live = runtime.deps_for("coach").agent.settings.desktop
    assert (live.mode, live.apps, live.on) == ("on", ("Notes", "com.apple.Safari"), True)
    # The agent holds its tools at once, with no helper on the machine and no restart.
    assert desktop_tools(runtime) == list(DESKTOP_TOOLS)
    # PyYAML, which reads the file at the start, takes a bare `on` for True, and the start
    # refuses that: the word is kept in quotes so the file says what the person chose.
    assert read_at_start(home)["computer"] == "on"
    assert read_at_start(home)["computer_apps"] == ["Notes", "com.apple.Safari"]
    again = load_profiles(load_settings(env={"MY_AGENT_HOME": str(home)}))
    assert [p.settings.desktop for p in again if p.id == "coach"] == [live]


def test_off_saved_from_the_web_is_written_as_the_word_and_takes_the_tools_away(crew):
    client, runtime, home = crew
    client.patch("/api/agents/coach", json={"profile": {"computer": "on"}})
    assert desktop_tools(runtime) == list(DESKTOP_TOOLS)

    reply = client.patch("/api/agents/coach", json={"profile": {"computer": "off"}})

    assert reply.status_code == 200, reply.text
    assert reply.json()["profile"]["computer"] == "off"
    assert read_at_start(home)["computer"] == "off"
    assert desktop_tools(runtime) == []


def test_clearing_the_two_keys_takes_them_out_of_the_file(crew):
    client, runtime, home = crew
    client.patch(
        "/api/agents/coach", json={"profile": {"computer": "on", "computer_apps": ["Notes"]}}
    )

    reply = client.patch(
        "/api/agents/coach", json={"profile": {"computer": None, "computer_apps": None}}
    )

    assert reply.status_code == 200, reply.text
    profile = reply.json()["profile"]
    assert (profile["computer"], profile["computer_apps"]) == ("off", [])
    assert "computer" not in read_at_start(home) and "computer_apps" not in read_at_start(home)
    assert desktop_tools(runtime) == []


def test_an_emptied_application_list_leaves_the_agent_looking_only(crew):
    client, runtime, home = crew
    client.patch(
        "/api/agents/coach", json={"profile": {"computer": "on", "computer_apps": ["Notes"]}}
    )

    reply = client.patch("/api/agents/coach", json={"profile": {"computer_apps": []}})

    assert reply.status_code == 200, reply.text
    assert reply.json()["profile"]["computer_apps"] == []
    assert read_at_start(home)["computer"] == "on"
    assert runtime.deps_for("coach").agent.settings.desktop.apps == ()


@pytest.mark.parametrize(
    "patch",
    [
        {"computer": True},
        {"computer": "act"},
        {"computer": "yes"},
        {"computer": 1},
        {"computer": ["on"]},
        {"computer_apps": "Notes"},
        {"computer_apps": [7]},
        {"computer_apps": [""]},
        {"computer_apps": ["Notes", None]},
        {"computer_apps": {"Notes": True}},
    ],
)
def test_a_bad_value_from_the_web_is_refused_and_the_file_is_left_alone(crew, patch):
    client, runtime, home = crew
    client.patch("/api/agents/coach", json={"profile": {"computer_apps": ["Notes"]}})
    before = (home / "agents" / "coach" / "agent.yaml").read_text(encoding="utf-8")

    reply = client.patch("/api/agents/coach", json={"profile": patch})

    assert reply.status_code == 422, reply.text
    assert (home / "agents" / "coach" / "agent.yaml").read_text(encoding="utf-8") == before
    live = runtime.deps_for("coach").agent.settings.desktop
    assert (live.mode, live.apps) == ("off", ("Notes",))
    assert desktop_tools(runtime) == []


def test_a_new_agent_may_be_made_with_the_two_keys(crew):
    client, runtime, _ = crew

    reply = client.post(
        "/api/agents",
        json={"agent_id": "desk", "profile": {"computer": "on", "computer_apps": ["Notes"]}},
    )

    assert reply.status_code in (200, 201), reply.text
    assert desktop_tools(runtime, "desk") == list(DESKTOP_TOOLS)
    assert desktop_tools(runtime, "default") == []
