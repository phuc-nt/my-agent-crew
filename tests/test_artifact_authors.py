"""The line naming who wrote the versions of a canvas an agent has not seen."""

from my_agent_crew.store.artifact_authors import authors_line
from my_agent_crew.store.artifact_models import IMPORT_NOTE, USER, ArtifactVersion
from my_agent_crew.texts_canvas import ARTIFACT_AUTHORS

ART = "0123456789ab"


def _history(
    *authors: str, numbers: tuple[int, ...] = (), notes: dict[int, str] | None = None
) -> list[ArtifactVersion]:
    numbers = numbers or tuple(range(1, len(authors) + 1))
    notes = notes or {}
    return [
        ArtifactVersion(ART, number, 1, author, "", notes.get(number, ""), "", "")
        for number, author in zip(numbers, authors, strict=True)
    ]


def test_the_authors_line_groups_each_run_of_one_author():
    history = _history(USER, USER, "agent:coach", USER)
    line = authors_line(history, 0, 4)
    assert "v1–v2 người, v3 agent:coach, v4 người" in line
    assert "v2 người, v3 agent:coach" in authors_line(history, 1, 3)
    assert "v1" not in authors_line(history, 1, 3) and "v4" not in authors_line(history, 1, 3)
    assert authors_line(history, 4, 4) == ""
    assert authors_line(history, 4, 9) == ""


def test_a_group_spans_the_numbers_a_folded_burst_left_out():
    history = _history(USER, USER, "agent:coach", numbers=(1, 3, 4))
    assert "v1–v3 người, v4 agent:coach" in authors_line(history, 0, 4)


def test_the_authors_line_names_the_six_newest_groups_at_most():
    """The newest versions are the ones the agent is about to meet, so the older ones give way."""
    history = _history(*[USER, "agent:coach"] * 4)
    newest = "…, v3 người, v4 agent:coach, v5 người, v6 agent:coach, v7 người, v8 agent:coach"
    assert authors_line(history, 0, 8) == ARTIFACT_AUTHORS.format(groups=newest)
    assert authors_line(history, 2, 8) == ARTIFACT_AUTHORS.format(groups=newest[3:])


def test_a_restore_is_a_group_of_its_own_naming_the_version_it_brought_back():
    """A restore puts back text the agent may already know, so it must not hide inside a run of
    ordinary saves by the same person."""
    notes = {3: "restore:1", 4: "restore:1", 5: "restore:2"}
    history = _history(*[USER] * 6, notes=notes)
    groups = (
        "v1–v2 người, v3 người khôi phục v1, v4 người khôi phục v1, v5 người khôi phục v2, v6 người"
    )
    assert authors_line(history, 0, 6) == ARTIFACT_AUTHORS.format(groups=groups)
    assert authors_line(history, 4, 5) == ARTIFACT_AUTHORS.format(groups="v5 người khôi phục v2")


def test_a_version_imported_from_a_file_is_named_as_one_whoever_imported_it():
    """An import puts a file's text in place of the canvas's, so it must not hide inside a run
    of the same author's ordinary writes; imports one after another are one group."""
    notes = {2: IMPORT_NOTE, 4: IMPORT_NOTE, 5: IMPORT_NOTE}
    history = _history(USER, USER, "agent:coach", "agent:coach", "agent:coach", USER, notes=notes)
    groups = (
        "v1 người, v2 người nhập từ tệp, v3 agent:coach, v4–v5 agent:coach nhập từ tệp, v6 người"
    )
    assert authors_line(history, 0, 6) == ARTIFACT_AUTHORS.format(groups=groups)
    assert authors_line(history, 1, 2) == ARTIFACT_AUTHORS.format(groups="v2 người nhập từ tệp")
