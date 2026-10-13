"""A folder the server keeps private, and a command in the sandbox: the folder is neither
read nor written, and nothing carries it to a path the rules do not name."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.tools import shell_sandbox
from my_agent_crew.tools.shell_sandbox import private_rules, sandbox_profile
from tests.test_shell_network_sandbox import needs_sandbox, python, run

SECRET = "bimat-4711"
HOME = "crew/home"
KEPT = f"{HOME}/browser"
COOKIES = f"{KEPT}/coach/Cookies"
# Every way in that was tried on a real sandbox. Each must fail and show nothing.
WAYS_IN = {
    "read": f"cat {COOKIES}",
    "read in a language of its own": python(f"print(open('{COOKIES}').read())"),
    "read by another spelling": f"cat {HOME}/BROWSER/coach/Cookies",
    "read by another name of the disk": f'cat "/System/Volumes/Data$PWD/{COOKIES}"',
    "list": f"ls {KEPT}/coach",
    "list the folder": f"ls {KEPT}",
    "copy": f"cp {COOKIES} work/data/c && cat work/data/c",
    "copy the folder": f"cp -R {KEPT} work/data/b && cat work/data/b/coach/Cookies",
    "link hard": f"ln {COOKIES} work/data/h && cat work/data/h",
    "link": f'ln -s "$PWD/{COOKIES}" work/data/s && cat work/data/s',
    "link the folder": f'ln -s "$PWD/{KEPT}" work/data/d && cat work/data/d/coach/Cookies',
    "move the file": f"mv {COOKIES} work/data/c2 && cat work/data/c2",
    "move what is in it": f"mv {KEPT}/coach work/data/coach && cat work/data/coach/Cookies",
    "move the folder": f"mv {KEPT} work/data/moved && cat work/data/moved/coach/Cookies",
    "move the folder above": f"mv {HOME} work/data/h2 && cat work/data/h2/browser/coach/Cookies",
    "move the one above that": f"mv crew work/data/c3 && cat work/data/c3/home/{COOKIES[10:]}",
    "write": f"echo x > {KEPT}/coach/new",
    "write over": f"echo x > {COOKIES}",
    "remove": f"rm -r {KEPT}",
}
CONFINED = {
    "writes all round it": {"write_paths": ["."]},
    "offline, writes all round it": {"network": False, "write_paths": ["."]},
    "offline, writes nowhere": {"network": False},
}


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A crew home with a browser folder that holds one agent's logins and a workspace
    beside it. The temp directories a sandbox leaves writable are taken away: pytest's own
    folders lie under one, and nothing here would be refused a write."""
    monkeypatch.setattr(shell_sandbox, "temp_dirs", lambda: ())
    root = tmp_path.resolve()
    (root / KEPT / "coach").mkdir(parents=True)
    (root / COOKIES).write_text(SECRET + "\n", encoding="utf-8")
    (root / HOME / "inbox").mkdir()
    (root / HOME / "inbox" / "note.md").write_text("ghi chu\n", encoding="utf-8")
    (root / "work" / "data").mkdir(parents=True)
    return root


def shell(root: Path, command: str, **confined):
    """`command` run at `root` by an agent whose shell is confined so, with the browser
    folder of the home kept private."""
    paths = [root / path for path in confined.pop("write_paths", ())]
    return run(root, command, write_paths=paths, private=[root / KEPT], **confined)


def untouched(root: Path) -> bool:
    inside = sorted(found.name for found in (root / KEPT / "coach").iterdir())
    return inside == ["Cookies"] and (root / COOKIES).read_text(encoding="utf-8") == SECRET + "\n"


def test_the_rules_close_a_folder_and_hold_every_folder_above_it_in_place():
    plain = sandbox_profile([Path("/w")], network=True)
    closed = sandbox_profile([Path("/w")], network=True, private=[Path("/h/browser")])

    assert private_rules([]) == "" and "file-read*" not in plain
    assert private_rules([Path("/h/browser")]) == (
        '(deny file-read* file-write* network-outbound (subpath "/h/browser"))'
        '(deny file-write-unlink (literal "/") (literal "/h"))'
    )
    # Named after the rule that opens the writable paths: of two rules the later decides.
    assert closed == plain + private_rules([Path("/h/browser")])
    two = private_rules([Path("/h/browser"), Path('/h/a "b"/c')])
    inside = '(subpath "/h/browser") (subpath "/h/a \\"b\\"/c")'
    assert two == (
        f"(deny file-read* file-write* network-outbound {inside})"
        '(deny file-write-unlink (literal "/") (literal "/h") (literal "/h/a \\"b\\""))'
    )


@needs_sandbox
@pytest.mark.parametrize("confined", CONFINED.values(), ids=CONFINED.keys())
async def test_no_command_in_a_sandbox_gets_at_a_private_folder(root: Path, confined: dict):
    for way, command in WAYS_IN.items():
        result = await shell(root, command, **confined)

        assert not result.ok, way
        assert SECRET not in result.output, way
        assert untouched(root), way
    # Nothing was carried off either: what a command left behind holds no login.
    left = [p for p in (root / "work").rglob("*") if p.is_file() and not p.is_symlink()]
    assert all(SECRET not in p.read_text(encoding="utf-8") for p in left)
    # `rm -f` reads a folder it may not look at as one that is gone and says nothing, so a
    # forced removal, of the folder and of what lies round it, is judged by what is left.
    await shell(root, f"rm -rf {KEPT}; rm -rf {HOME}; rm -rf crew", **confined)
    assert untouched(root)


@needs_sandbox
async def test_what_lies_beside_a_private_folder_is_read_and_written_as_before(root: Path):
    beside = {
        f"cat {HOME}/inbox/note.md": "ghi chu",
        f"echo moi > {HOME}/note2.md && cat {HOME}/note2.md": "moi",
        f"mkdir {HOME}/browsers && echo gan > {HOME}/browsers/f && cat {HOME}/browsers/f": "gan",
        f"mv {HOME}/inbox {HOME}/inbox2 && cat {HOME}/inbox2/note.md": "ghi chu",
        "mv work/data work/data2 && ls work": "data2",
        f"ls {HOME}": "browser\n",
    }
    for command, shown in beside.items():
        result = await shell(root, command, write_paths=["."])

        assert result.ok and shown in result.output, command
    assert untouched(root)


@needs_sandbox
async def test_a_private_folder_named_through_a_link_is_closed_where_it_really_lies(root: Path):
    """The sandbox goes by the real path, and a home is often given by another: `/tmp` and
    `/var` are links on this system, and a person may keep the home behind one of their own."""
    (root / "alias").symlink_to(root / HOME)
    named = [root / "alias" / "browser"]

    for command in (f"cat {COOKIES}", "cat alias/browser/coach/Cookies"):
        result = await run(root, command, write_paths=[root], private=named)

        assert not result.ok and SECRET not in result.output, command
    moved = await run(root, f"mv {HOME} work/data/h2", write_paths=[root], private=named)
    assert not moved.ok and untouched(root)


@needs_sandbox
async def test_a_refusal_tells_an_agent_with_a_private_folder_of_both_rules(root: Path):
    """A read refused in the folder prints the words a write refused anywhere prints, and
    after a `cd` the path in them says little. So the agent is told the two rules it may
    have met, and one with no private folder is told of writing alone, as before."""
    data = [root / "work" / "data"]
    both = texts.SHELL_PRIVATE_DENIED.format(paths=data[0])
    writes = texts.SHELL_WRITE_DENIED.format(paths=data[0])
    assert "hồ sơ trình duyệt" in both and "hồ sơ trình duyệt" not in writes

    for command in (f"cat {COOKIES}", f"cd {HOME} && cat browser/coach/Cookies", "echo x > new"):
        result = await shell(root, command, write_paths=["work/data"])
        assert not result.ok and result.output.endswith(both), command

    plain = await run(root, "echo x > new", write_paths=data)
    assert not plain.ok and plain.output.endswith(writes)
    # A command that failed for a reason of its own is told of neither.
    missing = await shell(root, f"cat {HOME}/nothing.md", write_paths=["work/data"])
    assert not missing.ok and "Sandbox" not in missing.output


@needs_sandbox
async def test_a_shell_that_was_never_confined_is_not_confined_by_a_private_folder(root: Path):
    """The stated limit: an agent whose shell runs free reads what its user reads. Such an
    agent is not one to give a browser, which the docs say and no rule here makes up for."""
    result = await run(root, f"cat {COOKIES}", private=[root / KEPT])

    assert result.ok and SECRET in result.output
