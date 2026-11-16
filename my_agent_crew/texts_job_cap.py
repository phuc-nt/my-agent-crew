"""Strings of the day's cap on what scheduled jobs may cost (`scheduler/day_cap.py`).
Constants only, and nothing imported.
"""

# What a job's run is summed up by when it was skipped because the day's cap was reached.
JOB_CAP_SKIPPED = (
    "Bỏ qua, không chạy: chi phí các lịch hôm nay ({spent} USD) đã chạm hạn mức {cap} USD"
    " (jobs_daily_cost_cap_usd)."
)
