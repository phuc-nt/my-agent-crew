"""Strings about canvases: what the canvas tools tell the agent, and the marks the diff and
the nearest-region search leave where they shorten a long line. Imported from here rather
than through `texts`, which is at its line budget."""

# A long line shown in part: what was left out before and after the part that matters.
LINE_CUT_HEAD = "({n} ký tự trước) …"
LINE_CUT_TAIL = "… (+{n} ký tự)"
# Lines left out of a diff or a region that ran out of room.
LINES_CUT = "… (+{n} dòng)"
# One change in a diff, numbered as in the text after the change.
DIFF_HUNK = "@@ dòng {span} @@"

ARTIFACT_EDIT_EMPTY_OLD = (
    "`old` không được rỗng. Muốn chèn chữ thì lấy một đoạn có sẵn ngay cạnh chỗ chèn làm `old`,"
    " rồi viết lại đoạn đó kèm chữ mới trong `new`."
)
ARTIFACT_EDIT_NO_MATCH = (
    "Không thấy `old` trong canvas, kể cả khi coi nháy cong là nháy thẳng và dấu cách đặc biệt là"
    " dấu cách. Chưa sửa gì. Đọc lại đoạn cần sửa bằng artifact_read rồi chép nguyên văn vào `old`."
)
ARTIFACT_EDIT_NEAREST = (
    "Chỗ giống nhất nằm trong dòng {span}, chép ở khung dưới đây. Nếu đúng là chỗ cần sửa, chép"
    " nguyên văn phần cần sửa vào `old`; dấu … đánh dấu phần bị lược, đừng chép nó."
)
ARTIFACT_EDIT_AMBIGUOUS = (
    "`old` khớp {count} chỗ trong canvas, chưa sửa gì. Thêm vài chữ xung quanh để `old` chỉ đúng"
    " một chỗ, hoặc đặt replace_all=true nếu muốn thay tất cả."
)
ARTIFACT_EDIT_TOO_LARGE = (
    "Sau khi sửa, canvas sẽ nặng {size} byte, quá trần {cap} byte của loại này. Chưa sửa gì: bớt"
    " nội dung, hoặc chuyển phần dài sang một canvas khác."
)
# Said where a diff would be when a change spreads over too many lines to compare line by line.
ARTIFACT_EDIT_DIFF_WIDE = (
    "Chỗ đã đổi trải qua quá nhiều dòng để liệt kê từng chỗ khác biệt. Cần kiểm tra kết quả thì"
    " đọc lại bằng artifact_read."
)
ARTIFACT_CONFLICT_WIDE = (
    "Từ v{seen}, bản bạn thấy lần cuối, tới v{head} đã đổi quá nhiều dòng để liệt kê từng chỗ:"
    " đọc bản mới nhất bằng artifact_read thay vì xem phần khác biệt."
)

# Who wrote the versions the agent has not seen yet, oldest first: "v3–v5 người, v6 agent:coach".
AUTHOR_PERSON = "người"
AUTHOR_RESTORE = "{author} khôi phục v{version}"
ARTIFACT_AUTHORS = "Các bản bạn chưa thấy: {groups}."

# The same words for a canvas that does not exist and one out of the agent's reach, so the
# answer never tells an agent which canvases exist beyond its reach.
ARTIFACT_NOT_FOUND = "Không tìm thấy canvas {id}. Xem các canvas bạn mở được bằng artifact_list."
ARTIFACT_CHANNEL_CLOSED = (
    "Kênh của lượt này chưa mở được canvas (mới chỉ web chat mở được), nên chưa ghi gì. Viết"
    " thẳng nội dung vào câu trả lời."
)
# The tail of the system prompt for a turn whose channel cannot write a canvas, said before
# the model puts a whole document into a call only to hear `ARTIFACT_CHANNEL_CLOSED`.
CANVAS_CLOSED_TITLE = "Canvas"
CANVAS_CLOSED_BODY = "Kênh này chưa mở được canvas: trả lời thẳng trong tin nhắn, đừng gọi {tools}."
ARTIFACT_WRITE_BUDGET = (
    "Lượt này đã ghi {limit} bản cho canvas này, chạm trần của một lượt, nên chưa ghi gì. Dừng"
    " sửa và báo người những gì đã làm; lượt sau ghi tiếp được."
)
ARTIFACT_CREATE_BUDGET = (
    "Lượt này đã tạo {limit} canvas, chạm trần của một lượt, nên chưa tạo gì. Báo người những gì"
    " đã làm; lượt sau tạo tiếp được."
)
ARTIFACT_KIND_CLOSED = "Agent chưa ghi được loại canvas này. Các loại ghi được: {kinds}."
ARTIFACT_TOO_LARGE = (
    "Canvas {kind} sẽ nặng {size} byte, quá trần {cap} byte của loại này. Chưa lưu gì: chia nội"
    " dung thành nhiều canvas nhỏ hơn."
)
ARTIFACT_BAD_TITLE = "Tiêu đề cần có chữ và dài tối đa {limit} ký tự. Chưa lưu gì."
ARTIFACT_BAD_LANGUAGE = (
    "`language` là tên ngắn của ngôn ngữ lập trình, chỉ gồm chữ, số và +#._-, tối đa {limit} ký"
    " tự, vd. python, typescript, c++. Chưa lưu gì."
)
ARTIFACT_STORAGE_FULL = (
    "Các canvas đã dùng {used} trên {cap} byte agent được dùng. Chưa lưu gì. Đừng thử lại: báo"
    " người để họ xoá bớt canvas cũ."
)
ARTIFACT_VERSION_GONE = (
    "v{version} không còn, bản mới nhất là v{head}. Đọc lại từ bản mới nhất: artifact_read id={id}."
)
ARTIFACT_VERSION_CONFLICT = (
    "Canvas đã có bản mới hơn (v{head}) từ lần cuối bạn thấy nó, nên chưa ghi gì. Đọc lại bằng"
    " artifact_read rồi sửa bằng artifact_edit."
)
ARTIFACT_ARG_TEXT = "`{name}` cần là một chuỗi chữ. Chưa làm gì."
ARTIFACT_NO_CONVERSATION = "Canvas chỉ dùng được trong một cuộc trò chuyện. Chưa làm gì."
ARTIFACT_REWRITE_UNSEEN = (
    "Bạn chưa đọc hết bản mới nhất của canvas này nên chưa viết lại được, chưa ghi gì. Sửa từng"
    " đoạn bằng artifact_edit, hoặc đọc hết bằng artifact_read id={id} rồi mới viết lại."
)
ARTIFACT_READ_PAST_END = "v{version} có {total} dòng; from_line phải từ 1 tới {total}."
ARTIFACT_READ_BINARY = "Canvas này là {kind}; agent chưa đọc được loại này."
# What an earlier turn's canvas write carries in the prompt in place of the document text
# it sent: where that text went, that it went nowhere, or that the write was cut off before
# anyone learnt which. The store keeps the text itself.
CANVAS_PAYLOAD_SAVED = (
    "[đã lược {chars} ký tự; lần ghi này đã vào artifact {id} v{version}, đọc lại bằng"
    " artifact_read]"
)
CANVAS_PAYLOAD_FAILED = "[đã lược {chars} ký tự; lần ghi này thất bại, chưa lưu gì]"
CANVAS_PAYLOAD_CUT_OFF = (
    "[đã lược {chars} ký tự; lần ghi này bị ngắt giữa chừng, không rõ đã lưu chưa: xem"
    " artifact_list trước khi ghi lại]"
)

# The canvas note stored with a person's message and read in front of it: what changed in
# the conversation's canvases since its agent last heard, and what is open in the web chat.
# A canvas's own text inside it is quoted, never part of the frame.
CANVAS_NOTE_OPEN = "[Canvas — ghi chú của hệ thống]"
CANVAS_NOTE_CLOSE = "[Hết ghi chú canvas]"
# What an earlier turn's note becomes in the prompt: the canvases have moved on since.
CANVAS_NOTE_STUB = "[Canvas — ghi chú cũ đã lược; đọc canvas bằng artifact_read nếu cần]"
CANVAS_NOTE_FOCUS = "Canvas đang mở trên web: «{title}» (id {id}, v{version})."
# The passage the person selected, quoted under this line; `where` is one of the PICK_ forms.
CANVAS_NOTE_PICK = "Người đang chọn trong «{title}» (id {id}), {where}:"
PICK_LINES = "dòng {span} của v{version}"
PICK_TEXT = "trên v{version}, tìm theo chữ"
PICK_OLD = "trên v{version} (bản mới nhất là v{head}), tìm theo chữ"
PICK_GONE = "trên một bản đã gộp (bản mới nhất là v{head}), tìm theo chữ"
CANVAS_NOTE_NEW = "Hội thoại có canvas bạn chưa đọc: «{title}» (id {id}), bản mới nhất v{head}."
CANVAS_NOTE_EDITED = "Người đã sửa «{title}» (id {id}) từ v{base} lên v{head}:"
CANVAS_NOTE_BUMP = "«{title}» (id {id}) đã lên v{head}."
CANVAS_NOTE_READ = "Đọc bằng artifact_read."
CANVAS_NOTE_LARGE = "Người đã sửa nhiều chỗ trong «{title}» (id {id}), từ v{base} lên v{head}."
CANVAS_NOTE_MORE = "…và {n} canvas khác đã đổi; xem bằng artifact_list."

# Said above a diagram's source when the page could not load the library that draws it: no
# network, or a file that is not the one the page pins.
RENDER_MERMAID_OFFLINE = (
    "Không tải được thư viện Mermaid (có thể đang mất mạng) nên đây là mã nguồn của sơ đồ."
)
