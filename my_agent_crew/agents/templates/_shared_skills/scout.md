---
name: scout
description: Cách dò một repo lạ để tìm đúng vùng mã liên quan mà không đọc hết mọi thứ.
---
Mục tiêu: trả về **đường dẫn**, không phải nội dung. Người đọc báo cáo sẽ tự mở tệp.

## Thứ tự

1. `workspace_list` ở gốc — nhìn hình dạng dự án (ngôn ngữ, thư mục chính, tệp cấu hình).
2. `workspace_grep` theo từ khoá của việc: tên hàm, tên biến, chuỗi hiển thị, tên bảng.
   Tìm định danh trước, tìm chữ tiếng Việt sau (chuỗi hiển thị thường nằm ở một tệp riêng).
3. `workspace_glob` khi biết dạng tệp cần (`**/*test*.py`, `**/routes_*.py`).
4. Chỉ `workspace_read` khi grep đã chỉ đúng chỗ, và đọc theo cửa sổ (`offset`/`limit`)
   thay vì cả tệp lớn.

## Quy tắc

- Grep trước khi đọc. Một lần grep rẻ hơn mười lần đọc.
- Không đọc tệp trên 500 dòng nguyên khối; đọc quanh dòng grep trả về.
- Bỏ qua thư mục sinh ra: bundle, thư mục phụ thuộc, ảnh chụp test.
- Dừng ở khoảng 30 lần gọi công cụ. Chưa đủ thì nói chưa đủ, đừng dò mãi.
- Thấy hai chỗ cùng làm một việc thì nói ra — trùng lặp là thông tin quan trọng.

## Báo cáo

```
## Scout Report: <việc>

### Tệp liên quan
- `path/to/file.py:120` — mô tả một dòng, vì sao liên quan

### Quy ước đang dùng
- <mẫu code lặp lại mà người sửa nên theo>

### Chưa rõ
- <câu hỏi còn treo, hoặc "không có">
```
