import os
import stat
from pathlib import Path

import pytest

from my_agent_crew.env_file import (
    check_value,
    env_path,
    load_env_file,
    read_env,
    remove_env,
    set_env,
    set_many,
)


def test_a_value_the_shell_would_misread_is_written_so_it_reads_back_the_same(
    tmp_path: Path,
) -> None:
    path = env_path(tmp_path)
    tricky = 'it\'s $HOME `id` "quoted" \\ back'

    set_env(path, "TRICKY", tricky)

    assert read_env(path) == {"TRICKY": tricky}
    assert path.read_text(encoding="utf-8").startswith("TRICKY='")


def test_hand_written_lines_survive_an_edit_byte_for_byte(tmp_path: Path) -> None:
    path = env_path(tmp_path)
    path.write_text(
        '# my keys\nexport FIRST="one"\n\nSECOND=two # note\nFIRST=stale\n', encoding="utf-8"
    )

    set_env(path, "FIRST", "new")
    set_env(path, "THIRD", "3")

    # Every assignment to the name collapses into one, where the first one stood.
    assert path.read_text(encoding="utf-8") == (
        "# my keys\nFIRST='new'\n\nSECOND=two # note\nTHIRD='3'\n"
    )
    assert read_env(path) == {"FIRST": "new", "SECOND": "two", "THIRD": "3"}


def test_several_names_are_written_and_dropped_as_one_replacement_of_the_file(
    tmp_path: Path, monkeypatch
) -> None:
    path = env_path(tmp_path)
    path.write_text("# my keys\nKEEP=1\nOLD=stale\nGOES=2\n\nexport OLD=again\n", encoding="utf-8")
    os.chmod(path, 0o644)
    replaced, replace = [], os.replace
    monkeypatch.setattr(
        "my_agent_crew.env_file.os.replace", lambda *a: (replaced.append(a), replace(*a))[1]
    )

    set_many(path, {"OLD": "it's new", "GOES": "", "FRESH": "f", "NEVER_THERE": ""})

    assert len(replaced) == 1
    # Each name stands where its first line stood, a new one at the end, as one at a time.
    assert path.read_text(encoding="utf-8") == (
        "# my keys\nKEEP=1\nOLD='it'\\''s new'\n\nFRESH='f'\n"
    )
    assert read_env(path) == {"KEEP": "1", "OLD": "it's new", "FRESH": "f"}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_dropping_names_that_are_not_there_writes_nothing(tmp_path: Path) -> None:
    path = env_path(tmp_path)

    set_many(path, {"GONE": "", "NEVER_THERE": ""})

    assert not path.exists()
    # Not even to give a hand-written file the line end it lacks.
    path.write_text("# mine, with no line end", encoding="utf-8")
    set_many(path, {"GONE": "", "NEVER_THERE": ""})
    assert path.read_text(encoding="utf-8") == "# mine, with no line end"


def test_a_replacement_that_fails_leaves_the_file_as_it_was_and_nothing_beside_it(
    tmp_path: Path, monkeypatch
) -> None:
    path = env_path(tmp_path)
    path.write_text("KEEP=1\nOLD=stale\n", encoding="utf-8")

    def no_room(src, dst):
        raise OSError("no room left")

    monkeypatch.setattr("my_agent_crew.env_file.os.replace", no_room)

    with pytest.raises(OSError, match="no room left"):
        set_many(path, {"OLD": "new", "KEEP": "", "FRESH": "f"})

    assert path.read_text(encoding="utf-8") == "KEEP=1\nOLD=stale\n"
    assert [entry.name for entry in tmp_path.iterdir()] == ["env"]


def test_the_file_is_owner_only_even_when_it_was_not(tmp_path: Path) -> None:
    path = env_path(tmp_path)
    path.write_text("A=1\n", encoding="utf-8")
    os.chmod(path, 0o644)

    set_env(path, "B", "2")

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_removing_drops_only_that_name(tmp_path: Path) -> None:
    path = env_path(tmp_path)
    set_env(path, "KEEP", "1")
    set_env(path, "DROP", "2")

    assert remove_env(path, "DROP") is True
    assert remove_env(path, "DROP") is False
    assert read_env(path) == {"KEEP": "1"}


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("   ", "empty"),
        ("a\nB=2", "multiline"),
        ("a\rb", "multiline"),
        ("a\u2028B=2", "multiline"),
        ("a\x0bb", "multiline"),
        ("a\x0cb", "multiline"),
        ("a\x85b", "multiline"),
        ("a\x01b", "multiline"),
        ("a\ud800b", "multiline"),  # a lone surrogate cannot even be written as UTF-8
        ("x" * 5000, "too long"),
    ],
)
def test_a_value_that_could_become_a_second_line_of_shell_is_refused(raw, reason) -> None:
    with pytest.raises(ValueError, match=reason):
        check_value(raw)


def test_a_pasted_key_loses_its_stray_whitespace() -> None:
    assert check_value("  sk-abc\t") == "sk-abc"


def test_the_process_environment_wins_over_the_file(tmp_path: Path) -> None:
    set_env(env_path(tmp_path), "FROM_FILE", "file")
    set_env(env_path(tmp_path), "BOTH", "file")
    environ = {"BOTH": "process"}

    loaded = load_env_file(tmp_path, environ)

    assert loaded == ["FROM_FILE"]
    assert environ == {"BOTH": "process", "FROM_FILE": "file"}


def test_a_home_without_the_file_loads_nothing(tmp_path: Path) -> None:
    assert load_env_file(tmp_path, {}) == []


def test_a_form_feed_in_a_hand_written_line_does_not_split_it_in_two(tmp_path: Path) -> None:
    path = env_path(tmp_path)
    # The shell reads this as one assignment to A; so must we, or a rewrite would
    # turn the second half into a real line the shell runs at the next restart.
    path.write_bytes(b"A=x\x0cDYLD_X=1\n")

    environ: dict[str, str] = {}
    load_env_file(tmp_path, environ)
    set_env(path, "OTHER", "y")

    assert "DYLD_X" not in read_env(path) and "DYLD_X" not in environ
    assert path.read_bytes() == b"A=x\x0cDYLD_X=1\nOTHER='y'\n"


def test_an_env_file_that_is_a_link_stays_a_link(tmp_path: Path) -> None:
    real = tmp_path / "secrets" / "env"
    real.parent.mkdir()
    real.write_text("KEEP=1\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    env_path(home).symlink_to(real)

    set_env(env_path(home), "NEW", "2")

    assert env_path(home).is_symlink()
    assert read_env(real) == {"KEEP": "1", "NEW": "2"}
