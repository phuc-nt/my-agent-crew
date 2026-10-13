"""The browser's settings: what the machine says in `config.yaml` or the environment, what one
agent says in its own file, and that a save from the web is read back as what was asked."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.config import Settings, load_settings
from my_agent_crew.config_browser import BrowserSettings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.texts_browser import DEFAULT_ASK_WORDS


def test_a_machine_has_no_browser_until_it_says_so(tmp_path: Path):
    browser = load_settings(env={"MY_AGENT_HOME": str(tmp_path)}).browser

    assert browser == BrowserSettings()
    assert (browser.enabled, browser.channel) == (False, "chromium")
    assert (browser.idle_minutes, browser.max_tabs) == (10, 5)
    assert browser.ask_patterns == DEFAULT_ASK_WORDS
    assert not browser.reads and not browser.acts


def test_the_file_sets_the_browser_and_the_environment_wins(tmp_path: Path):
    home = {"MY_AGENT_HOME": str(tmp_path)}
    (tmp_path / "config.yaml").write_text(
        "browser_enabled: true\nbrowser_channel: chrome\nbrowser_idle_minutes: 3\n"
        "browser_max_tabs: 2\nbrowser_ask_patterns: [trả tiền, ' pay now ']\n",
        encoding="utf-8",
    )

    from_file = load_settings(env=home).browser
    env = {
        **home,
        "MY_AGENT_BROWSER_ENABLED": "0",
        "MY_AGENT_BROWSER_CHANNEL": "chromium",
        "MY_AGENT_BROWSER_IDLE_MINUTES": "7",
        "MY_AGENT_BROWSER_MAX_TABS": "9",
        "MY_AGENT_BROWSER_ASK_PATTERNS": "mua; pay",
    }
    from_env = load_settings(env=env).browser

    assert from_file == BrowserSettings(
        enabled=True,
        channel="chrome",
        idle_minutes=3,
        max_tabs=2,
        ask_patterns=("trả tiền", "pay now"),
    )
    assert from_env == BrowserSettings(
        enabled=False, channel="chromium", idle_minutes=7, max_tabs=9, ask_patterns=("mua", "pay")
    )


def test_an_emptied_ask_list_turns_the_soft_guard_off_on_purpose(tmp_path: Path):
    home = {"MY_AGENT_HOME": str(tmp_path)}
    emptied = load_settings(env={**home, "MY_AGENT_BROWSER_ASK_PATTERNS": ""})
    assert emptied.browser.ask_patterns == ()
    (tmp_path / "config.yaml").write_text("browser_ask_patterns: []\n", encoding="utf-8")
    assert load_settings(env=home).browser.ask_patterns == ()


@pytest.mark.parametrize(
    ("line", "said"),
    [
        ("browser_channel: firefox", "browser_channel must be chromium or chrome"),
        ("browser_idle_minutes: 0", "must be >= 1"),
        ("browser_max_tabs: 0", "must be >= 1"),
        ("browser_profile: /tmp/x", "unknown keys ['browser_profile']"),
    ],
)
def test_a_browser_setting_nobody_knows_stops_the_start(tmp_path: Path, line: str, said: str):
    (tmp_path / "config.yaml").write_text(line + "\n", encoding="utf-8")

    with pytest.raises(ValueError) as refusal:
        load_settings(env={"MY_AGENT_HOME": str(tmp_path)})

    assert said in str(refusal.value)


def on(settings: Settings) -> Settings:
    from dataclasses import replace

    return replace(settings, browser=replace(settings.browser, enabled=True))


def parsed(settings: Settings, tmp_path: Path, text: str) -> BrowserSettings:
    """What the start reads from an `agent.yaml` written by hand."""
    raw = yaml.safe_load(text) or {}
    return parse_profile("shop", tmp_path / "agents" / "shop", raw, settings).settings.browser


def test_an_agent_reads_or_acts_only_where_its_own_file_says_so(settings, tmp_path):
    machine = on(settings)

    silent = parsed(machine, tmp_path, "name: Shop\n")
    reads = parsed(machine, tmp_path, "browser: read\n")
    hosts = "browser_hosts: [shop.example, '*.pay.example']\n"
    acts = parsed(machine, tmp_path, "browser: act\n" + hosts)

    assert (silent.mode, silent.reads, silent.acts) == ("off", False, False)
    assert (reads.mode, reads.reads, reads.acts) == ("read", True, False)
    assert (acts.mode, acts.reads, acts.acts) == ("act", True, True)
    assert acts.hosts == ("shop.example", "*.pay.example")
    # What the machine set is the agent's too; only the two keys are its own.
    assert acts.ask_patterns == machine.browser.ask_patterns


def test_an_agent_file_cannot_turn_on_a_browser_the_machine_has_not(settings, tmp_path):
    acts = parsed(settings, tmp_path, "browser: act\n")

    assert acts.mode == "act"
    assert not acts.reads and not acts.acts


def test_the_mode_is_never_inherited_from_the_settings_an_agent_starts_from(settings, tmp_path):
    from dataclasses import replace

    base = replace(
        settings,
        browser=replace(settings.browser, enabled=True, mode="act", hosts=("shop.example",)),
    )

    silent = parsed(base, tmp_path, "name: Shop\n")

    assert (silent.mode, silent.hosts) == ("off", ())


@pytest.mark.parametrize("word", ["off", "no", "false", "Off", "~", ""])
def test_a_bare_yaml_off_means_off(settings, tmp_path, word):
    assert parsed(on(settings), tmp_path, f"browser: {word}\n").mode == "off"


@pytest.mark.parametrize("word", ["on", "yes", "true"])
def test_a_bare_yaml_on_is_refused_because_it_does_not_say_how_far(settings, tmp_path, word):
    with pytest.raises(ValueError) as refusal:
        parsed(on(settings), tmp_path, f"browser: {word}\n")

    assert "write read to let it open and read pages" in str(refusal.value)


@pytest.mark.parametrize("text", ["browser: write\n", "browser: [read]\n", "browser: 1\n"])
def test_a_mode_nobody_knows_is_refused(settings, tmp_path, text):
    with pytest.raises(ValueError, match="browser must be off, read or act"):
        parsed(on(settings), tmp_path, text)


@pytest.mark.parametrize(
    "hosts",
    [
        "shop.example",
        "[https://shop.example]",
        "[shop.example/orders]",
        "['shop.example:8443']",
        "[Shop.Example]",
        "['*shop.example']",
        "['shop.*.example']",
        "['*']",
        "[cửa-hàng.vn]",
        "[12]",
        "[shop.example, '']",
    ],
)
def test_a_host_list_holds_only_host_names(settings, tmp_path, hosts):
    with pytest.raises(ValueError, match="browser_hosts must be a list of host names"):
        parsed(on(settings), tmp_path, f"browser: act\nbrowser_hosts: {hosts}\n")


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.yaml").write_text("browser_enabled: true\n", encoding="utf-8")
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        client.post("/api/agents", json={"agent_id": "shop", "profile": {"name": "Shop"}})
        yield client, runtime, home


def read_at_start(home: Path) -> dict:
    return yaml.safe_load((home / "agents" / "shop" / "agent.yaml").read_text(encoding="utf-8"))


def test_a_save_from_the_web_is_what_the_next_start_reads(crew):
    client, runtime, home = crew

    reply = client.patch(
        "/api/agents/shop",
        json={"profile": {"browser": "act", "browser_hosts": ["shop.example", "*.pay.example"]}},
    )

    assert reply.status_code == 200, reply.text
    profile = reply.json()["profile"]
    assert (profile["browser"], profile["browser_hosts"]) == (
        "act",
        ["shop.example", "*.pay.example"],
    )
    assert reply.json()["restart_required"] == []
    live = runtime.deps_for("shop").agent.settings.browser
    assert (live.mode, live.hosts, live.acts) == ("act", ("shop.example", "*.pay.example"), True)
    assert read_at_start(home)["browser"] == "act"
    assert read_at_start(home)["browser_hosts"] == ["shop.example", "*.pay.example"]


def test_off_saved_from_the_web_is_written_as_the_word_and_not_as_a_switch(crew):
    client, runtime, home = crew
    client.patch("/api/agents/shop", json={"profile": {"browser": "read"}})

    reply = client.patch("/api/agents/shop", json={"profile": {"browser": "off"}})

    assert reply.status_code == 200, reply.text
    assert reply.json()["profile"]["browser"] == "off"
    # PyYAML, which reads the file at the start, takes a bare `off` for False: the word is
    # kept in quotes so the file says what the person chose.
    assert read_at_start(home)["browser"] == "off"
    assert runtime.deps_for("shop").agent.settings.browser.mode == "off"


def test_clearing_the_two_keys_takes_them_out_of_the_file(crew):
    client, _, home = crew
    client.patch(
        "/api/agents/shop", json={"profile": {"browser": "act", "browser_hosts": ["a.example"]}}
    )

    cleared = {"browser": None, "browser_hosts": None}
    reply = client.patch("/api/agents/shop", json={"profile": cleared})

    assert reply.status_code == 200, reply.text
    assert (reply.json()["profile"]["browser"], reply.json()["profile"]["browser_hosts"]) == (
        "off",
        [],
    )
    assert "browser" not in read_at_start(home) and "browser_hosts" not in read_at_start(home)


@pytest.mark.parametrize(
    "patch",
    [
        {"browser": "write"},
        {"browser": True},
        {"browser_hosts": "shop.example"},
        {"browser_hosts": ["https://shop.example"]},
        {"browser_hosts": [7]},
    ],
)
def test_a_bad_value_from_the_web_is_refused_and_the_file_is_left_alone(crew, patch):
    client, runtime, home = crew
    before = (home / "agents" / "shop" / "agent.yaml").read_text(encoding="utf-8")

    reply = client.patch("/api/agents/shop", json={"profile": patch})

    assert reply.status_code == 422, reply.text
    assert (home / "agents" / "shop" / "agent.yaml").read_text(encoding="utf-8") == before
    assert runtime.deps_for("shop").agent.settings.browser.mode == "off"
