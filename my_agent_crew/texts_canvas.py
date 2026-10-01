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

# Who wrote the versions the agent has not seen yet, oldest first: "v3–v5 người, v6 agent:coach".
AUTHOR_PERSON = "người"
ARTIFACT_AUTHORS = "Các bản bạn chưa thấy: {groups}."

# The same words for a canvas that does not exist and one out of the agent's reach, so the
# answer never tells an agent which canvases exist beyond its reach.
ARTIFACT_NOT_FOUND = "Không tìm thấy canvas {id}. Xem các canvas bạn mở được bằng artifact_list."
ARTIFACT_CHANNEL_CLOSED = (
    "Kênh của lượt này chưa mở được canvas (mới chỉ web chat mở được), nên chưa ghi gì. Viết"
    " thẳng nội dung vào câu trả lời."
)
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
