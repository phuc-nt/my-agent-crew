"""Installing one of the bundled agent templates into a home.

A template is plain data — an `agent.yaml` and the persona files beside it — so adding an
agent is a copy, not a code path. The shared skills travel with it into the home's own
skills directory, where every agent can reach them.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

TEMPLATES_DIR = Path(__file__).parent / "templates"
SHARED_SKILLS = "_shared_skills"
MANIFEST = "agent.yaml"


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    description: str
    mode: str
    tools: tuple[str, ...]
    delegates: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "mode": self.mode,
            "tools": list(self.tools),
            "delegates": list(self.delegates),
        }


def _read(directory: Path) -> Template:
    raw = yaml.safe_load((directory / MANIFEST).read_text(encoding="utf-8")) or {}
    return Template(
        id=directory.name,
        name=str(raw.get("name") or directory.name),
        description=str(raw.get("description") or ""),
        mode=str(raw.get("mode") or "assistant"),
        tools=tuple(str(t) for t in raw.get("tools") or []),
        delegates=tuple(str(d) for d in raw.get("delegates") or []),
    )


def list_templates() -> list[Template]:
    if not TEMPLATES_DIR.is_dir():
        return []
    return [
        _read(d)
        for d in sorted(TEMPLATES_DIR.iterdir())
        if d.is_dir() and d.name != SHARED_SKILLS and (d / MANIFEST).is_file()
    ]


def _copy_tree(src: Path, dest: Path, force: bool) -> list[Path]:
    """Copies file by file rather than `copytree` so an existing file can be kept. An
    interrupted add leaves what it managed to write, and running it again finishes the job
    instead of refusing outright."""
    written = []
    for path in sorted(p for p in src.rglob("*") if p.is_file()):
        target = dest / path.relative_to(src)
        if target.exists() and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        written.append(target)
    return written


def add_template(
    template: str, home: Path, agent_id: str = "", force: bool = False
) -> tuple[Path, list[str]]:
    """Copies one template into `home/agents/<id>` and its shared skills into `home/skills`.

    A template that delegates brings the peers it names, under their own ids, because the
    server refuses to start when a `delegates` entry points at an agent that is not there
    — adding a lead on its own would leave a home that cannot come up.

    Returns the agent directory and the ids of any peers added with it. Raises `KeyError`
    for a name that is not a template and `FileExistsError` when the id is taken, so a
    mistyped name never half-writes an agent.
    """
    source = TEMPLATES_DIR / template
    if not (source / MANIFEST).is_file():
        raise KeyError(template)
    agent_dir = home / "agents" / (agent_id or template)
    if agent_dir.exists() and not force:
        raise FileExistsError(agent_dir)
    _copy_tree(source, agent_dir, force)
    shared = TEMPLATES_DIR / SHARED_SKILLS
    if shared.is_dir():
        _copy_tree(shared, home / "skills", force)
    peers = []
    for peer in _read(source).delegates:
        peer_dir = home / "agents" / peer
        if peer_dir.exists() or not (TEMPLATES_DIR / peer / MANIFEST).is_file():
            continue
        _copy_tree(TEMPLATES_DIR / peer, peer_dir, force=False)
        peers.append(peer)
    return agent_dir, peers
