"""Strings for the Telegram channel, split out of `texts` so neither file outgrows its
budget. Import them from `my_agent_crew.texts`, which re-exports this module's names."""

TELEGRAM_CONVERSATION_TITLE = "Telegram · {date}"
TELEGRAM_NEW_CONVERSATION = "Đã mở cuộc trò chuyện mới."
# Fills `{how}` of REPLY_APPROVAL: on Telegram the decision is a slash command.
TELEGRAM_APPROVAL_HOW = "gửi /approve để duyệt, /deny để từ chối"
SHELL_ASK_REASON = "khớp mẫu cần duyệt: `{pattern}`"
TELEGRAM_APPROVAL_EXPIRED = (
    "Yêu cầu duyệt công cụ {name} đã hết hạn chờ, agent tiếp tục như bị từ chối."
)
TELEGRAM_BUSY = "Cuộc trò chuyện đang chờ bạn duyệt một công cụ: /approve hoặc /deny."
TELEGRAM_MEDIA_MISSING = "(không gửi được ảnh: {path})"
# Said in the chat when a `FILE:` line names something that cannot be sent. The reason
# rides along because the person reading it is usually the one who asked for the file.
TELEGRAM_FILE_MISSING = "(không gửi được tệp: {path})"
TELEGRAM_FILE_SUFFIX = "định dạng không gửi qua chat được; chỉ nhận: {kinds}"
TELEGRAM_FILE_TOO_BIG = "tệp {size:.1f} MB, quá mức {cap:.0f} MB cho chat"
# Said when a `FILE: artifact:<id>` line names a canvas the chat does not get. None repeats
# what the model wrote: `{id}` is an id that was read as one. A canvas that is not there and
# one out of the agent's reach share a sentence, so a reply cannot tell which ids exist.
TELEGRAM_CANVAS_MISSING = "(không gửi được canvas {id}: không tìm thấy canvas này)"
TELEGRAM_CANVAS_BAD_REF = "(không gửi được canvas: dòng đính kèm ghi sai mã canvas)"
TELEGRAM_CANVAS_SOURCE = (
    "(không gửi được canvas {id}: nó được nhập từ một tệp thuộc loại không gửi qua chat được)"
)
TELEGRAM_CANVAS_FAILED = "(không gửi được canvas {id}; mở web UI để xem nó)"
# Under the file a canvas arrives as: its title and the version that was sent.
TELEGRAM_CANVAS_CAPTION = '"{title}" v{version}'
# The list a chat is sent of the canvases a turn wrote: a canvas shows on the web alone, so
# the chat is told what to look for there. The address is on a line of its own, so a title
# cannot run into it; without one the last line says where to look.
TELEGRAM_CANVAS_HEADER = "Canvas vừa ghi:"
TELEGRAM_CANVAS_LINE = '• "{title}" v{version}'
TELEGRAM_CANVAS_LINK_LINE = "  {link}"
TELEGRAM_CANVAS_MORE = "… và {n} canvas khác."
TELEGRAM_CANVAS_OPEN_WEB = "Mở web UI để xem."
TELEGRAM_CANVAS_NOTICE_FAILED = (
    "(lượt này có ghi canvas nhưng không gửi được danh sách; mở web UI để xem)"
)
# What the agent reads when the person sends photos or a file: one line per saved path,
# the caption (if any) after them, so the model treats the attachments as part of the message.
# The web thread finds these lines by their words (`attachmentSaved` in web/src/i18n/vi.ts)
# to draw each file; reword both together.
TELEGRAM_ATTACHMENT_LINE = "[Tệp đính kèm đã lưu: {path}]"
TELEGRAM_ATTACHMENT = "{files}\n{caption}"
TELEGRAM_ATTACHMENT_FAILED = "Không tải được tệp đính kèm từ Telegram ({error}); gửi lại giúp."
TELEGRAM_RUN_UNFINISHED = (
    "Lượt chạy dừng mà chưa có câu trả lời ({reason}); xem chi tiết trên web UI."
)
TELEGRAM_RUN_CUT_SHORT = (
    "Lượt chạy dừng sớm ({reason}), đã chi ${spent:.4f}; "
    "câu trả lời trên có thể chưa đủ. Xem web UI."
)
TELEGRAM_COMMANDS = {
    "new": "Mở cuộc trò chuyện mới.",
    "reset": "Mở cuộc trò chuyện mới (giống /new).",
    "help": "Liệt kê các lệnh.",
    "status": "Trạng thái cuộc trò chuyện hôm nay.",
    "tools": "Các công cụ agent đang có.",
    "approve": "Duyệt công cụ đang chờ.",
    "deny": "Từ chối công cụ đang chờ.",
    "steer": "Chèn ý vào lượt đang chạy.",
}
TELEGRAM_HELP_LINE = "/{command} — {description}"
# The last line of /help: what a message sent while the agent works becomes.
TELEGRAM_HELP_BUSY = (
    "Nhắn khi agent đang làm thì tin xếp hàng chờ lượt sau; "
    "/steer <nội dung> thì chèn vào lượt đang chạy."
)
TELEGRAM_UNKNOWN_COMMAND = "Không có lệnh /{command}. Gửi /help để xem các lệnh."
TELEGRAM_STATUS = (
    "{title}\n"
    "Lượt: {turns} · đã chi ${spent:.4f} / ${cap:.2f}\n"
    "Model: {routes}\n"
    "Trạng thái: {state}\n"
    "Lần chạy gần nhất: {run}"
)
TELEGRAM_STATE_IDLE = "sẵn sàng"
TELEGRAM_STATE_RUNNING = "đang chạy · {queued} tin xếp hàng"
TELEGRAM_STATE_OVER_BUDGET = "hết ngân sách"
TELEGRAM_STATE_AWAITING = "đang chờ duyệt {name} (/approve, /deny)"
TELEGRAM_RUN_NONE = "chưa có"
TELEGRAM_RUN = "{status}, {steps} bước, {started}"
TELEGRAM_TOOLS = "Công cụ ({count}):\n{names}"
TELEGRAM_NO_APPROVAL = "Không có công cụ nào đang chờ duyệt."
# /new while a turn runs or messages wait: those stay in the conversation they came to.
TELEGRAM_NEW_BUSY = (
    "Agent đang làm dở hoặc còn tin xếp hàng; đợi xong rồi hãy /new, hoặc dừng lượt trên web UI."
)
# A turn that broke without an answer; only the error's kind is named, the log has the rest.
TELEGRAM_TURN_FAILED = "Lượt vừa rồi hỏng giữa chừng ({error}); xem log hoặc gửi lại giúp."
# The first line of a crew member's brief delivered to the master's chat.
TELEGRAM_AGENT_PREFIX = "[{name}]"
# Sent when a stop (the bot's token or chat changed from the web) cut off a turn.
# Said whether the stop came from a connection change or the server shutting down, and
# whether or not part of the reply had already gone out — hence "may" and "if".
# Said in place of TELEGRAM_CUT_OFF when it is the server that is going down: the turn it cut
# is taken up again when the server is back, once, if nothing stands in its way.
TELEGRAM_CUT_RESUMES = (
    "Server đang khởi động lại nên lượt vừa rồi bị ngắt giữa chừng. Khi server chạy lại, lượt "
    "này sẽ được làm tiếp một lần nếu còn làm tiếp được; nếu sau đó vẫn không thấy câu trả lời "
    "thì gửi lại giúp mình nhé."
)
TELEGRAM_CUT_OFF = (
    "Tin nhắn vừa rồi có thể chưa được trả lời trọn vẹn vì bot vừa khởi động lại. "
    "Nếu bạn chưa nhận đủ câu trả lời, gửi lại giúp mình nhé."
)
TRANSCRIBE_SYSTEM = (
    "Bạn chép lời một đoạn ghi âm sang chữ. Chép nguyên văn từng từ, đúng ngôn ngữ nói,"
    " không tóm tắt, không thêm bớt, không bình luận. Nghe không rõ thì chỉ trả lời"
    " đúng chuỗi [không nghe rõ], không đoán."
)
# Said right after a voice note is transcribed, so the sender can catch a mishearing
# before it reaches the agent. Cut to 500 characters with an ellipsis: a long clip must
# not turn this confirmation into the whole answer.
TELEGRAM_VOICE_HEARD = "Đã nghe: {text}"
TELEGRAM_VOICE_NO_ROUTE = (
    "Chưa bật chép lời voice: cần cấu hình audio_routes (biến môi trường"
    " MY_AGENT_AUDIO_ROUTES) trỏ tới một model nghe được audio."
)
TELEGRAM_VOICE_TOO_LONG = "Voice dài {seconds:.0f} giây, quá mức {limit:.0f} giây cho chép lời."
TELEGRAM_VOICE_TOO_BIG = "Voice nặng {size:.1f} MB, quá mức {limit:.1f} MB cho chép lời."
TELEGRAM_VOICE_FORMAT = "Không nhận ra định dạng voice này; gửi lại bằng voice note hoặc mp3/m4a."
TELEGRAM_VOICE_FAILED = "Không chép được lời voice ({reason}); gửi lại giúp."
VOICE_REASON_TIMEOUT = "hết giờ chờ"
VOICE_REASON_ROUTE_ERROR = "tuyến chép lời lỗi"
VOICE_REASON_UNCLEAR = "không nghe rõ tiếng nói"
# Opens the turn the master sees, right after the attachment line: names the transcript as
# what it is (a machine's guess at speech) so the model reads it with the same caution the
# person just got from "Đã nghe: …", and never as a caption written by the sender.
TELEGRAM_VOICE_TURN = "{file}\nTin nhắn thoại (lời chép, có thể nghe sai): {text}\n{caption}"
