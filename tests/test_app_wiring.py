"""build_runtime wires real settings into providers, tools, skills and agent profiles."""

from pathlib import Path

from my_agent_crew.config import load_settings
from my_agent_crew.server import build_deps, build_runtime
from my_agent_crew.server.runtime import PROVIDER_TIMEOUT_SECONDS


def env_for(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo", **extra}


def test_fake_provider_always_registered_and_openrouter_only_with_key(tmp_path: Path):
    without = build_deps(load_settings(env=env_for(tmp_path)))
    with_key = build_deps(load_settings(env=env_for(tmp_path, OPENROUTER_API_KEY="k")))
    assert set(without.chain.providers) == {"fake"}
    assert set(with_key.chain.providers) == {"fake", "openrouter"}


def test_web_search_tool_follows_search_key(tmp_path: Path):
    assert "web_search" not in build_deps(load_settings(env=env_for(tmp_path))).tools.names()
    with_key = build_deps(load_settings(env=env_for(tmp_path, TAVILY_API_KEY="k")))
    assert "web_search" in with_key.tools.names()


def test_home_skills_dir_is_loaded_and_shell_tool_present(tmp_path: Path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "mine.md").write_text("---\nname: mine\n---\nhello")
    deps = build_deps(load_settings(env=env_for(tmp_path)))
    assert "mine" in {s.name for s in deps.skills}
    assert deps.settings.workspace_dir.is_dir()
    assert "shell_run" in deps.tools.names()


def test_runtime_builds_one_deps_per_profile_with_own_workspace(tmp_path: Path):
    agent = tmp_path / "agents" / "coach"
    agent.mkdir(parents=True)
    (agent / "agent.yaml").write_text(
        "name: Coach\nroutes: [fake:echo]\ncost_cap_usd: 2\n"
        "schedules:\n  - id: brief\n    cron: '0 7 * * *'\n    prompt: hi\n"
    )
    (agent / "skills").mkdir()
    (agent / "skills" / "plan.md").write_text("---\nname: plan\n---\nplan body")
    rt = build_runtime(load_settings(env=env_for(tmp_path)))
    assert list(rt.agents) == ["default", "coach"]
    coach = rt.deps_for("coach")
    assert coach.agent.workspace == (agent / "workspace").resolve()
    assert coach.agent.workspace.is_dir() and coach.agent.memory_dir.is_dir()
    assert coach.settings.cost_cap_usd == 2 and rt.default.settings.cost_cap_usd == 0.5
    assert "plan" in {s.name for s in coach.skills}
    assert "plan" not in {s.name for s in rt.default.skills}
    assert [j.id for j in rt.scheduler.jobs()] == ["coach/brief"]
    assert rt.store is coach.store is rt.default.store


def test_profile_routes_without_a_key_fall_back_to_the_global_routes(tmp_path: Path):
    agent = tmp_path / "agents" / "coach"
    agent.mkdir(parents=True)
    (agent / "agent.yaml").write_text("name: Coach\nroutes: [openrouter:x, fake:echo]\n")
    (tmp_path / "agents" / "pong").mkdir()
    (tmp_path / "agents" / "pong" / "agent.yaml").write_text("name: Pong\nroutes: [openrouter:y]\n")
    rt = build_runtime(load_settings(env=env_for(tmp_path)))
    assert [f"{r.provider}:{r.model}" for r in rt.deps_for("coach").chain.routes] == ["fake:echo"]
    assert [f"{r.provider}:{r.model}" for r in rt.deps_for("pong").chain.routes] == ["fake:echo"]
    assert [f"{r.provider}:{r.model}" for r in rt.deps_for("pong").settings.routes] == ["fake:echo"]
    with_key = load_settings(env=env_for(tmp_path, OPENROUTER_API_KEY="k"))
    routes = build_runtime(with_key).deps_for("coach").chain.routes
    assert [f"{r.provider}:{r.model}" for r in routes] == ["openrouter:x", "fake:echo"]


def test_default_http_client_waits_as_long_as_the_provider_would(tmp_path: Path):
    deps = build_deps(load_settings(env=env_for(tmp_path, OPENROUTER_API_KEY="k")))
    client = deps.chain.providers["openrouter"]._client
    assert client.timeout.read == PROVIDER_TIMEOUT_SECONDS
    assert client.timeout.connect == PROVIDER_TIMEOUT_SECONDS


def test_telegram_channel_is_built_only_when_its_token_env_var_is_set(tmp_path: Path, caplog):
    agent = tmp_path / "agents" / "coach"
    agent.mkdir(parents=True)
    (agent / "agent.yaml").write_text(
        "name: Coach\nroutes: [fake:echo]\ntelegram:\n  token_env: COACH_BOT\n  chat_id: 42\n"
    )
    settings = load_settings(env=env_for(tmp_path))
    with caplog.at_level("WARNING"):
        without = build_runtime(settings, env=env_for(tmp_path))
    assert without.channels == {} and "COACH_BOT" in caplog.text
    rt = build_runtime(settings, env=env_for(tmp_path, COACH_BOT="1:abc"))
    assert list(rt.channels) == ["coach"] and rt.channels["coach"].chat_id == 42
    assert rt.deps_for("coach").agent.to_dict()["telegram"]["token_env"] == "COACH_BOT"
    assert "1:abc" not in str(rt.deps_for("coach").agent.to_dict())
