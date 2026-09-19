"""build_deps wires real settings into providers, tools and skills."""

from pathlib import Path

from my_agent_crew.config import load_settings
from my_agent_crew.server import build_deps


def test_fake_provider_always_registered_and_openrouter_only_with_key(tmp_path: Path):
    base = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    without = build_deps(load_settings(env=base))
    with_key = build_deps(load_settings(env={**base, "OPENROUTER_API_KEY": "k"}))
    assert set(without.chain.providers) == {"fake"}
    assert set(with_key.chain.providers) == {"fake", "openrouter"}


def test_web_search_tool_follows_search_key(tmp_path: Path):
    base = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    assert "web_search" not in build_deps(load_settings(env=base)).tools.names()
    with_key = build_deps(load_settings(env={**base, "TAVILY_API_KEY": "k"}))
    assert "web_search" in with_key.tools.names()


def test_home_skills_dir_is_loaded(tmp_path: Path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "mine.md").write_text("---\nname: mine\n---\nhello")
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    deps = build_deps(load_settings(env=env))
    assert "mine" in {s.name for s in deps.skills}
    assert deps.settings.workspace_dir.is_dir()
