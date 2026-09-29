"""Where each live path lands in the copy, and what the copied manifests say.

Every path in a copied manifest is rewritten to stay inside the run directory. One that
reaches beyond the home and the workspaces has no copy and is refused, before anything is
copied."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import yaml

from my_agent_crew.agents.profile import AgentProfile

# The copy runs nothing on its own, talks to no one and lets no shell command run unasked.
DROPPED_KEYS = ("schedules", "telegram", "memory_consolidate", "shell_allow_patterns")
PATH_KEYS = ("workspace", "skills_dirs", "persona_files")
MAX_WARNING_TEXT = 160

Mapping = list[tuple[Path, Path]]  # (a live root, where its copy lives)


def refuse_kit_agents_outside(crew: Sequence[AgentProfile], yaml_ids: set[str], live: Path):
    for profile in crew:
        if profile.id not in yaml_ids and not profile.workspace.resolve().is_relative_to(live):
            raise ValueError(
                f"kit agent {profile.id}: its workspace {profile.workspace} is outside the home, "
                "so the copy would leave it behind; give the agent an agent.yaml or move it"
            )


def external_roots(workspaces: Sequence[Path], live: Path) -> list[Path]:
    """The workspaces outside the home, each once, none inside another."""
    resolved = [w.resolve() for w in workspaces]
    unique = list(dict.fromkeys(r for r in resolved if not r.is_relative_to(live)))
    user_home = Path.home().resolve()
    for root in unique:
        if live.is_relative_to(root):
            raise ValueError(f"the workspace {root} contains the live home; it cannot be copied")
        if user_home.is_relative_to(root):
            raise ValueError(f"the workspace {root} is or contains your home directory")
        if not root.is_dir() and root.exists():
            raise ValueError(f"the workspace {root} is not a directory")
    return [r for r in unique if not any(r != o and r.is_relative_to(o) for o in unique)]


def check_run_dir(root: Path, sources: Sequence[Path]) -> None:
    for source in sources:
        if root.is_relative_to(source):
            raise ValueError(f"the run dir {root} is inside {source}, which the copy reads")
        if source.is_relative_to(root):
            raise ValueError(f"the run dir {root} contains {source}: `~` would reach it")


def copy_dirs(externals: Sequence[Path], ws: Path) -> list[Path]:
    """`ws/<name>` for each workspace; a second one with the same name gets `-2`."""
    dirs: list[Path] = []
    for root in externals:
        name = root.name or "root"
        unique, n = name, 1
        while ws / unique in dirs:
            n += 1
            unique = f"{name}-{n}"
        dirs.append(ws / unique)
    return dirs


def plan_manifests(
    live: Path, mapping: Mapping, live_paths: Sequence[str]
) -> tuple[list[tuple[str, dict[str, Any]]], set[str], list[str]]:
    """Each manifest as the copy will hold it, worked out before anything is copied so a
    path that leads nowhere is refused while there is nothing to clean up."""
    planned: list[tuple[str, dict[str, Any]]] = []
    tokens: set[str] = set()
    warnings: list[str] = []
    for rel, source, live_dir in _manifests(live):
        raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{rel}: expected a mapping at the top level")
        telegram = raw.get("telegram")
        if isinstance(telegram, dict) and isinstance(telegram.get("token_env"), str):
            tokens.add(telegram["token_env"])
        for key in DROPPED_KEYS:
            raw.pop(key, None)
        for key in PATH_KEYS:
            if key in raw:
                raw[key] = _rewrite(rel, key, raw[key], live_dir, mapping)
        for text in _strings(raw):
            if any(p.lower() in text.lower() for p in live_paths):
                shown = text if len(text) <= MAX_WARNING_TEXT else text[:MAX_WARNING_TEXT] + "..."
                warnings.append(f'{rel}: "{shown}" still names a live path')
        planned.append((rel, raw))
    return planned, tokens, warnings


def _manifests(live: Path) -> Iterator[tuple[str, Path, Path]]:
    """(name inside the home, the live file, the directory its paths are relative to)."""
    for name in ("agent.yaml", "config.yaml"):
        if (live / name).is_file():
            yield name, live / name, live
    agents = live / "agents"
    if agents.is_dir():
        for agent_dir in sorted(p for p in agents.iterdir() if p.is_dir() and p.name[:1] != "."):
            if (agent_dir / "agent.yaml").is_file():
                rel = f"agents/{agent_dir.name}/agent.yaml"
                yield rel, agent_dir / "agent.yaml", agent_dir.resolve()


def _rewrite(rel: str, key: str, value: Any, live_dir: Path, mapping: Mapping) -> Any:
    if key == "workspace":
        return _rewrite_one(rel, key, value, live_dir, mapping)
    if not isinstance(value, list):
        return value
    return [_rewrite_one(rel, key, v, live_dir, mapping) for v in value]


def _rewrite_one(rel: str, key: str, value: Any, live_dir: Path, mapping: Mapping) -> Any:
    """A path that stays inside its agent's directory is kept as written; any other becomes
    the absolute path of its copy. One that reaches beyond the home and the workspaces has
    no copy and is refused."""
    if not isinstance(value, str) or not value:
        return value
    if key == "persona_files":
        target = (live_dir / value).resolve()
    else:
        target = (live_dir / Path(value).expanduser()).resolve()
    mapped = map_path(target, mapping)
    if mapped is None:
        raise ValueError(
            f"{rel}: {key} {value!r} points outside the home and the workspaces ({target}); "
            "the copy has nowhere to put it"
        )
    written_relative = not Path(value).is_absolute() and (
        key == "persona_files" or not value.startswith("~")
    )
    return value if written_relative and target.is_relative_to(live_dir) else str(mapped)


def map_path(target: Path, mapping: Mapping) -> Path | None:
    inside = [(live, copy) for live, copy in mapping if target.is_relative_to(live)]
    if not inside:
        return None
    live, copy = max(inside, key=lambda pair: len(pair[0].parts))
    return copy / target.relative_to(live)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
