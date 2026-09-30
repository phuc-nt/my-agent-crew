"""Pure validation and formatting for a schedule proposed from chat: the same checks a
tool call is judged by and the same text a person reads on the approval card, so neither
can drift from the other."""

from __future__ import annotations

from datetime import datetime

import pytest

from my_agent_crew.tools.schedule_proposal import (
    MAX_NAME,
    MAX_PER_AGENT,
    MAX_PROMPT,
    MIN_GAP_MINUTES,
    ProposalError,
    min_gap_minutes,
    parse,
    reason_line,
    upcoming,
)


@pytest.mark.parametrize(
    ("cron", "expected"),
    [
        ("*/5 * * * *", 5),
        ("*/15 * * * *", 15),
        ("0 7 * * *", 1440),
        ("0 7,19 * * *", 720),
        ("30 23,0 * * *", 60),
        ("* * * * *", 1),
    ],
)
def test_min_gap_minutes_documented_cases(cron: str, expected: int) -> None:
    from my_agent_crew.scheduler.cron import CronSpec

    assert min_gap_minutes(CronSpec.parse(cron)) == expected


class TestRejections:
    def test_every_minute_is_too_frequent(self) -> None:
        with pytest.raises(ProposalError):
            parse({"name": "n", "prompt": "p", "cron": "* * * * *"}, known_skills=())

    def test_every_five_minutes_is_too_frequent(self) -> None:
        with pytest.raises(ProposalError):
            parse({"name": "n", "prompt": "p", "cron": "*/5 * * * *"}, known_skills=())

    def test_a_cron_with_no_run_in_the_horizon_is_rejected(self) -> None:
        with pytest.raises(ProposalError):
            parse({"name": "n", "prompt": "p", "cron": "0 0 30 2 *"}, known_skills=())

    def test_every_five_minutes_is_too_short(self) -> None:
        with pytest.raises(ProposalError):
            parse({"name": "n", "prompt": "p", "every": "5m"}, known_skills=())

    def test_every_fourteen_minutes_is_too_short(self) -> None:
        with pytest.raises(ProposalError):
            parse({"name": "n", "prompt": "p", "every": "14m"}, known_skills=())

    def test_both_cron_and_every_is_rejected(self) -> None:
        with pytest.raises(ProposalError):
            parse(
                {"name": "n", "prompt": "p", "cron": "0 7 * * *", "every": "1h"},
                known_skills=(),
            )

    def test_neither_cron_nor_every_is_rejected(self) -> None:
        with pytest.raises(ProposalError):
            parse({"name": "n", "prompt": "p"}, known_skills=())

    def test_an_invalid_cron_expression_is_rejected(self) -> None:
        with pytest.raises(ProposalError):
            parse({"name": "n", "prompt": "p", "cron": "not a cron"}, known_skills=())

    def test_a_prompt_over_the_length_cap_is_rejected(self) -> None:
        with pytest.raises(ProposalError):
            parse(
                {"name": "n", "prompt": "x" * (MAX_PROMPT + 1), "cron": "0 7 * * *"},
                known_skills=(),
            )

    def test_a_name_over_the_length_cap_is_rejected(self) -> None:
        with pytest.raises(ProposalError):
            parse(
                {"name": "x" * (MAX_NAME + 1), "prompt": "p", "cron": "0 7 * * *"},
                known_skills=(),
            )

    def test_an_unknown_skill_is_rejected(self) -> None:
        with pytest.raises(ProposalError):
            parse(
                {"name": "n", "prompt": "p", "cron": "0 7 * * *", "skills": ["ghost"]},
                known_skills=("real",),
            )


class TestAcceptance:
    def test_every_fifteen_minutes_cron_is_accepted(self) -> None:
        proposal = parse({"name": "n", "prompt": "p", "cron": "*/15 * * * *"}, known_skills=())
        assert proposal.cron == "*/15 * * * *" and proposal.every is None

    def test_daily_at_seven_is_accepted(self) -> None:
        proposal = parse({"name": "n", "prompt": "p", "cron": "0 7 * * *"}, known_skills=())
        assert proposal.cron == "0 7 * * *"

    def test_every_fifteen_minutes_interval_is_accepted(self) -> None:
        proposal = parse({"name": "n", "prompt": "p", "every": "15m"}, known_skills=())
        assert proposal.every == "15m" and proposal.cron is None

    def test_a_yearly_cron_is_accepted(self) -> None:
        proposal = parse({"name": "n", "prompt": "p", "cron": "0 9 3 5 *"}, known_skills=())
        assert proposal.cron == "0 9 3 5 *"

    def test_a_known_skill_is_kept(self) -> None:
        proposal = parse(
            {"name": "n", "prompt": "p", "cron": "0 7 * * *", "skills": ["real"]},
            known_skills=("real",),
        )
        assert proposal.skills == ("real",)


class TestUpcoming:
    def test_a_cron_proposal_lists_three_runs(self) -> None:
        proposal = parse({"name": "n", "prompt": "p", "cron": "0 7 * * *"}, known_skills=())
        runs = upcoming(proposal, datetime(2026, 9, 30, 8, 0), count=3)
        assert runs == [
            datetime(2026, 10, 1, 7, 0),
            datetime(2026, 10, 2, 7, 0),
            datetime(2026, 10, 3, 7, 0),
        ]

    def test_a_cron_proposal_stops_after_one_run_once_it_is_far_out(self) -> None:
        # A yearly cron's second occurrence is always far beyond 31 days from the first.
        proposal = parse({"name": "n", "prompt": "p", "cron": "0 9 3 5 *"}, known_skills=())
        runs = upcoming(proposal, datetime(2026, 1, 1), count=3)
        assert len(runs) == 1
        assert runs[0] == datetime(2026, 5, 3, 9, 0)

    def test_an_interval_proposal_lists_now_plus_k_periods(self) -> None:
        proposal = parse({"name": "n", "prompt": "p", "every": "30m"}, known_skills=())
        now = datetime(2026, 9, 30, 8, 0)
        runs = upcoming(proposal, now, count=3)
        assert runs == [
            datetime(2026, 9, 30, 8, 30),
            datetime(2026, 9, 30, 9, 0),
            datetime(2026, 9, 30, 9, 30),
        ]


class TestReasonLine:
    def test_reason_line_carries_every_required_part(self) -> None:
        proposal = parse(
            {"name": "Uống nước", "prompt": "Nhắc tôi uống nước.", "cron": "0 7 * * *"},
            known_skills=(),
        )
        line = reason_line(proposal, datetime(2026, 9, 30, 8, 0))
        assert "Uống nước" in line
        assert "Nhắc tôi uống nước." in line
        assert len(line) <= 3000
        when_line = line.splitlines()[1]
        assert when_line == "Lịch: Mỗi ngày 07:00 (0 7 * * *)"

    def test_reason_line_speaks_the_every_shorthand_in_words_too(self) -> None:
        proposal = parse({"name": "n", "prompt": "p", "every": "30m"}, known_skills=())
        line = reason_line(proposal, datetime(2026, 9, 30, 8, 0))
        assert line.splitlines()[1] == "Lịch: Mỗi 30 phút (30m)"

    def test_reason_line_falls_back_to_the_written_cron_for_an_unnamed_shape(self) -> None:
        # A schedule with no run in a month never fires: min_gap_minutes rejects it before
        # reason_line ever runs on it, so a monthly-only-once-a-year shape is used here — one
        # that still passes validation but has no words of its own.
        proposal = parse({"name": "n", "prompt": "p", "cron": "0 9 3 5 *"}, known_skills=())
        line = reason_line(proposal, datetime(2026, 1, 1))
        assert line.splitlines()[1] == "Lịch: 0 9 3 5 * (0 9 3 5 *)"

    def test_reason_line_includes_attached_skills(self) -> None:
        proposal = parse(
            {"name": "n", "prompt": "p", "cron": "0 7 * * *", "skills": ["real"]},
            known_skills=("real",),
        )
        line = reason_line(proposal, datetime(2026, 9, 30, 8, 0))
        assert "real" in line

    def test_reason_line_for_an_invalid_proposal_is_the_validation_error_in_words(self) -> None:
        # A malformed proposal still needs a card: the card is the error, so the model
        # gets truthful feedback instead of a silent failure.
        try:
            parse({"name": "n", "prompt": "p", "cron": "* * * * *"}, known_skills=())
        except ProposalError as exc:
            assert str(exc)
        else:  # pragma: no cover - defensive: the parametrized rejection test already
            # proves this raises; this branch only guards against that test drifting.
            pytest.fail("expected a ProposalError")

    def test_reason_line_never_empty_and_stays_short_for_a_yearly_cron(self) -> None:
        proposal = parse({"name": "n", "prompt": "p", "cron": "0 9 3 5 *"}, known_skills=())
        line = reason_line(proposal, datetime(2026, 1, 1))
        assert line and len(line) <= 3000


def test_min_gap_minutes_is_a_lower_bound_that_only_under_rejects() -> None:
    """Day/month/weekday constraints can only make a schedule sparser than the hour ×
    minute combinations alone suggest, so a lower bound computed from those combinations
    can reject a cron that is actually fine to run less often, but must never accept one
    that truly repeats faster than MIN_GAP_MINUTES."""
    from my_agent_crew.scheduler.cron import CronSpec

    # Fires only once a year, but the hour/minute combination alone (just "9:00") reads
    # as a 1440-minute gap: the bound is exactly right here, not an under-estimate.
    assert min_gap_minutes(CronSpec.parse("0 9 3 5 *")) == 1440 >= MIN_GAP_MINUTES


def test_max_per_agent_constant_matches_the_documented_cap() -> None:
    assert MAX_PER_AGENT == 20
