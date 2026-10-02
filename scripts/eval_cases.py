"""Behaviour-eval cases: the file format, and how a file or a folder of them is loaded.

A case is a short conversation with one agent plus what must, and must not, happen in it (see
`scripts/eval_example_cases.yaml`). `eval_expect.py` holds the `expect` block, `eval_canvas.py`
the canvas steps between messages, and `eval_check.py` judges a run against it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from eval_canvas import CanvasStep, parse_messages
from eval_expect import Expect, parse_expect
from eval_shape import only, strings

APPROVAL_POLICIES = ("deny", "approve")
CASE_KEYS = ("id", "agent", "messages", "approvals", "answers", "expect")


@dataclass(frozen=True)
class Case:
    id: str
    agent: str
    messages: tuple[str | CanvasStep, ...]
    approvals: str = "deny"
    answers: tuple[str, ...] = ()
    expect: Expect = field(default_factory=Expect)
    source: str = ""


def load_cases(path: Path) -> list[Case]:
    """Every case of one YAML file, or of every `*.yaml` in a directory, in name order."""
    if path.is_dir():
        files = sorted(path.glob("*.yaml"))
    elif path.is_file():
        files = [path]
    else:
        raise ValueError(f"{path}: no such file or directory")
    cases: list[Case] = []
    where: dict[str, str] = {}
    for file in files:
        try:
            raw = yaml.safe_load(file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ValueError(f"{file}: not valid YAML: {exc}") from exc
        for item in raw if isinstance(raw, list) else [] if raw is None else [raw]:
            case = parse_case(item, str(file))
            if case.id in where:
                raise ValueError(f"duplicate case id {case.id!r}: in {where[case.id]} and {file}")
            where[case.id] = str(file)
            cases.append(case)
    if not cases:
        raise ValueError(f"{path}: no cases found (a case file is a *.yaml list of cases)")
    return cases


def parse_case(raw: object, source: str) -> Case:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{source}: a case is a mapping, not {type(raw).__name__}")
    case_id = raw.get("id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError(f"{source}: a case needs an id")
    where = f"{source}: case {case_id!r}"
    only(raw, CASE_KEYS, where)
    agent = raw.get("agent")
    if not isinstance(agent, str) or not agent:
        raise ValueError(f"{where}: needs an agent")
    approvals = raw.get("approvals", "deny")
    if approvals not in APPROVAL_POLICIES:
        raise ValueError(f"{where}: approvals is one of {', '.join(APPROVAL_POLICIES)}")
    messages = parse_messages(raw.get("messages"), where)
    answers = strings(raw.get("answers", []), f"{where}: answers")
    expect = parse_expect(raw.get("expect") or {}, where)
    return Case(case_id, agent, messages, str(approvals), answers, expect, source)
