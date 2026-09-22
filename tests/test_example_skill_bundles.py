"""The skill bundles under `docs/examples/skills/` are meant to be copied into a real
`skills_dirs` and filled in. A sample that the loader cannot read, or that carries a real
account id out of someone's home directory, is worse than no sample at all — so both are
checked here rather than trusted to review.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from my_agent_crew.skills.loader import load_skills, parse_skill

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "examples" / "skills"
BUNDLES = sorted(p for p in EXAMPLES.iterdir() if (p / "SKILL.md").is_file())

# An id someone pasted in while testing against their own account. Long unbroken runs of
# id-ish characters and anything shaped like an email address are the two ways a real one
# has ever reached a sample. A real id mixes letters and digits, which is what separates it
# from the comment dividers and the shouty env-var names that also run long.
LONG_ID = re.compile(r"(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{25,}")
EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def test_examples_directory_has_bundles() -> None:
    """Without this the whole file would pass by having nothing to check."""
    assert BUNDLES, f"no skill bundles under {EXAMPLES}"


@pytest.mark.parametrize("bundle", BUNDLES, ids=lambda p: p.name)
def test_loader_reads_the_sample(bundle: Path) -> None:
    skills = load_skills(bundle.parent, which=lambda _: "/usr/bin/true")
    by_name = {s.name: s for s in skills}
    skill = by_name.get(bundle.name)
    assert skill is not None, f"{bundle.name} did not load under its folder name"
    assert skill.description, "a sample with no description is invisible in the index"
    assert skill.body.strip(), "empty body"


@pytest.mark.parametrize("bundle", BUNDLES, ids=lambda p: p.name)
def test_cli_sample_declares_its_program(bundle: Path) -> None:
    """A bundle shipping `scripts/` drives a command-line program, and the two fields that
    make that survivable are `requires.bins` (so a missing program is labelled instead of
    failing mid-turn) and `cliHelp` (so the model reads the syntax instead of guessing)."""
    if not (bundle / "scripts").is_dir():
        pytest.skip("not a CLI bundle")
    skill = parse_skill((bundle / "SKILL.md").read_text(encoding="utf-8"), bundle.name)
    assert skill.requires_bins, "a CLI sample must name the program it needs"
    assert skill.cli_help, "a CLI sample must name the command that prints real syntax"


@pytest.mark.parametrize("bundle", BUNDLES, ids=lambda p: p.name)
def test_sample_carries_no_real_account(bundle: Path) -> None:
    for path in sorted(p for p in bundle.rglob("*") if p.is_file()):
        where = path.relative_to(EXAMPLES)
        # A sample is text a person copies and edits. Anything that will not decode is
        # something nobody reviewed, so refuse it rather than skipping past it — a scan
        # that raises on a stray file is a scan that stops checking the rest.
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            pytest.fail(f"{where}: not UTF-8 text; a skill sample should be readable source")
        assert not EMAIL.search(text), f"{where}: an email address reached the repo"
        found = LONG_ID.search(text)
        assert found is None, f"{where}: {found.group()[:8] if found else ''}… looks like a real id"


def test_wrapper_refuses_to_log_in() -> None:
    """`gws auth login` opens a browser, so under a job it hangs until the run times out.
    The wrapper has to refuse it without ever reaching the binary, which is also why this
    test can run on a machine that has no gws installed."""
    wrapper = EXAMPLES / "gws" / "scripts" / "gws-run.sh"
    if not wrapper.is_file():
        pytest.skip("gws sample absent")
    done = subprocess.run(
        ["bash", str(wrapper), "auth", "login"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == 2
    assert '"ok": false' in done.stderr
    assert "auth status" in done.stderr
    # stdout is what a caller pipes into jq. A refusal must not pollute it.
    assert done.stdout == ""
