"""Kept in step, case for case, with `web/src/lib/cron-text.test.ts`: the same cron read the
same way in both places, since a person reads this exact wording on an approval card and the
Jobs tab reads the same schedule with the same function's web counterpart."""

from __future__ import annotations

import pytest

from my_agent_crew.tools.schedule_words import cron_words, every_words, schedule_words

READS_AS_WORDS = [
    ("0 7 * * *", "Mỗi ngày 07:00"),
    ("30 21 * * *", "Mỗi ngày 21:30"),
    ("0 8,20 * * *", "Mỗi ngày 08:00, 20:00"),
    ("0 7 * * 0-6", "Mỗi ngày 07:00"),
    ("0 9 * * 1-5", "Thứ Hai–Thứ Sáu 09:00"),
    ("0 9 * * 1,2,3,4,5", "Thứ Hai–Thứ Sáu 09:00"),
    ("0 10 * * 0,6", "Cuối tuần 10:00"),
    ("0 10 * * 6,7", "Cuối tuần 10:00"),
    ("0 18 * * 5", "Thứ Sáu hằng tuần 18:00"),
    ("0 20 * * 7", "Chủ Nhật hằng tuần 20:00"),  # Sunday written either way
    ("0 20 * * 0,1", "Thứ Hai, Chủ Nhật hằng tuần 20:00"),  # read last, as a week is
    ("0 * * * *", "Mỗi giờ"),
    ("15 * * * *", "Mỗi giờ vào phút 15"),
    ("0 */2 * * *", "Mỗi 2 giờ"),
    ("5 */6 * * *", "Mỗi 6 giờ vào phút 5"),
    ("* * * * *", "Mỗi phút"),
    ("*/15 * * * *", "Mỗi 15 phút"),
    ("0 3 1 * *", "Ngày 1 hằng tháng 03:00"),
    ("  0 7 * * *  ", "Mỗi ngày 07:00"),
]

# Every shape below is valid to the scheduler, but a sentence for it would either be long or
# leave something out; the cron itself is the honest answer.
LEFT_AS_WRITTEN = [
    "0 7 * 1 *",
    "0 7 1 * 1",
    "0 7-9 * * *",
    "*/10 9 * * *",
    "0 */5,7 * * *",
    "0 7 * * 5-1",
    "0 7 * * 8",
    "61 7 * * *",
    "0 24 * * *",
    "0 7 32 * *",
    "*/0 * * * *",
    # A step that does not divide the hour or the day restarts at :00 or at midnight, so the
    # last gap is shorter: "every 7 minutes" would be wrong once an hour.
    "*/7 * * * *",
    "*/45 * * * *",
    "0 */5 * * *",
    "0 */7 * * *",
    "0 */10 * * *",
    "0 7 * *",
    "@daily",
    "",
]


@pytest.mark.parametrize(("cron", "words"), READS_AS_WORDS)
def test_cron_words_reads_a_recognised_shape_in_words(cron: str, words: str) -> None:
    assert cron_words(cron) == words


@pytest.mark.parametrize("cron", LEFT_AS_WRITTEN)
def test_cron_words_leaves_an_unrecognised_shape_as_written(cron: str) -> None:
    assert cron_words(cron) == cron


def test_every_words_reads_the_shorthand_in_the_units_the_scheduler_accepts() -> None:
    assert every_words("30m") == "Mỗi 30 phút"
    assert every_words("1h") == "Mỗi giờ"
    assert every_words("2 d") == "Mỗi 2 ngày"
    assert every_words("90s") == "Mỗi 90 giây"
    assert every_words("1w") == "1w"


def test_schedule_words_uses_whichever_key_the_schedule_is_written_with() -> None:
    assert schedule_words("0 7 * * *", None) == "Mỗi ngày 07:00"
    assert schedule_words(None, "30m") == "Mỗi 30 phút"
    assert schedule_words(None, None) == ""
