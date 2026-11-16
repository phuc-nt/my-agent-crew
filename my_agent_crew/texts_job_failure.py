"""Strings of why a job failed, as its run is summed up: a command's code and last line,
and a check that disagreed (`my_agent_crew/scheduler/jobs.py`,
`my_agent_crew/scheduler/check.py`). Constants only, and nothing imported.
"""

# Why a command failed: the code it left with, and the last line it printed when it printed
# any. One stopped at the limit a command is given is told by `texts.SHELL_TIMEOUT`, the
# sentence the shell tool has for it.
COMMAND_EXITED = "Lệnh thoát với mã {code}."
COMMAND_LAST_LINE = "Dòng cuối lệnh in ra: {line}"
# What it said went wrong, from the line that reports an error (`scheduler/command_said.py`).
COMMAND_SAID = "Lệnh báo lỗi: {line}"

# What a run is summed up by when the job itself ended well and the command its row states
# as `check` then left with something other than 0 (`scheduler/check.py`). The reason is the
# check's own: its code and last line, or that it ran past its limit.
JOB_CHECK_SUMMARY = "Chạy xong nhưng lệnh kiểm tra không xác nhận. {reason}"
