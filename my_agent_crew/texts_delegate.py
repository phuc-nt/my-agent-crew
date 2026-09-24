"""Strings for delegation, split out of `texts` so neither file outgrows its budget.
Import them from `my_agent_crew.texts`, which re-exports every name here."""

DELEGATE_DESCRIPTION = (
    "Giao một việc trọn vẹn cho agent khác và chờ kết quả. Agent con KHÔNG thấy lịch sử "
    "cuộc trò chuyện này, nên `task` phải tự đủ: lời người dùng nguyên văn, hôm nay là "
    "ngày nào, điều chỉ cuộc này biết (người dùng vừa nói gì, đường dẫn tệp đính kèm), kết "
    "quả cần trả về và ràng buộc (ví dụ chỉ đọc). Giao ý định, không giao cách làm: agent "
    "nhận việc tự biết dữ liệu của nó lưu ở đâu và bằng công cụ nào. Không tự đặt tên tệp, "
    "thư mục hay bảng; chỉ nêu đường dẫn có thật (người dùng đưa ra, hoặc bạn đã thấy nó "
    "tồn tại). Viết với tư cách người giao việc, không nhập vai agent nhận. Gọi nhiều lần "
    "trong cùng một lượt để chạy song song. Dùng cho việc lớn, độc lập; việc nhỏ thì tự "
    "làm nhanh hơn."
)
DELEGATE_PARAM_TASK = (
    "Ý định của người dùng cùng ngữ cảnh chỉ cuộc này biết. Không bịa đường dẫn hay chỗ lưu."
)
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
    "hợp kết quả và trả lời người dùng bằng lời của bạn. Giao ý định (lời người dùng "
    "nguyên văn, ngày hôm nay), không giao cách làm hay chỗ lưu: mỗi agent tự biết dữ liệu "
    "của nó nằm đâu. Các agent nhận việc:"
)
# No workspace path: a master that knows where a peer keeps its files starts telling it
# which file to write, and invents the ones it does not know.
CREW_ROSTER_LINE = "- {id} — {name} ({mode}): {description}"

DELEGATED_TURN_TITLE = "Việc được giao"
DELEGATED_TURN_BODY = (
    "Tin nhắn đầu của cuộc này do agent điều phối viết để giao việc, không phải người dùng "
    "gõ. Ý định của người dùng trong đó là việc cần làm. Cách làm mà task gợi ý (tệp nào, "
    "thư mục nào, lưu ở đâu) chỉ là phỏng đoán của agent điều phối: hướng dẫn của bạn và "
    "quy ước của workspace luôn thắng. Không tạo tệp hay thư mục chỉ vì task nhắc tới; nếu "
    "đường dẫn đó chưa có, làm theo cách của bạn và nói trong câu trả lời bạn đã lưu ở đâu. "
    "Câu trả lời cuối gửi về agent điều phối: nêu kết quả và việc đã làm, ngắn gọn."
)
CREW_ROSTER_NO_DESCRIPTION = "chưa có mô tả"
