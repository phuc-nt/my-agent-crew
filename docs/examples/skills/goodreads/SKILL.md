---
name: goodreads
description: "Goodreads: đọc kệ sách và hoạt động qua RSS công khai, ghi (rate, đổi kệ, tiến độ, review) qua phiên trình duyệt riêng. Không cần API key."
requires:
  bins: [python3]
cliHelp: "python3 <skills_dir>/goodreads/scripts/goodreads-rss.py --help"
---

# Goodreads

API Goodreads đóng từ 12/2020. Còn lại hai đường: **RSS công khai** để đọc, và **điều khiển
trình duyệt** để ghi. Hai đường đó tách hẳn nhau, và chỉ đường đọc chạy thẳng được.

## Đọc — chạy thẳng, không cần duyệt

```bash
S=<skills_dir>/goodreads/scripts/goodreads-rss.py

python3 $S shelf --shelf currently-reading --limit 10   # đang đọc
python3 $S shelf --shelf read --limit 20 --sort date_read
python3 $S shelf --shelf to-read --limit 20
python3 $S activity --limit 10                          # hoạt động gần đây
```

**Không cần truyền user id.** Script tự đọc `scripts/goodreads.json`. Truyền id ở vị trí
đầu chỉ khi muốn xem kệ của người khác.

Mỗi lệnh in một object JSON có `ok: true`. Lỗi đi ra **stderr** kèm khoá `fix` nói phải làm
gì — stdout luôn sạch để pipe vào `jq`.

## Hai lệnh hiện KHÔNG dùng được

`book <id>` và `search <query>` đọc trang HTML chứ không đọc feed, và Goodreads đang chặn:
nó trả HTTP 202 với **thân rỗng** thay vì báo lỗi. Script phát hiện và trả JSON lỗi thay vì
trả một bản ghi toàn `null` trông như câu trả lời thật.

Gặp lỗi đó thì **báo người dùng**, đừng thử scrape bằng cách khác. Thông tin về một cuốn
sách vẫn lấy được từ `shelf` nếu sách nằm trong kệ của người dùng.

## Ghi — luôn hỏi trước

```bash
W=<skills_dir>/goodreads/scripts/goodreads-write.sh

$W status                          # phiên còn sống không
$W rate <book_id> <1-5>
$W shelf <book_id> <read|currently-reading|to-read>
$W progress <book_id> <percent>
$W review <book_id> "<cả bài review>"   # thay bài cũ nếu đã có
```

Review đăng công khai dưới tên người dùng: chỉ đăng **đúng lời người dùng viết**,
không tự thêm, bớt hay dịch.

`book_id` lấy từ kết quả `shelf` (khoá `book_id`).

**Luôn hỏi người dùng trước khi chạy một lệnh ghi**, kể cả khi đang autonomous. Những lệnh
này đổi hồ sơ công khai của người dùng và không có nút hoàn tác. Thêm `goodreads-write` vào
`shell_ask_patterns` của agent để lệnh ghi luôn dừng chờ duyệt.

### Không bao giờ gọi `login`

`$W login` mở một cửa sổ trình duyệt thật và đợi người gõ mật khẩu. Chạy trong một lượt
job thì cửa sổ đó không có ai trước mặt, và lượt chạy treo tới khi hết giờ. Wrapper đã từ
chối khi không có terminal, nhưng đây vẫn là lệnh của người, không phải của agent.

Phiên hết hạn thì mọi lệnh ghi trả:

```json
{"ok": false, "error": "session expired", "fix": "run goodreads-write.sh login in a terminal, then retry"}
```

Gặp dòng đó thì **báo người dùng chạy `login` ở terminal**, đừng tự mở trình duyệt.

### Thiếu môi trường Playwright

Lần đầu chạy, wrapper trả JSON kèm đúng ba lệnh để dựng `.venv` và tải Chromium. Đọc khoá
`fix` rồi đưa lệnh đó cho người dùng.

## Khi Goodreads đổi trang

Mọi lệnh ghi tìm nút theo `aria-label`. Đổi giao diện thì lệnh trả lỗi nói rõ không tìm
thấy nút nào. **Báo người dùng**, đừng đoán selector khác — đoán trên một trang đã đăng
nhập là cách bấm nhầm vào thứ không định bấm.

## Chép về

Chép cả thư mục vào một nơi trong `skills_dirs`, rồi tạo `scripts/goodreads.json` từ
`scripts/goodreads.json.example` và điền id Goodreads của bạn (chuỗi số trong URL hồ sơ).
Không có tệp đó thì mọi lệnh đọc dừng lại và nói đúng phải tạo gì.
