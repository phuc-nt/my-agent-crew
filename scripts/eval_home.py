"""The throwaway home the behaviour evals run on.

`build_home` copies the live crew's home and the workspaces its agents work in into a run
directory, and rewrites every path in the copied manifests to stay inside it, so an eval
server can act without touching the live tree. The copy has no secrets file, no crew
database, no history and no version control; no agent of it has a schedule, a Telegram bot
or a shell allow list.

What it cannot do is rewrite a shell pattern or a prompt that spells a live path out: those
are reported as warnings, and the runner refuses an approval that names one."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from eval_copy import copy_trees, count_tree, remove_tree
from eval_layout import (
    Mapping,
    check_run_dir,
    copy_dirs,
    external_roots,
    map_path,
    plan_manifests,
    refuse_kit_agents_outside,
)

from my_agent_crew.agents.kit_agents import load_profiles
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.agents.profile_yaml import load_yaml_profiles
from my_agent_crew.config import load_settings


@dataclass(frozen=True)
class EvalHome:
    root: Path  # the run directory: HOME of the eval server, so `~` reaches nothing live
    home: Path  # MY_AGENT_HOME of the eval server
    token_envs: tuple[str, ...]  # bot-token variables the live agents name; keep them out
    files: int = 0
    size_bytes: int = 0
    warnings: tuple[str, ...] = ()
    live_paths: tuple[str, ...] = ()  # what an approved command must not name


def synthetic_home(out: Path) -> EvalHome:
    """One `default` agent on the fake route: for `--dry-run` and for tests."""
    root = Path(out).expanduser().resolve()
    home = root / "home"
    if home.exists():
        raise ValueError(f"{home} already exists; a copy never overwrites another")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    home.mkdir(mode=0o700)
    (home / "config.yaml").write_text("routes: fake:echo\n", encoding="utf-8")
    files, size = count_tree(root)
    return EvalHome(root=root, home=home, token_envs=(), files=files, size_bytes=size)


def build_home(live_home: Path, out: Path) -> EvalHome:
    live = Path(live_home).expanduser().resolve()
    if not live.is_dir():
        raise ValueError(f"no such home: {live}")
    root = Path(out).expanduser().resolve()
    settings = load_settings({"MY_AGENT_HOME": str(live)})
    yaml_profiles = load_yaml_profiles(settings)
    crew = load_profiles(settings)
    refuse_kit_agents_outside(crew, {p.id for p in yaml_profiles}, live)
    externals = external_roots([p.workspace for p in yaml_profiles], live)
    check_run_dir(root, [live, *externals])
    home, ws = root / "home", root / "ws"
    for taken in (home, ws):
        if taken.exists():
            raise ValueError(f"{taken} already exists; a copy never overwrites another")
    mapping: Mapping = [(live, home), *zip(externals, copy_dirs(externals, ws), strict=True)]
    live_paths = tuple(str(p) for p in (live, *externals))
    manifests, tokens, warnings = plan_manifests(live, mapping, live_paths)
    fresh = not root.exists()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        left = copy_trees(live, home, mapping[1:], warnings)
        for rel, raw in manifests:
            text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)
            (home / rel).write_text(text, encoding="utf-8")
        warnings += _verify(root, home, crew, mapping)
        if left.links:
            noun = "symlink" if left.links == 1 else "symlinks"
            warnings.append(
                f"{left.links} {noun} not copied: a link could lead back to the live tree"
            )
        if left.logins:
            warnings.append(
                f"{left.logins} cookie, key or browser-profile entries not copied: "
                "no case needs a login"
            )
        files, size = count_tree(root)
    except BaseException:
        for made in (home, ws):
            remove_tree(made)
        if fresh:
            with contextlib.suppress(OSError):
                root.rmdir()
        raise
    return EvalHome(
        root=root,
        home=home,
        token_envs=tuple(sorted(tokens)),
        files=files,
        size_bytes=size,
        warnings=tuple(warnings),
        live_paths=live_paths,
    )


def _verify(
    root: Path, home: Path, live_crew: Sequence[AgentProfile], mapping: Mapping
) -> list[str]:
    """Load the copy the way the server will and prove it cannot reach the live tree."""
    crew = load_profiles(load_settings({"MY_AGENT_HOME": str(home)}))
    live_ids, ids = [p.id for p in live_crew], [p.id for p in crew]
    if ids != live_ids:
        raise ValueError(f"the copy has the agents {ids}; the live home has {live_ids}")
    warnings: list[str] = []
    for live, copy in zip(live_crew, crew, strict=True):
        for path in _paths(copy):
            if not path.resolve().is_relative_to(root):
                raise ValueError(f"agent {copy.id}: {path} is outside the run dir {root}")
        if copy.schedules or copy.telegram or copy.memory_consolidate:
            raise ValueError(f"agent {copy.id}: the copy still has a schedule or a Telegram bot")
        if copy.settings.shell_allow_patterns:
            raise ValueError(f"agent {copy.id}: the copy still lets a shell command run unasked")
        if _present(copy) < _present(live):
            raise ValueError(
                f"agent {copy.id}: a persona file of the live agent is not in the copy"
            )
        for skills in live.skills_dirs:
            mapped = map_path(skills.resolve(), mapping)
            if skills.is_dir() and (mapped is None or not mapped.is_dir()):
                warnings.append(f"agent {live.id}: the skills dir {skills} is not in the copy")
    return warnings


def _paths(profile: AgentProfile) -> list[Path]:
    persona = [profile.dir / name for name in profile.persona_files]
    return [profile.workspace, *profile.skills_dirs, *persona]


def _present(profile: AgentProfile) -> int:
    return sum((profile.dir / name).exists() for name in profile.persona_files)
