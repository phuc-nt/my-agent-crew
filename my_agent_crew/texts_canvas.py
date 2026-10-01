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
