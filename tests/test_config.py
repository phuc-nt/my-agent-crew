from pathlib import Path

import pytest

from my_agent_crew.config import DEFAULT_ROUTES, Route, ensure_home, load_settings


def test_defaults_without_env(tmp_path: Path):
    s = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    assert s.routes == (Route.parse(DEFAULT_ROUTES),)
    assert s.language == "vi"
    assert s.cost_cap_usd == 0.5
    assert s.openrouter_api_key is None
    assert s.workspace_dir == tmp_path / "workspace"
    assert s.db_path == tmp_path / "agent.sqlite3"


def test_routes_from_env_in_order(tmp_path: Path):
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "openrouter:a/b, fake:echo"}
    s = load_settings(env=env)
    assert s.routes == (Route("openrouter", "a/b"), Route("fake", "echo"))


def test_route_parse_rejects_missing_model():
    with pytest.raises(ValueError):
        Route.parse("openrouter")


def test_yaml_overrides_defaults_but_env_wins(tmp_path: Path):
    (tmp_path / "config.yaml").write_text(
        "routes: [fake:echo]\ncost_cap_usd: 2\nlanguage: en\nmax_steps: 3\n"
    )
    s = load_settings(env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_COST_CAP_USD": "9"})
    assert s.routes == (Route("fake", "echo"),)
    assert s.cost_cap_usd == 9.0
    assert s.language == "en"
    assert s.max_steps == 3


def test_yaml_unknown_key_is_an_error(tmp_path: Path):
    (tmp_path / "config.yaml").write_text("openrouter_api_key: sk-nope\n")
    with pytest.raises(ValueError, match="openrouter_api_key"):
        load_settings(env={"MY_AGENT_HOME": str(tmp_path)})


def test_secrets_only_from_env(tmp_path: Path):
    env = {
        "MY_AGENT_HOME": str(tmp_path),
        "OPENROUTER_API_KEY": "k1",
        "BRAVE_API_KEY": "k2",
        "MY_AGENT_AUTONOMOUS": "true",
    }
    s = load_settings(env=env)
    assert (s.openrouter_api_key, s.brave_api_key, s.autonomous_default) == ("k1", "k2", True)


def test_ensure_home_creates_dirs(tmp_path: Path):
    s = load_settings(env={"MY_AGENT_HOME": str(tmp_path / "h")})
    ensure_home(s)
    assert s.workspace_dir.is_dir() and s.skills_dir.is_dir()
