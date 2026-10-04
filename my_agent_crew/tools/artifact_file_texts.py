"""Strings for the two tools that carry a canvas to and from a workspace file: what each says
it is for, what each argument means, the lines of a result and the refusals only they make.
A result names the file, its size and a digest, never what the file holds: whoever wrote the
file must not be able to put words into what a model reads back from a tool."""

from __future__ import annotations

ARTIFACT_IMPORT_DESCRIPTION = (
    "Đưa một tệp đã có trong thư mục làm việc vào canvas mà không chép nội dung qua tin nhắn:"
    " một trang đã dựng, một hình SVG xuất từ công cụ khác, một ảnh, một tài liệu. Đừng đọc tệp"
    " rồi chép vào artifact_create. Loại canvas suy từ đuôi tệp; đuôi không nói đúng loại thì"
    " truyền `kind`. Muốn sửa mã nguồn của một trang HTML như văn bản thì nhập với kind: code,"
    " language: html. Ảnh chỉ vào canvas bằng tool này, và chỉ thay được bằng cách nhập lại với"
    " `id`. Có `id` thì tệp thay bản mới nhất của canvas đó, bản cũ vẫn ở lịch sử; chỉ đặt"
    " replace: true khi người muốn thay phần đã sửa trên canvas. `source_url` là link tới bản"
    " gốc, khi tệp chỉ là một bản xuất. Kết quả không kèm nội dung tệp."
)
ARTIFACT_EXPORT_DESCRIPTION = (
    "Ghi một bản của canvas ra một tệp trong thư mục làm việc mà không chép nội dung qua tin"
    " nhắn. Ghi đè tệp đích nếu đã có. Văn bản ra UTF-8 không BOM, xuống dòng LF; ảnh ra đúng"
    " từng byte. Cần người duyệt trước khi ghi. Canvas không đổi."
)

PARAM_IMPORT_PATH = "Đường dẫn của tệp cần nhập, tính từ thư mục làm việc."
PARAM_IMPORT_ID = (
    "Id 12 ký tự của canvas có sẵn mà tệp sẽ thay bản mới nhất; bỏ trống để tạo canvas mới."
)
PARAM_IMPORT_TITLE = "Tiêu đề canvas; bỏ trống thì lấy tên tệp, hoặc giữ tiêu đề đang có."
PARAM_IMPORT_KIND = "Loại canvas, chỉ khi đuôi tệp không nói đúng; bỏ trống để suy từ đuôi."
PARAM_SOURCE_URL = "Link http hoặc https tới bản gốc của tệp, nếu tệp chỉ là một bản xuất."
PARAM_REPLACE = "true để thay cả những bản bạn chưa thấy; chỉ khi người muốn thay phần đã sửa."
PARAM_EXPORT_PATH = "Đường dẫn của tệp đích, tính từ thư mục làm việc; đuôi tệp do bạn chọn."
PARAM_EXPORT_VERSION = "Bản cần xuất; bỏ trống để xuất bản mới nhất."

IMPORT_CREATED = "Đã nhập {path} thành canvas «{title}» ({kind}, {size} byte, sha256 {digest})."
IMPORT_REPLACED = (
    "Đã nhập {path} vào canvas «{title}», thay v{replaced} ({kind}, {size} byte, sha256 {digest})."
)
IMPORT_KEPT_IN_HISTORY = "Các bản bạn chưa thấy vẫn ở lịch sử của canvas."
# A picture is not offered for reading: `artifact_read` refuses one.
IMPORT_SOURCE = "Nguồn: {source}. Người mở canvas trên web để xem."
IMPORT_SOURCE_READABLE = (
    "Nguồn: {source}. Người mở canvas trên web để xem; đọc nội dung bằng artifact_read nếu cần."
)
IMPORT_SOURCE_RECORDED = "Đã ghi nguồn mới: {source}."
SOURCE_WORKSPACE = "workspace {path}"
# The count alone: an example would be text of the file's own choosing.
IMPORT_RELATIVE_REFS = (
    "Cảnh báo: trang dùng {count} đường dẫn tương đối. Canvas không nạp tệp ngoài; nhúng chúng"
    " vào trang (data URI, CSS nội tuyến) nếu cần thấy."
)
EXPORT_DONE = "Đã xuất v{version} của canvas {id} «{title}» ({size} byte) ra {path}."
EXPORT_REPLACED = " Đã thay tệp có sẵn."

IMPORT_UNKNOWN_KIND = (
    "`kind` phải là một trong {kinds}, hoặc bỏ trống để suy từ đuôi tệp. Chưa nhập gì."
)
IMPORT_KIND_MISMATCH = (
    "Canvas {id} là {kind}, và nhập vào một canvas có sẵn không đổi được loại của nó. Chưa nhập"
    " gì: bỏ `kind`, hoặc bỏ `id` để nhập tệp thành một canvas mới."
)
IMPORT_WOULD_OVERWRITE = (
    "Canvas {id} đã tới v{head} và có những bản bạn chưa thấy, nên tệp sẽ đè lên phần bạn chưa"
    " đọc.{authors} Chưa nhập gì. Chọn một: đọc bản mới nhất bằng artifact_read rồi gộp; xuất"
    " bản hiện tại ra một tệp khác bằng artifact_export; hoặc gọi lại với replace: true khi"
    " người muốn thay phần đã sửa."
)
IMPORT_BAD_URL = (
    "`source_url` phải là một link http hoặc https có tên máy chủ, tối đa {limit} ký tự, không"
    " có khoảng trắng hay ký tự ẩn. Chưa nhập gì."
)
IMPORT_BAD_PATH = (
    "`path` phải là một đường dẫn không rỗng, tối đa {limit} ký tự, không có ký tự điều khiển"
    " hay ký tự ẩn. Chưa làm gì."
)
EXPORT_TARGET_IS_LINK = (
    "{path} là một liên kết (symlink) nên không ghi đè lên. Chưa xuất gì: chọn đường dẫn khác."
)
EXPORT_FAILED = "Không ghi được {path}. Tệp cũ ở đó, nếu có, còn nguyên."
