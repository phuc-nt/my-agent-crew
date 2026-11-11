"""Strings of the day's cap on what scheduled jobs may cost (`scheduler/day_cap.py`).
Constants only, and nothing imported.
"""

# What a job's run is summed up by when it was skipped because the day's cap was reached.
JOB_CAP_SKIPPED = (
    "Bỏ qua, không chạy: chi phí các lịch hôm nay ({spent} USD) đã chạm hạn mức {cap} USD"
    " (jobs_daily_cost_cap_usd)."
)

# Told once a day to the channel of the first job skipped: what was spent, what the cap is,
# what is skipped from now on, and where the cap is set.
JOB_CAP_REACHED = (
    "Chi phí các lịch chạy hôm nay đã là {spent} USD, chạm hạn mức {cap} USD một ngày.\n"
    'Từ giờ đến hết ngày, các lịch gọi model bị bỏ qua, bắt đầu từ "{name}"; lịch chạy lệnh'
    " vẫn chạy, và trò chuyện không bị ảnh hưởng.\n"
    "Đổi hạn mức ở khoá jobs_daily_cost_cap_usd trong config.yaml."
)
