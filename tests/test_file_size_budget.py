"""Every source file stays small enough to read in one sitting."""

from pathlib import Path

LIMIT = 200
ROOT = Path(__file__).resolve().parents[1] / "my_agent_crew"


def test_no_source_file_exceeds_the_line_budget():
    offenders = {
        p.relative_to(ROOT).as_posix(): n
        for p in ROOT.rglob("*.py")
        if (n := len(p.read_text(encoding="utf-8").splitlines())) > LIMIT
    }
    assert offenders == {}
