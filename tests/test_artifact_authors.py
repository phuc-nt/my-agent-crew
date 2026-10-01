"""The line naming who wrote the versions of a canvas an agent has not seen."""

from my_agent_crew.store.artifact_authors import authors_line
from my_agent_crew.store.artifact_models import USER, ArtifactVersion

ART = "0123456789ab"


def _history(*authors: str, numbers: tuple[int, ...] = ()) -> list[ArtifactVersion]:
    numbers = numbers or tuple(range(1, len(authors) + 1))
    return [
        ArtifactVersion(ART, number, 1, author, "", "", "", "")
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


def test_the_authors_line_names_six_groups_at_most():
    history = _history(*[USER, "agent:coach"] * 4)
    line = authors_line(history, 0, 8)
    assert "v1 người" in line and "v6 agent:coach" in line
    assert "v7" not in line and line.rstrip(".").endswith("…")
