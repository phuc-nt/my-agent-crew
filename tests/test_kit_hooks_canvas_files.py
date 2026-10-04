"""Kit hooks and the two canvas tools that touch workspace files. `artifact_import` reads a
file the way `workspace_read` does and `artifact_export` writes one the way `workspace_write`
does, so a hook that guards reading or writing is asked about them too, whether it names our
tool or the harness's; a hook that guards only the other is not."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.kit_agents import TOOL_NAMES
from my_agent_crew.agents.kit_hooks import POST, PRE, TOOL_ALIASES, Hook
from my_agent_crew.config import Settings
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.store.db import Store
from my_agent_crew.tools.hooks import HookRunner
from tests.canvas_helpers import PLAN, call, created, persons_canvas, put, tagged, turn

FILE_TOOLS = ("workspace_read", "workspace_write", "artifact_import", "artifact_export")
NO = "kit says no"


def py(code: str) -> str:
    return f"python3 -c {json.dumps(code)}"


REFUSE = py(f"import sys; print({NO!r}, file=sys.stderr); sys.exit(2)")


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "ws").mkdir()
    return tmp_path / "ws"


def _guard(cwd: Path, matcher: str, event: str = PRE) -> Hook:
    return Hook(event, matcher, REFUSE, cwd, timeout=10)


def _blocked(name: str) -> str:
    return texts.TOOL_BLOCKED_BY_HOOK.format(name=name, reason=NO)


@pytest.mark.parametrize("matcher", ["Read|Write|Edit|Bash", "workspace_read|workspace_write"])
async def test_a_hook_that_guards_files_is_asked_about_the_canvas_tools_that_carry_them(
    tmp_path: Path, matcher: str
):
    runner = HookRunner([_guard(tmp_path, matcher)], "coach")
    for name in FILE_TOOLS:
        assert await runner.before(name, {"path": "notes/x.md"}) == NO, name
    assert await runner.before("artifact_read", {"id": "a"}) is None


@pytest.mark.parametrize(
    ("matcher", "asked", "spared"),
    [
        ("Write", "artifact_export", "artifact_import"),
        ("workspace_write", "artifact_export", "artifact_import"),
        ("Read", "artifact_import", "artifact_export"),
        ("workspace_read", "artifact_import", "artifact_export"),
    ],
)
async def test_a_hook_is_asked_only_about_the_canvas_tool_that_does_what_it_guards(
    tmp_path: Path, matcher: str, asked: str, spared: str
):
    """Before the call and after it: an import writes no file and an export reads none."""
    runner = HookRunner([_guard(tmp_path, matcher), _guard(tmp_path, matcher, POST)], "coach")
    args = {"path": "notes/x.md"}
    assert await runner.before(asked, args) == NO
    assert await runner.before(spared, args) is None
    assert await runner.after(asked, args, True, "out") == texts.TOOL_HOOK_NOTE.format(note=NO)
    assert await runner.after(spared, args, True, "out") == ""


def test_a_hook_naming_a_canvas_tool_is_asked_about_that_tool_alone(tmp_path: Path):
    """The canvas tool answers to the file tool's name, never the file tool to the canvas's."""
    pairs = {"artifact_export": "workspace_write", "artifact_import": "workspace_read"}
    for own, like in pairs.items():
        hook = _guard(tmp_path, own)
        assert hook.matches(own) and not hook.matches(like), own
    literal = _guard(tmp_path, "(Write")
    assert not literal.matches("artifact_export") and literal.matches("(Write")


def test_front_matter_still_reads_a_harness_name_as_the_plain_file_tool():
    """An agent whose front matter allows `Read` is given `workspace_read`, not an import."""
    assert (TOOL_NAMES["read"], TOOL_NAMES["write"]) == ("workspace_read", "workspace_write")
    canvas = {"artifact_import", "artifact_export"}
    assert not canvas & set(TOOL_NAMES.values()) and not canvas & set(TOOL_ALIASES)


async def test_the_hook_is_told_the_canvas_tools_own_name_and_the_harness_name_for_what_it_does(
    tmp_path: Path,
):
    record = py(
        "import json,sys; d=json.load(sys.stdin);"
        f" open({str(tmp_path)!r}+'/'+d['tool_name']+'.json','w').write(json.dumps(d))"
    )
    runner = HookRunner([Hook(PRE, "*", record, tmp_path, timeout=10)], "coach")
    calls = {
        "artifact_export": {"id": "a", "path": "out/x.md"},
        "artifact_import": {"path": "notes/x.md"},
        "artifact_read": {"id": "a"},
    }
    for name, args in calls.items():
        assert await runner.before(name, args) is None
    told = {name: json.loads((tmp_path / f"{name}.json").read_text()) for name in calls}
    assert {name: payload["tool_name"] for name, payload in told.items()} == {n: n for n in calls}
    assert {name: payload["tool_alias"] for name, payload in told.items()} == {
        "artifact_export": "Write",
        "artifact_import": "Read",
        "artifact_read": "artifact_read",
    }
    assert {name: payload["tool_input"] for name, payload in told.items()} == calls


async def test_a_hook_that_refuses_writes_stops_an_export_before_any_file_is_made(
    store: Store, root: Path, tmp_path: Path
):
    turn(store)
    art = await created(store, PLAN)
    args = {"id": art, "path": "out/x.md"}
    guard = HookRunner([_guard(tmp_path, "Write")], "coach")
    refused = await call(store, "artifact_export", args, hooks=guard, root=root)
    assert (refused.ok, refused.output) == (False, _blocked("artifact_export"))
    assert list(root.iterdir()) == []
    reads = HookRunner([_guard(tmp_path, "Read")], "coach")
    assert (await call(store, "artifact_export", args, hooks=reads, root=root)).ok
    assert (root / "out" / "x.md").read_text(encoding="utf-8") == PLAN


async def test_a_hook_that_refuses_reads_stops_an_import_before_any_canvas_is_made(
    store: Store, root: Path, tmp_path: Path
):
    turn(store)
    put(root, "notes/x.md", PLAN)
    guard = HookRunner([_guard(tmp_path, "Read")], "coach")
    refused = await call(store, "artifact_import", {"path": "notes/x.md"}, hooks=guard, root=root)
    assert (refused.ok, refused.output) == (False, _blocked("artifact_import"))
    assert store.artifacts.list() == []
    writes = HookRunner([_guard(tmp_path, "Write")], "coach")
    let = await call(store, "artifact_import", {"path": "notes/x.md"}, hooks=writes, root=root)
    assert store.artifacts.head(tagged(let)[0]).content == PLAN


async def test_the_hooks_of_an_agents_kit_stand_before_its_canvas_file_tools(
    settings: Settings, store: Store, tmp_path: Path
):
    """Through the registry an agent is really given: its profile's hooks, its own workspace."""
    settings.workspace_dir.mkdir(parents=True)
    put(settings.workspace_dir, "notes/x.md", PLAN)
    hooks = (_guard(tmp_path, "Read|Write"),)
    registry = build_tools(
        replace(default_profile(settings), hooks=hooks), httpx.AsyncClient(), store, []
    )
    conv = turn(store)
    art = persons_canvas(store, PLAN, conv.id)
    taken = await registry.execute("artifact_import", {"path": "notes/x.md"})
    given = await registry.execute("artifact_export", {"id": art, "path": "out/x.md"})
    assert taken.output == _blocked("artifact_import")
    assert given.output == _blocked("artifact_export")
    assert [summary.id for summary in store.artifacts.list()] == [art]
    assert [entry.name for entry in settings.workspace_dir.iterdir()] == ["notes"]
