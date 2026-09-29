"""Strings for a turn that stops before its answer, split out of `texts` so neither file
outgrows its budget. Import them from `my_agent_crew.texts`, which re-exports every name here."""

# The halt reasons the loop emits are codes; a person reads these words in their place.
# The web keeps its own copy (`halted*` in web/src/i18n/vi.ts); reword both together.
HALT_REASONS = {
    "budget": "chạm trần chi phí",
    "max_steps": "hết số bước tối đa",
    "loop": "gọi lại y hệt một lệnh nhiều lần liên tiếp",
}
# Told to the model once a run of identical tool calls reaches the guard's threshold. It is
# stored as a user message, so the log shows why the next call changed course; for the same
# reason it names the tools and quotes nothing a tool returned.
LOOP_REDIRECT = (
    "[Hệ thống] Bạn đã gọi {names} với tham số y hệt nhau {count} lần liên tiếp. Kết quả nằm "
    "ngay phía trên; gọi lại y hệt sẽ không cho kết quả khác. Đổi cách làm (sửa tham số, dùng "
    "công cụ khác) hoặc dừng lại và nói rõ điều gì đang chặn bạn. Nếu còn gọi y hệt, lượt này "
    "sẽ bị dừng."
)
# The result of a call the guard refused to run: the turn stopped instead.
LOOP_HALTED_TOOL = (
    "Không chạy: lệnh này đã được gọi y hệt nhiều lần liên tiếp nên lượt bị dừng tại đây."
)
