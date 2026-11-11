"""Strings of what the person is told when a job that opened no conversation failed, and
when it ran well again (`my_agent_crew/scheduler/failure_notice.py`,
`my_agent_crew/scheduler/failure_streaks.py`). A script's own message is `JOB_SCRIPT_FAILED`
in `texts_script_job.py`. Constants only, and nothing imported.
"""

# Told to the agent's channel when a schedule that runs no script failed: a command, or the
# rewrite of the agent's memory. Three lines as a script's has: which schedule, why, and
# where the run is on the web UI.
JOB_FAILED = (
    'Lịch "{name}" gặp lỗi khi chạy:\n{reason}\nXem lượt chạy ở web UI, mục Quản lý → Hoạt động.'
)

# Why a command failed: the code it left with, and the last line it printed when it printed
# any. One stopped at the limit a command job is given is told by `texts.SHELL_TIMEOUT`,
# the sentence the shell tool has for it.
COMMAND_EXITED = "Lệnh thoát với mã {code}."
COMMAND_LAST_LINE = "Dòng cuối lệnh in ra: {line}"
# What it said went wrong, from the line that reports an error (`scheduler/command_said.py`).
COMMAND_SAID = "Lệnh báo lỗi: {line}"

# Told when the job itself ended well and the command its row states as `check` then left
# with something other than 0 (`scheduler/check.py`): worded apart from `JOB_FAILED`, so
# the person can tell "it said done, the check disagrees" from a job that broke. The reason
# is the check's own: its code and last line, or that it ran past its limit.
JOB_CHECK_FAILED = (
    'Lịch "{name}" báo đã chạy xong, nhưng lệnh kiểm tra sau khi chạy không xác nhận:\n'
    "{reason}\nXem lượt chạy ở web UI, mục Quản lý → Hoạt động."
)
# What such a run is summed up by.
JOB_CHECK_SUMMARY = "Chạy xong nhưng lệnh kiểm tra không xác nhận. {reason}"

# The line every message of a failure ends on: when the next one comes. From the second
# failure in a row it first says how long the job has been failing; `since` is written with
# `JOB_FAILING_SINCE`.
JOB_FAILED_NEXT = "Nếu lịch còn hỏng, tin nhắc kế tiếp sẽ đến sau {hours} giờ."
JOB_FAILED_AGAIN = "Đây là lần hỏng thứ {count} liên tiếp, tính từ {since}. " + JOB_FAILED_NEXT
JOB_FAILING_SINCE = "%H:%M ngày %d/%m"

# Told once when a job the person had been told of ran well again.
JOB_RECOVERED = 'Lịch "{name}" đã chạy lại được sau {count} lần hỏng liên tiếp.'

# Told once when a rewrite of an agent's memory was held for the person to approve
# (`scheduler/proposal_notice.py`): which agent, why it was held, and where to decide.
MEMORY_HELD = (
    "Trí nhớ của {agent} vừa được cô đọng nhưng đang chờ bạn duyệt: {why}\n"
    "Duyệt ở web UI: Hộp thư, hoặc Quản lý → Trí nhớ."
)
