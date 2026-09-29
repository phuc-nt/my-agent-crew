"""The throwaway copy of the live home the behaviour evals run on: what it leaves behind,
what it keeps, and the checks that keep it from reaching the live tree."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import yaml
from eval_copy import remove_tree
from eval_home import EvalHome, build_home, synthetic_home

from my_agent_crew.agents.kit_agents import load_profiles
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.config import load_settings

GIT = ".git"
LOGINS = (
    "Cookies",
    "Cookies-journal",
    "cookies.txt",
    "Trust Tokens",
    "Trust Tokens-journal",
    "Login Data",
    "client_secret_123.json",
    "id_rsa",
    "id_ed25519",
    "tls.pem",
    "signing.key",
    "cert.p12",
    "cert.pfx",
    "vault.kdbx",
)
LOOK_ALIKES = ("cookies-policy.md", "monkey.txt", "keys.md", "login.py", "trust.md")


@dataclass
class Live:
    home: Path
    ws: Path  # the coach's workspace: absolute in its manifest, outside the home
    other: Path  # a directory the crew does not own
    out: Path


def put(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def manifest(path: Path, **raw: Any) -> None:
    put(path, yaml.safe_dump(raw))


def write_coach(live: Live, **overrides: Any) -> None:
    raw: dict[str, Any] = {
        "name": "Coach",
        "workspace": str(live.ws),
        "skills_dirs": [str(live.ws / "skills")],
        "persona_files": ["AGENTS.md", "SOUL.md"],
        "telegram": {"token_env": "COACH_BOT_TOKEN", "chat_id": 22},
        "schedules": [
            {
                "id": "report",
                "cron": "0 8 * * *",
                "command": f"python3 {live.ws}/scripts/report.py",
            }
        ],
        "memory_consolidate": "30 3 * * *",
    }
    raw.update(overrides)
    manifest(live.home / "agents" / "coach" / "agent.yaml", **raw)


def make_live(tmp_path: Path) -> Live:
    live = Live(
        home=tmp_path / "live-home",
        ws=tmp_path / "elsewhere" / "coach-ws",
        other=tmp_path / "elsewhere" / "other",
        out=tmp_path / "run",
    )
    home, ws = live.home, live.ws
    for name in ("env", ".env.local", "agent.sqlite3", "agent.sqlite3-wal", "agent.sqlite3-shm"):
        put(home / name, "OPENROUTER_API_KEY=live-secret")
    for name in ("backups/old.db", "logs/server.log", "telegram.offset", "channels/t.offset"):
        put(home / name)
    for name in ("run-server.zsh", "evals/case.yaml", "spill/out.txt", f"{GIT}/HEAD"):
        put(home / name)
    put(home / "config.yaml", "timezone: Asia/Ho_Chi_Minh\n")
    put(home / "AGENTS.md", "master persona")
    put(home / "workspace" / "notes.txt", "hello")
    put(home / ".agents" / "commands" / "wrap.md", "---\ndescription: wrap up\n---\nbody")
    put(home / ".claude" / "skills" / "crew-skill" / "SKILL.md", "---\nname: crew-skill\n---\nx")
    manifest(
        home / "agent.yaml",
        name="Master",
        telegram={"token_env": "MASTER_BOT_TOKEN", "chat_id": 11},
        schedules=[{"id": "brief", "cron": "0 7 * * *", "prompt": "Say hello"}],
        memory_consolidate="0 3 * * *",
    )
    write_coach(live)
    for name in ("AGENTS.md", "SOUL.md", "memory/MEMORY.md", ".claude/skills/own/SKILL.md"):
        put(home / "agents" / "coach" / name, "coach " + name)
    manifest(home / "agents" / "helper" / "agent.yaml", name="Helper", workspace=str(ws))
    manifest(
        home / "agents" / "plain" / "agent.yaml",
        name="Plain",
        persona_files=["AGENTS.md", "docs/extra.md"],
        skills_dirs=["extra-skills"],
    )
    for name in ("AGENTS.md", "docs/extra.md", "extra-skills/x/SKILL.md"):
        put(home / "agents" / "plain" / name)
    for name in ("notes.md", "skills/s.md", "scripts/report.py", "data/data.db"):
        put(ws / name)
    for name in ("data/data.db-wal", "data/data.db-shm"):
        put(ws / name, "journal")
    for name in (
        f"{GIT}/HEAD",
        ".venv/bin/python",
        "node_modules/pkg/index.js",
        "pkg/__pycache__/a.pyc",
        ".env",
        ".env.production",
        ".claude/settings.json",
        ".agents/x.md",
        ".opencode/y.md",
    ):
        put(ws / name)
    put(live.other / "persona.md", "not the crew's")
    return live


def loaded(built: EvalHome) -> list[AgentProfile]:
    return load_profiles(load_settings({"MY_AGENT_HOME": str(built.home)}))


def workspace_of(built: EvalHome, agent: str) -> Path:
    raw = yaml.safe_load((built.home / "agents" / agent / "agent.yaml").read_text())
    return Path(raw["workspace"])


def snapshot(*roots: Path) -> dict[str, tuple[int, int, int, str]]:
    seen = {}
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for name in dirnames + filenames:
                path = Path(dirpath) / name
                stat = path.lstat()
                is_file = path.is_file() and not path.is_symlink()
                digest = hashlib.sha1(path.read_bytes()).hexdigest() if is_file else ""
                seen[str(path)] = (stat.st_mode, stat.st_size, stat.st_mtime_ns, digest)
    return seen


def strings_in(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings_in(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings_in(v)]
    return []


def test_the_copy_leaves_out_secrets_state_databases_and_history(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    left_out = (
        "env",
        ".env.local",
        "agent.sqlite3",
        "agent.sqlite3-wal",
        "agent.sqlite3-shm",
        "backups",
        "logs",
        "telegram.offset",
        "channels",
        "run-server.zsh",
        "evals",
        "spill",
        GIT,
    )
    assert [n for n in left_out if os.path.lexists(built.home / n)] == []
    assert built.home == live.out.resolve() / "home"
    assert built.root == live.out.resolve()


def test_the_copy_keeps_config_persona_memory_workspace_files_and_databases(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    assert (built.home / "config.yaml").read_text() == "timezone: Asia/Ho_Chi_Minh\n"
    assert (built.home / "AGENTS.md").read_text() == "master persona"
    assert (built.home / "workspace" / "notes.txt").read_text() == "hello"
    assert (built.home / "agents" / "coach" / "memory" / "MEMORY.md").is_file()
    assert (built.home / ".agents" / "commands" / "wrap.md").is_file()
    coach_ws = workspace_of(built, "coach")
    for name in ("notes.md", "skills/s.md", "data/data.db", "data/data.db-wal", "data/data.db-shm"):
        assert (coach_ws / name).is_file(), name


def test_a_workspace_loses_its_git_dir_environments_dependencies_secrets_and_kits(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    coach_ws = workspace_of(built, "coach")
    dropped = (
        GIT,
        ".venv",
        "node_modules",
        "pkg/__pycache__",
        ".env",
        ".env.production",
        ".claude",
        ".agents",
        ".opencode",
    )
    assert [n for n in dropped if os.path.lexists(coach_ws / n)] == []


def test_what_holds_a_login_is_left_out_and_counted_but_look_alikes_stay(tmp_path):
    live = make_live(tmp_path)
    for name in LOGINS + LOOK_ALIKES:
        put(live.ws / name)
    site = live.home / "skills-personal" / "site"
    put(site / ".browser-data" / "Default" / "Cookies")
    put(site / "run.sh")

    built = build_home(live.home, live.out)

    coach_ws = workspace_of(built, "coach")
    assert [n for n in LOGINS if os.path.lexists(coach_ws / n)] == []
    assert [n for n in LOOK_ALIKES if not (coach_ws / n).is_file()] == []
    copied = built.home / "skills-personal" / "site"
    assert (copied / "run.sh").is_file()
    assert not os.path.lexists(copied / ".browser-data")
    said = f"{len(LOGINS) + 1} cookie, key or browser-profile entries not copied"
    assert any(said in warning for warning in built.warnings)


def test_a_kit_directly_under_the_home_or_an_agent_is_kept_because_the_crew_reads_it(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    assert (built.home / ".claude" / "skills" / "crew-skill" / "SKILL.md").is_file()
    assert (built.home / "agents" / "coach" / ".claude" / "skills" / "own" / "SKILL.md").is_file()
    coach = next(p for p in loaded(built) if p.id == "coach")
    assert built.home / ".claude" / "skills" in coach.skills_dirs
    assert built.home / "agents" / "coach" / ".claude" / "skills" in coach.skills_dirs


def test_symlinks_are_neither_copied_nor_followed_and_the_report_says_so(tmp_path):
    live = make_live(tmp_path)
    put(live.other / "secret-dir" / "s.txt", "secret")
    os.symlink(live.other / "secret-dir", live.ws / "link-dir")
    os.symlink(live.other / "persona.md", live.ws / "link-file")

    built = build_home(live.home, live.out)

    coach_ws = workspace_of(built, "coach")
    assert not os.path.lexists(coach_ws / "link-dir")
    assert not os.path.lexists(coach_ws / "link-file")
    assert any("2 symlinks" in warning for warning in built.warnings)


def test_the_copy_loads_with_the_real_loaders_and_every_path_stays_inside_the_run_dir(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    profiles = loaded(built)
    assert [p.id for p in profiles] == ["default", "coach", "helper", "plain"]
    for profile in profiles:
        paths = [profile.workspace, *profile.skills_dirs]
        paths += [profile.dir / name for name in profile.persona_files]
        outside = [p for p in paths if not p.resolve().is_relative_to(built.root)]
        assert outside == [], profile.id


def test_no_agent_of_the_copy_has_a_schedule_a_consolidation_or_a_telegram_bot(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    for profile in loaded(built):
        assert profile.schedules == (), profile.id
        assert profile.telegram is None, profile.id
        assert profile.memory_consolidate == "", profile.id


def test_no_agent_of_the_copy_lets_a_shell_command_run_unasked(tmp_path):
    live = make_live(tmp_path)
    put(
        live.home / "config.yaml",
        "timezone: Asia/Ho_Chi_Minh\nshell_allow_patterns: [git status]\n",
    )
    write_coach(live, shell_allow_patterns=[f"python3 {live.ws}/scripts/report.py"])
    live_crew = load_profiles(load_settings({"MY_AGENT_HOME": str(live.home)}))
    assert all(p.settings.shell_allow_patterns for p in live_crew)

    built = build_home(live.home, live.out)

    for profile in loaded(built):
        assert profile.settings.shell_allow_patterns == (), profile.id
    assert "shell_allow_patterns" not in (built.home / "config.yaml").read_text()
    raw = yaml.safe_load((built.home / "agents" / "coach" / "agent.yaml").read_text())
    assert "shell_allow_patterns" not in raw


def test_no_string_in_a_copied_manifest_names_the_live_home_or_a_live_workspace(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    manifests = [built.home / "agent.yaml", *(built.home / "agents").glob("*/agent.yaml")]
    assert len(manifests) == 4
    for path in manifests:
        for text in strings_in(yaml.safe_load(path.read_text())):
            assert str(live.home) not in text, path
            assert str(live.ws) not in text, path


def test_persona_files_that_exist_live_exist_in_the_copy(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    for profile in loaded(built):
        live_profile = next(
            p
            for p in load_profiles(load_settings({"MY_AGENT_HOME": str(live.home)}))
            if p.id == profile.id
        )
        present = [(p.dir / n).exists() for p in (live_profile, profile) for n in p.persona_files]
        half = len(present) // 2
        assert present[:half] == present[half:], profile.id


def test_paths_that_stay_inside_an_agent_dir_stay_as_written_and_absolute_ones_move(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    plain = yaml.safe_load((built.home / "agents" / "plain" / "agent.yaml").read_text())
    assert plain["persona_files"] == ["AGENTS.md", "docs/extra.md"]
    assert plain["skills_dirs"] == ["extra-skills"]
    coach = yaml.safe_load((built.home / "agents" / "coach" / "agent.yaml").read_text())
    assert coach["persona_files"] == ["AGENTS.md", "SOUL.md"]
    assert Path(coach["workspace"]).is_relative_to(built.root / "ws")
    assert all(Path(d).is_relative_to(built.root / "ws") for d in coach["skills_dirs"])


def test_agents_that_share_a_workspace_share_one_copy_of_it(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    assert workspace_of(built, "helper") == workspace_of(built, "coach")
    assert [p.name for p in (built.root / "ws").iterdir()] == ["coach-ws"]


def test_workspaces_with_the_same_name_get_their_own_copies(tmp_path):
    live = make_live(tmp_path)
    twin = tmp_path / "another" / "coach-ws"
    put(twin / "twin.md", "twin")
    manifest(live.home / "agents" / "helper" / "agent.yaml", name="Helper", workspace=str(twin))

    built = build_home(live.home, live.out)

    assert sorted(p.name for p in (built.root / "ws").iterdir()) == ["coach-ws", "coach-ws-2"]
    assert (workspace_of(built, "helper") / "twin.md").read_text() == "twin"
    assert (workspace_of(built, "coach") / "notes.md").is_file()


def test_the_bot_tokens_the_live_profiles_name_are_reported_to_keep_out_of_the_server(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    assert built.token_envs == ("COACH_BOT_TOKEN", "MASTER_BOT_TOKEN")


def test_the_live_paths_are_reported_for_the_approval_guard(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    assert set(built.live_paths) == {str(live.home), str(live.ws)}


def test_a_manifest_string_that_still_names_a_live_path_is_reported_not_rewritten(tmp_path):
    live = make_live(tmp_path)
    write_coach(live, shell_ask_patterns=[f"cat {live.ws}/data/"])

    built = build_home(live.home, live.out)

    assert any(
        "agents/coach/agent.yaml" in warning and f"cat {live.ws}/data/" in warning
        for warning in built.warnings
    )
    raw = yaml.safe_load((built.home / "agents" / "coach" / "agent.yaml").read_text())
    assert raw["shell_ask_patterns"] == [f"cat {live.ws}/data/"]


def test_a_config_string_that_names_a_live_path_is_reported_too(tmp_path):
    live = make_live(tmp_path)
    put(live.home / "config.yaml", f"shell_ask_patterns: ['cat {live.ws}/data/']\n")

    built = build_home(live.home, live.out)

    assert any(
        "config.yaml" in warning and f"cat {live.ws}/data/" in warning for warning in built.warnings
    )


@pytest.mark.parametrize("key", ["skills_dirs", "persona_files"])
def test_a_path_key_that_leaves_the_home_and_the_workspaces_is_refused_by_file_and_key(
    tmp_path, key
):
    live = make_live(tmp_path)
    outside = live.other / ("persona.md" if key == "persona_files" else "skills")
    write_coach(live, **{key: [str(outside)]})

    with pytest.raises(ValueError) as refused:
        build_home(live.home, live.out)

    message = str(refused.value)
    assert "agents/coach/agent.yaml" in message
    assert key in message
    assert not (live.out / "home").exists()


def test_a_kit_agent_working_outside_the_home_is_refused_before_anything_is_copied(tmp_path):
    live = make_live(tmp_path)
    put(
        live.home / ".agents" / "agents" / "scout.md",
        f"---\nname: scout\ndescription: looks around\nworkspace: {live.other}\n---\nYou scout.",
    )

    with pytest.raises(ValueError, match="scout"):
        build_home(live.home, live.out)

    assert not (live.out / "home").exists()


def test_a_run_dir_inside_the_live_home_or_a_workspace_is_refused(tmp_path):
    live = make_live(tmp_path)

    for inside in (live.home / "run", live.ws / "run"):
        with pytest.raises(ValueError, match="inside"):
            build_home(live.home, inside)


def test_an_existing_copy_is_never_overwritten(tmp_path):
    live = make_live(tmp_path)
    put(live.out / "home" / "keep.txt", "mine")

    with pytest.raises(ValueError, match="already exists"):
        build_home(live.home, live.out)

    assert (live.out / "home" / "keep.txt").read_text() == "mine"


def test_a_missing_live_home_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no such home"):
        build_home(tmp_path / "nowhere", tmp_path / "run")


def test_the_live_tree_is_left_exactly_as_it_was(tmp_path):
    live = make_live(tmp_path)
    before = snapshot(live.home, live.ws.parent)

    build_home(live.home, live.out)

    assert snapshot(live.home, live.ws.parent) == before


def test_the_run_dir_is_private_to_its_owner(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    assert built.root.stat().st_mode & 0o077 == 0


def test_the_file_count_and_size_are_those_of_the_copy(tmp_path):
    live = make_live(tmp_path)

    built = build_home(live.home, live.out)

    walked = [Path(d) / f for d, _, names in os.walk(built.root) for f in names]
    assert built.files == len(walked)
    assert built.size_bytes == sum(p.stat().st_size for p in walked)


def test_a_synthetic_home_loads_with_the_fake_route_and_nothing_of_the_live_crew(tmp_path):
    built = synthetic_home(tmp_path / "run")

    settings = load_settings({"MY_AGENT_HOME": str(built.home)})

    assert [(r.provider, r.model) for r in settings.routes] == [("fake", "echo")]
    assert [p.id for p in load_profiles(settings)] == ["default"]
    assert built.token_envs == ()
    assert built.live_paths == ()
    assert built.root == (tmp_path / "run").resolve()


def test_a_skills_dir_that_only_lived_under_a_dropped_kit_is_reported_as_missing(tmp_path):
    live = make_live(tmp_path)
    hidden = live.ws / ".claude" / "skills"
    put(hidden / "hidden" / "SKILL.md", "---\nname: hidden\n---\nx")
    write_coach(live, skills_dirs=[str(hidden)])

    built = build_home(live.home, live.out)

    assert any(
        "coach" in warning and str(hidden) in warning and "not in the copy" in warning
        for warning in built.warnings
    )


def test_a_workspace_that_does_not_exist_live_becomes_an_empty_directory_with_a_warning(tmp_path):
    live = make_live(tmp_path)
    gone = tmp_path / "elsewhere" / "gone-ws"
    manifest(live.home / "agents" / "helper" / "agent.yaml", name="Helper", workspace=str(gone))

    built = build_home(live.home, live.out)

    assert list(workspace_of(built, "helper").iterdir()) == []
    assert any(str(gone) in warning and "does not exist" in warning for warning in built.warnings)


def test_a_workspace_inside_another_is_served_by_the_outer_copy(tmp_path):
    live = make_live(tmp_path)
    inner = live.ws / "sub" / "inner"
    put(inner / "deep.md", "deep")
    manifest(live.home / "agents" / "helper" / "agent.yaml", name="Helper", workspace=str(inner))

    built = build_home(live.home, live.out)

    assert [p.name for p in (built.root / "ws").iterdir()] == ["coach-ws"]
    assert workspace_of(built, "helper") == workspace_of(built, "coach") / "sub" / "inner"
    assert (workspace_of(built, "helper") / "deep.md").read_text() == "deep"


def test_a_workspace_that_contains_the_live_home_is_refused_before_anything_is_made(tmp_path):
    live = make_live(tmp_path)
    manifest(live.home / "agents" / "helper" / "agent.yaml", name="Helper", workspace=str(tmp_path))

    with pytest.raises(ValueError, match="contains the live home"):
        build_home(live.home, live.out)

    assert not live.out.exists()


def test_a_workspace_that_is_the_users_home_directory_is_refused(tmp_path, monkeypatch):
    live = make_live(tmp_path)
    user_home = tmp_path / "user-home"
    user_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    manifest(
        live.home / "agents" / "helper" / "agent.yaml", name="Helper", workspace=str(user_home)
    )

    with pytest.raises(ValueError, match="your home directory"):
        build_home(live.home, live.out)

    assert not live.out.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_a_copy_that_fails_midway_removes_what_it_made_and_keeps_what_was_already_there(tmp_path):
    live = make_live(tmp_path)
    put(live.out / "keep.txt", "mine")
    locked = put(live.ws / "locked.txt")
    locked.chmod(0)
    try:
        with pytest.raises(ValueError, match="could not copy"):
            build_home(live.home, live.out)
    finally:
        locked.chmod(0o600)

    assert sorted(p.name for p in live.out.iterdir()) == ["keep.txt"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_a_copy_that_fails_in_a_fresh_run_dir_leaves_no_run_dir_behind(tmp_path):
    live = make_live(tmp_path)
    locked = put(live.ws / "locked.txt")
    locked.chmod(0)
    try:
        with pytest.raises(ValueError, match="could not copy"):
            build_home(live.home, live.out)
    finally:
        locked.chmod(0o600)

    assert not live.out.exists()


def test_remove_tree_deletes_a_copy_that_holds_read_only_directories(tmp_path):
    tree = tmp_path / "copy"
    put(tree / "a" / "b" / "f.txt")
    (tree / "a" / "b").chmod(0o500)
    (tree / "a").chmod(0o500)

    remove_tree(tree)

    assert not tree.exists()


def test_remove_tree_unlinks_a_symlink_and_ignores_a_missing_path(tmp_path):
    kept = put(tmp_path / "target" / "keep.txt")
    link = tmp_path / "link"
    os.symlink(kept.parent, link)

    remove_tree(link)
    remove_tree(tmp_path / "missing")

    assert not os.path.lexists(link)
    assert kept.is_file()
