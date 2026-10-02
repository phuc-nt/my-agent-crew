"""Strings for the canvas tools: what each tool says it is for, what each argument means, and
the lines a result is made of. The refusals the tools share live in `texts_canvas`."""

from __future__ import annotations

# A model that finds the canvas it just made short of what was asked tends to make a second
# one, or to read back every page it has only just sent before rewriting it. The text it wrote
# this turn is still in front of it, and the store counts that version as seen.
CHANGE_IN_PLACE = (
    "Muốn đổi một canvas đã có, kể cả canvas vừa tạo, thì sửa hay viết lại chính nó; đừng tạo"
    " canvas thứ hai cho cùng tài liệu."
)
OWN_WRITE_IS_SEEN = "Không cần đọc lại bản chính bạn vừa tạo hay viết lại trong lượt này."
# A model asked for five lines the person would keep editing wrote them in the chat as a short
# answer: whether the text is kept decides, not its length.
KEPT_GOES_TO_CANVAS = (
    "Tài liệu người sẽ sửa dần, giữ lại hay dùng tiếp thì vào canvas, dù chỉ vài dòng."
)
# An edit only replaces, so new text has to ride on a passage that is already there.
ADD_BY_EDIT = (
    "Muốn thêm chữ mới, chép vào `old` đoạn đứng ngay trước chỗ thêm, rồi trong `new` viết lại"
    " đoạn đó với chữ mới theo sau."
)

# The descriptions decide when a model writes a canvas at all, so each says what belongs in
# one and what stays in the chat, and that a canvas is never copied back into the reply.
ARTIFACT_CREATE_DESCRIPTION = (
    "Tạo một canvas: tài liệu hiện ngay cạnh khung chat, người và bạn cùng sửa được. Dùng cho"
    " nội dung dài hoặc có cấu trúc mà người sẽ đọc lại, sửa hay dùng tiếp: kế hoạch, báo cáo,"
    f" bản nháp, một tệp code hoàn chỉnh. {KEPT_GOES_TO_CANVAS} Câu trả lời chỉ đọc một lần, câu"
    " hỏi và trao đổi thì để trong chat."
    " Sau khi tạo, trong câu trả lời chỉ nói ngắn bạn đã viết gì; đừng chép nội dung canvas vào."
    f" {CHANGE_IN_PLACE}"
)
ARTIFACT_LIST_DESCRIPTION = (
    "Liệt kê các canvas bạn mở được, mới sửa trước: id, tiêu đề, bản mới nhất, và canvas nào có"
    " bản bạn chưa thấy. Dùng để tìm id trước khi đọc hay sửa."
)
ARTIFACT_READ_DESCRIPTION = (
    "Đọc một canvas theo trang, chữ nguyên văn không đánh số dòng. Không truyền version thì đọc"
    " bản mới nhất từ dòng 1; cuối trang có lệnh đọc tiếp, dùng đúng version và from_line đó để"
    " mọi trang thuộc cùng một bản. Đọc tới hết bản mới nhất thì mới viết lại được cả canvas."
    f" {OWN_WRITE_IS_SEEN}"
)
ARTIFACT_EDIT_DESCRIPTION = (
    "Sửa một đoạn của canvas: thay `old`, chép nguyên văn từ canvas và đủ dài để chỉ khớp một"
    " chỗ, bằng `new`. Dùng cho mọi sửa đổi nhỏ và vừa, không cần đọc hết canvas trước."
    f" {ADD_BY_EDIT} Kết quả có diff của phần đã đổi và cỡ mới của canvas."
)
ARTIFACT_REWRITE_DESCRIPTION = (
    "Viết lại toàn bộ canvas bằng `content`. Chỉ dùng khi phải đổi gần hết nội dung; sửa vài"
    " đoạn thì dùng artifact_edit. Phải đọc hết bản mới nhất bằng artifact_read trước."
    f" {OWN_WRITE_IS_SEEN} Nếu từ đó người hay agent khác đã sửa canvas, lần ghi bị từ chối và"
    " bạn nhận diff của phần họ đổi."
)

PARAM_ID = "Id 12 ký tự của canvas, từ artifact_list hoặc từ thẻ [artifact …] của lần ghi trước."
PARAM_TITLE = "Tiêu đề ngắn, một dòng, tối đa 200 ký tự."
PARAM_NEW_TITLE = "Tiêu đề mới, chỉ khi muốn đổi tiêu đề."
PARAM_KIND = "markdown cho văn bản, code cho một tệp mã nguồn."
PARAM_LANGUAGE = "Với kind=code: tên ngôn ngữ, vd. python, typescript. Bỏ trống với markdown."
PARAM_CONTENT = "Toàn bộ nội dung của canvas."
PARAM_QUERY = "Chỉ liệt kê canvas có tiêu đề chứa chuỗi này, không phân biệt hoa thường và dấu."
PARAM_VERSION = "Bản cần đọc; bỏ trống để đọc bản mới nhất."
PARAM_FROM_LINE = "Dòng đầu của trang, đếm từ 1."
PARAM_LINES = "Số dòng tối đa của trang; bỏ trống để lấy nhiều nhất trang chứa được."
PARAM_OLD = "Đoạn cần thay, chép nguyên văn từ canvas."
PARAM_NEW = "Chữ thay vào chỗ `old`; để rỗng là xoá đoạn đó."
PARAM_REPLACE_ALL = "true để thay mọi chỗ khớp `old`, thay vì đòi `old` chỉ khớp một chỗ."

ARTIFACT_CREATED = (
    "Đã tạo canvas «{title}» ({kind}, {size} byte, {lines} dòng). Người thấy nó ngay cạnh khung"
    " chat: trong câu trả lời chỉ nói ngắn bạn đã viết gì, đừng chép lại nội dung."
)
# An edit says how long the canvas now is: a model growing one toward a length it was asked
# for otherwise reads it back, or measures it with a shell, after every edit.
ARTIFACT_EDITED = "Đã thay {count} chỗ; canvas giờ có {size} byte, {lines} dòng."
ARTIFACT_REWRITTEN = "Đã viết lại canvas ({size} byte, {lines} dòng)."
ARTIFACT_UNCHANGED = "Nội dung không đổi nên không thêm bản nào."
ARTIFACT_RENAMED = "Đã đổi tiêu đề thành «{title}»."
ARTIFACT_CONFLICT_DIFF = "Những gì đã đổi từ v{seen}, bản bạn thấy lần cuối, tới v{head}:"

# A page: the header, who wrote the versions not yet seen, the text as it is, the footer.
ARTIFACT_READ_HEADER = (
    "Canvas «{title}» (id {id}, v{version}, {kind}), dòng {span} / {total}{behind}"
)
ARTIFACT_READ_BEHIND = "; bản mới nhất là v{head}"
ARTIFACT_READ_MORE = "Đọc tiếp: artifact_read id={id} version={version} from_line={line}"
ARTIFACT_READ_END = "Hết canvas."

ARTIFACT_LIST_ROW = "- {id} «{title}» ({kind}, v{version}, sửa {when}){flag}"
ARTIFACT_LIST_UNREAD = " — chưa đọc"
ARTIFACT_LIST_NEWER = " — có bản mới (bạn thấy tới v{seen})"
ARTIFACT_LIST_EMPTY = "Chưa có canvas nào bạn mở được."
ARTIFACT_LIST_NO_MATCH = "Không có canvas nào bạn mở được khớp «{query}»."
