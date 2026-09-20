---
name: git
description: "Stage và commit an toàn: xem trước, chọn tệp, viết conventional commit."
---
## Trình tự

1. `git status --short` — xem có gì.
2. `git diff --stat` (và `git diff` phần đáng ngờ) — biết mình sắp commit cái gì.
3. `git add <đường dẫn cụ thể>` — liệt kê tệp, **không** `git add -A` khi chưa nhìn status.
4. `git commit -m "<type>(<scope>): <mô tả>"`.

## Không bao giờ

- `git checkout`, `git reset`, `git stash`, `git revert`, `git clean` — những lệnh này xoá
  việc người khác đang làm dở. Muốn lùi thì báo lại, đừng tự lùi.
- `git push --force` dưới mọi hình thức.
- `git rebase`, sửa lịch sử đã đẩy đi.
- Stage thư mục phụ thuộc, tệp `.env`, khoá, token, chứng chỉ, dữ liệu cá nhân.
  Thấy những thứ này trong `status` thì dừng và báo.

## Lời nhắn commit

`feat` tính năng · `fix` sửa lỗi · `refactor` dọn mã · `test` test · `docs` tài liệu ·
`perf` tốc độ · `build` đóng gói.

- Dòng đầu ≤ 72 ký tự, thức mệnh lệnh, không dấu chấm cuối.
- Nói **cái gì đổi và vì sao**, không kể lại tên tệp — diff đã nói rồi.
- Có lý do đáng nhớ thì thêm thân dòng sau một dòng trống.
- Không thêm dòng ghi công công cụ hay đồng tác giả máy.
- Không đặt mã plan hay số phase vào lời nhắn.

## Báo cáo

Hash ngắn + dòng đầu của commit, và những tệp đã cố ý **không** stage.
