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

# The line every message of a failure ends on: when the next one comes. From the second
# failure in a row it first says how long the job has been failing; `since` is written with
# `JOB_FAILING_SINCE`.
JOB_FAILED_NEXT = "Nếu lịch còn hỏng, tin nhắc kế tiếp sẽ đến sau {hours} giờ."
JOB_FAILED_AGAIN = "Đây là lần hỏng thứ {count} liên tiếp, tính từ {since}. " + JOB_FAILED_NEXT
JOB_FAILING_SINCE = "%H:%M ngày %d/%m"

# Told once when a job the person had been told of ran well again.
JOB_RECOVERED = 'Lịch "{name}" đã chạy lại được sau {count} lần hỏng liên tiếp.'
