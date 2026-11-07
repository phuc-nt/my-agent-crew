"""What a failed command job is summed up and told by when it printed why it failed and then
more: the line that reports the error and what follows it, not the end of all it printed.

A backup script logs `ERROR: gws delete that bai:` and then the JSON body of the refusal, so
the end of its output is a lone `}`, and the last `PREVIEW_CHARS` of it open inside an id.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.scheduler.command_said import what_failed
from my_agent_crew.scheduler.jobs import command_failure
from my_agent_crew.store.runs import FAILED
from tests.test_scheduler import with_schedules

REFUSED = (
    "2026-11-06 19:21:16 db: health.db.gz.gpg (8.1M)\n"
    "2026-11-06 19:21:16 ERROR: gws delete that bai: {\n"
    '  "error": {\n'
    '    "code": 403,\n'
    '    "message": "DELETE /drive/v3/files/1cX9%2Dl4V: not a write open to the home",\n'
    '    "reason": "unknown"\n'
    "  }\n"
    "}\n"
)
SAID = (
    '2026-11-06 19:21:16 ERROR: gws delete that bai: { "error": { "code": 403, "message": '
    '"DELETE /drive/v3/files/1cX9%2Dl4V: not a write open to the home", "reason": "unknown" } }'
)


@pytest.mark.parametrize(
    ("output", "said"),
    [
        (REFUSED, SAID),
        ("Traceback:\n  x\nValueError: hết chỗ\n", "ValueError: hết chỗ"),
        (
            "thử lần 1 lỗi: mạng\nthử lần 2 Lỗi: hết hạn\n  chi tiết\n",
            "thử lần 2 Lỗi: hết hạn chi tiết",
        ),
        ("sao lưu thất bại: ổ đầy", "sao lưu thất bại: ổ đầy"),
        ('{"error": {"code": 1}}\n', ""),
        ("lỗi ở stderr\n", ""),
        ("", ""),
    ],
    ids=[
        "json body",
        "exception",
        "last of two",
        "vietnamese",
        "json key only",
        "no colon",
        "empty",
    ],
)
def test_what_failed_is_read_from_the_last_line_that_reports_an_error(output, said):
    assert what_failed(output) == said


def test_a_command_that_reported_its_error_is_told_by_what_it_said():
    assert command_failure(1, REFUSED) == f"Lệnh thoát với mã 1. Lệnh báo lỗi: {SAID}"
    # Nothing reports an error: the last line still says it.
    assert command_failure(2, "đang chép\nổ đầy\n") == (
        "Lệnh thoát với mã 2. Dòng cuối lệnh in ra: ổ đầy"
    )


async def test_a_failed_command_run_is_summed_up_from_the_line_that_reports_its_error(
    deps_factory, tmp_path
):
    printed = tmp_path / "out.txt"
    printed.write_text(REFUSED)
    job = Schedule("backup", "Sao lưu", every="1h", command=f"cat '{printed}'; exit 1")
    deps = with_schedules(deps_factory(), job)
    sched = Scheduler(
        {"default": deps}, ActivityHub(deps.store), clock=lambda: datetime(2026, 11, 6)
    )

    run = await sched.run_job("default/backup")

    assert run.status == FAILED
    assert run.summary == SAID[:160] + "…"
    assert run.summary.startswith("2026-11-06 19:21:16 ERROR: gws delete that bai:")
