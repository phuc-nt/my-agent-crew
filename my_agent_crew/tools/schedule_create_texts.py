"""Strings for the schedule-create tool and its approval card.

They live apart from `my_agent_crew/texts.py` only because that file is at its size
budget; there is no other reason to look for them here."""

from __future__ import annotations

#: The description is the whole interface the model decides from. It says what the tool
#: is for (a repeating job, not a one-time reminder), that every proposal is reviewed
#: individually, and that a one-off request belongs elsewhere — without that last part a
#: model reaches for this tool the moment anyone mentions a time at all.
SCHEDULE_CREATE_DESCRIPTION = (
    "Đề xuất một việc LẶP LẠI theo lịch (ví dụ: mỗi sáng, mỗi giờ, mỗi thứ Hai)."
    " Không dùng cho một việc chỉ làm MỘT LẦN — việc một lần không cần lịch."
    " Mỗi đề xuất sẽ được người dùng xem và duyệt riêng, kể cả khi hội thoại đang tự động;"
    " nếu người dùng từ chối, đừng đề xuất lại cùng một lịch."
)

SCHEDULE_NAME_DESCRIPTION = "Tên ngắn gọn cho lịch, tối đa 60 ký tự."
SCHEDULE_PROMPT_DESCRIPTION = (
    "Nguyên văn câu lệnh sẽ chạy mỗi lần tới lịch, tối đa 2000 ký tự."
    " Người dùng sẽ đọc đúng câu này trước khi duyệt, nên viết đầy đủ, rõ ràng."
)
SCHEDULE_CRON_DESCRIPTION = (
    "Biểu thức cron 5 trường (phút giờ ngày tháng thứ), ví dụ '0 7 * * *' cho 7 giờ sáng"
    " mỗi ngày. Chỉ định đúng một trong hai trường cron hoặc every."
)
SCHEDULE_EVERY_DESCRIPTION = "Khoảng lặp lại, ví dụ '30m', '2h', '1d'. Tối thiểu 15 phút."
SCHEDULE_SKILLS_DESCRIPTION = "Tên các skill cần gắn kèm mỗi lần lịch chạy, nếu có."

#: The one sentence every card carries beyond the schedule itself: what approving it
#: actually means. Per-run oversight stops the moment this is approved — the reason line
#: is the only place that is said, so it has to say it plainly.
SCHEDULE_UNWATCHED_WARNING = (
    "Sau khi duyệt, lịch sẽ tự chạy mỗi lần tới giờ mà KHÔNG hỏi lại từng bước;"
    " chỉ lệnh shell khớp mẫu cần duyệt riêng mới bị chặn, và một lượt chạy không ai trông"
    " mà cần duyệt việc khác sẽ bị từ chối vì hết hạn."
)

SCHEDULE_REASON_HEADER = "Đề xuất lịch: {name}"
SCHEDULE_REASON_WHEN = "Lịch: {words} ({written})"
SCHEDULE_REASON_UPCOMING_HEADER = "Các lần chạy kế tiếp:"
#: An `every` schedule counts from the moment the scheduler first sees it, which is when
#: the person approves, not when the card was drawn — so its times can only be approximate.
SCHEDULE_REASON_UPCOMING_APPROX_HEADER = "Các lần chạy kế tiếp (khoảng, tính từ lúc duyệt):"
SCHEDULE_REASON_SKILLS = "Skill đi kèm: {skills}"
SCHEDULE_REASON_PROMPT_HEADER = "Nguyên văn sẽ chạy:"

SCHEDULE_CREATED = "Đã tạo lịch {name!r} (id {id}). Lần chạy kế tiếp: {next_run}."
SCHEDULE_CREATED_NO_UPCOMING = "Đã tạo lịch {name!r} (id {id})."

#: A proposal that is otherwise valid but the agent already holds the maximum chat-created
#: schedules — not a validation error, since nothing about the proposal itself is wrong;
#: the limit is checked atomically by the store, not by `schedule_proposal.parse`.
SCHEDULE_LIMIT_REACHED = "Agent này đã có {cap} lịch tạo từ chat, đây là mức tối đa cho phép."

#: Validation errors. A malformed proposal still gets a card, and one of these is its whole
#: reason, so each says what to change rather than what went wrong internally.
SCHEDULE_ERR_NEEDS_ONE_OF = "Cần đúng một trong hai: cron hoặc every."
SCHEDULE_ERR_NAME_MISSING = "Cần đặt một tên ngắn cho lịch."
SCHEDULE_ERR_NAME_TOO_LONG = "Tên lịch dài quá {limit} ký tự."
SCHEDULE_ERR_PROMPT_MISSING = "Cần nội dung sẽ chạy mỗi lần tới lịch."
SCHEDULE_ERR_PROMPT_TOO_LONG = "Nội dung dài quá {limit} ký tự."
SCHEDULE_ERR_EVERY_INVALID = "every không hợp lệ: {error}"
SCHEDULE_ERR_EVERY_TOO_SHORT = "every phải từ 15 phút trở lên."
SCHEDULE_ERR_EVERY_TOO_LONG = (
    "every không được dài quá 366 ngày, nếu không lịch sẽ không bao giờ chạy."
)
SCHEDULE_ERR_CRON_INVALID = "Biểu thức cron không hợp lệ: {error}"
SCHEDULE_ERR_CRON_TOO_LONG = "Biểu thức cron dài quá {limit} ký tự."
SCHEDULE_ERR_CRON_TOO_FREQUENT = (
    "Cron này có hai lần chạy chỉ cách nhau {gap} phút; cần cách nhau ít nhất 15 phút."
)
SCHEDULE_ERR_CRON_NEVER_RUNS = "Cron này không có lần chạy nào trong 366 ngày tới."
SCHEDULE_ERR_SKILLS_NOT_A_LIST = "skills phải là danh sách tên skill."
SCHEDULE_ERR_UNKNOWN_SKILL = "Không có skill tên {name!r}."

#: A schedule in words, the same phrasing `web/src/lib/cron-text.ts` takes from `vi.ts`.
SCHEDULE_WORDS_UNITS = {"s": "giây", "m": "phút", "h": "giờ", "d": "ngày"}
SCHEDULE_WORDS_DAY_NAMES = (
    "Chủ Nhật",
    "Thứ Hai",
    "Thứ Ba",
    "Thứ Tư",
    "Thứ Năm",
    "Thứ Sáu",
    "Thứ Bảy",
)
SCHEDULE_WORDS_EVERY_ONE = "Mỗi {unit}"
SCHEDULE_WORDS_EVERY_N = "Mỗi {n} {unit}"
SCHEDULE_WORDS_AT_MINUTE = "{every} vào phút {minute}"
SCHEDULE_WORDS_DAILY = "Mỗi ngày {time}"
SCHEDULE_WORDS_WEEKDAYS = "Thứ Hai–Thứ Sáu {time}"
SCHEDULE_WORDS_WEEKEND = "Cuối tuần {time}"
SCHEDULE_WORDS_WEEKLY = "{days} hằng tuần {time}"
SCHEDULE_WORDS_MONTHLY = "Ngày {date} hằng tháng {time}"
