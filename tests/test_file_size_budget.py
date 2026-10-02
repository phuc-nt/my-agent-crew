"""Every source file stays small enough to read in one sitting: the package's and the scripts'."""

from pathlib import Path

LIMIT = 200
REPO = Path(__file__).resolve().parents[1]
ROOTS = (REPO / "my_agent_crew", REPO / "scripts")


def test_no_source_file_exceeds_the_line_budget():
    offenders = {
        p.relative_to(REPO).as_posix(): n
        for root in ROOTS
        for p in root.rglob("*.py")
        if (n := len(p.read_text(encoding="utf-8").splitlines())) > LIMIT
    }
    assert offenders == {}


def test_every_folder_the_budget_covers_holds_sources():
    """A moved folder would leave the budget passing on nothing."""
    assert all(any(root.rglob("*.py")) for root in ROOTS)
