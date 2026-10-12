"""Every source file stays small enough to read in one sitting: package, scripts and web."""

from pathlib import Path

LIMIT = 200
REPO = Path(__file__).resolve().parents[1]
ROOTS = (REPO / "my_agent_crew", REPO / "scripts")
WEB = REPO / "web" / "src"
WEB_KINDS = (".ts", ".tsx", ".css")


def over_budget(paths) -> dict[str, int]:
    return {
        p.relative_to(REPO).as_posix(): n
        for p in paths
        if (n := len(p.read_text(encoding="utf-8").splitlines())) > LIMIT
    }


def web_sources() -> list[Path]:
    """What the web ships. Its tests and their helpers (`web/src/test/`) are not sources."""
    return [
        p
        for p in WEB.rglob("*")
        if p.suffix in WEB_KINDS
        and ".test." not in p.name
        and p.relative_to(WEB).parts[0] != "test"
    ]


def test_no_source_file_exceeds_the_line_budget():
    assert over_budget(p for root in ROOTS for p in root.rglob("*.py")) == {}


def test_every_folder_the_budget_covers_holds_sources():
    """A moved folder would leave the budget passing on nothing."""
    assert all(any(root.rglob("*.py")) for root in ROOTS)


def test_no_web_source_file_exceeds_the_line_budget():
    assert over_budget(web_sources()) == {}


def test_the_web_budget_covers_sources_of_every_kind():
    """Modules, components and stylesheets, the ones in nested folders included."""
    found = web_sources()
    assert {p.suffix for p in found} == {".ts", ".tsx", ".css"}
    assert any(len(p.relative_to(WEB).parts) > 2 for p in found)


def test_the_web_budget_leaves_tests_and_their_helpers_out():
    """They sit beside the sources, so the tree holds them and the budget must not."""
    found = set(web_sources())
    tests = list(WEB.rglob("*.test.*"))
    helpers = list((WEB / "test").rglob("*.ts*"))
    assert tests and helpers
    assert found.isdisjoint(tests) and found.isdisjoint(helpers)
