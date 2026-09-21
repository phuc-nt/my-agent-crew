"""Strings for delegation, split out of `texts` so neither file outgrows its budget.
Import them from `my_agent_crew.texts`, which re-exports every name here."""

DELEGATE_DESCRIPTION = (
    "Giao một việc trọn vẹn cho agent khác và chờ kết quả. Agent con KHÔNG thấy lịch sử "
    "cuộc trò chuyện này, nên `task` phải tự đủ: mục tiêu, tệp cần đọc, tệp được phép "
    "sửa, tiêu chí chấp nhận, ràng buộc. Gọi nhiều lần trong cùng một lượt để chạy song "
    "song. Dùng cho việc lớn, độc lập; việc nhỏ thì tự làm nhanh hơn."
)
DELEGATE_PARAM_TASK = "Mô tả việc, đầy đủ và tự đủ ngữ cảnh."
DELEGATE_PARAM_AGENT = (
    "Id agent nhận việc (xem mục 'Đội của bạn' trong hướng dẫn). Bỏ trống = giao cho chính "
    "mình trong một ngữ cảnh sạch."
)
DELEGATE_PARAM_SKILLS = "Tên các kỹ năng bật sẵn cho cuộc con."

DELEGATE_NOT_ALLOWED = "Không được giao việc cho agent {target}. Được phép: {allowed}."
DELEGATE_NO_PEERS = "chỉ chính mình"
DELEGATE_TOO_DEEP = (
    "Agent con không được giao việc tiếp. Tự làm phần việc này hoặc báo lại cho agent cha."
)
DELEGATE_TOO_MANY = (
    "Một lượt chỉ giao được tối đa {limit} việc. Việc này bị bỏ qua; giao lại ở lượt sau."
)
DELEGATE_CONVERSATION_TITLE = "{agent}: {task}"
DELEGATE_RESULT_HEADER = "conversation={conv_id} status={status} spent=${spent:.4f} steps={steps}"
DELEGATE_TIMEOUT = "Hết thời gian chờ agent con. Xem cuộc {conv_id} để biết nó đang ở đâu."

CREW_ROSTER_TITLE = "Đội của bạn"
CREW_ROSTER_INTRO = (
    "Bạn điều phối đội agent dưới đây. Việc nhỏ, hỏi đáp, trò chuyện, việc cần ngữ cảnh "
    "cuộc trò chuyện này: tự làm. Việc lớn, độc lập, hoặc đúng chuyên môn của một agent: "
    "dùng `delegate` (giao nhiều việc trong cùng một lượt để chạy song song), rồi tự tổng "
    "hợp kết quả và trả lời người dùng bằng lời của bạn. Các agent nhận việc:"
)
CREW_ROSTER_LINE = "- {id} — {name} ({mode}): {description} · workspace: {workspace}"
CREW_ROSTER_NO_DESCRIPTION = "chưa có mô tả"
