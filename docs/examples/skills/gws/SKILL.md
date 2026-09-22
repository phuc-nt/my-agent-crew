---
name: gws
description: "Google Workspace cho Pong qua `gws` CLI: Gmail, Calendar, Tasks, Sheets, Drive, Docs. Auth dùng chung, đã sẵn sàng."
requires:
  bins: [gws]
cliHelp: "gws <service> --help"
---

# gws — Google Workspace

`gws` đã cấu hình sẵn auth (credentials mã hoá + keyring, token tự refresh). Gọi thẳng,
không cần setup gì.

**Mọi lệnh gọi qua wrapper**, không gọi `gws` trần:

```bash
~/.my-agent-crew/skills-personal/gws/scripts/gws-run.sh <service> <args...>
```

Wrapper chặn hai thứ phá auth dùng chung, và khi `gws` lỗi thì in ra một dòng JSON nói
phải làm gì — đỡ đoán lại cùng một lệnh cho tới hết số bước.

## Bốn điều tuyệt đối không

1. **Không chạy `gws auth login`.** Lệnh này mở browser; dưới một job không có ai bấm
   nên process treo tới khi hết giờ. Wrapper từ chối sẵn.
2. **Không set `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE`** và không dùng
   `--credentials-file`. Nó đè credentials đang chạy tốt, và triệu chứng là 401 ở một
   chỗ hoàn toàn khác. Wrapper từ chối sẵn.
3. **Không export `credentials.json` ra plain text**, không đọc nó vào câu trả lời.
4. **Gặp 401 thì không tự xử.** Báo người dùng chạy `gws auth status` ở terminal, ghi rõ
   lệnh nào lỗi, rồi làm tiếp việc khác.

## Đọc thì chạy thẳng, ghi thì hỏi trước

Lệnh **đọc** (`+agenda`, `+triage`, `list`, `read`) chạy ngay.

Lệnh **ghi** (`+send`, `+reply`, `+reply-all`, `+insert`, `+append`, `+upload`, `+write`,
`tasks insert/patch/delete`) thì **soạn nháp, hỏi người dùng bằng `ask_user`, có "ok" mới
chạy** — kể cả khi đang autonomous. Hàng rào thật nằm ở `shell_ask_patterns` trong
`agent.yaml`: lệnh ghi khớp mẫu sẽ dừng chờ duyệt dù quyền tự chủ có bật.

## Cú pháp hay sai

- Helper **phải có tiền tố `+`**: `gws gmail +reply` đúng, `gws gmail reply` sai.
- Gmail reply dùng `--message-id`, **không phải** `--messageId`.
- Thời gian là RFC3339 kèm offset Việt Nam `+07:00`.
- Chưa chắc cú pháp thì chạy `gws <service> --help` hoặc
  `gws schema <service>.<resource>.<method>` **một lần**, đừng đoán cờ.

## Tài khoản

Chép thư mục này vào `skills_dirs` của agent rồi điền id thật ở đây. Bản trong repo
chỉ giữ cấu trúc; id tài khoản không thuộc về một repo công khai.

- Gmail: `<EMAIL>` · Calendar: `primary`
- Drive cá nhân: `<DRIVE_FOLDER_ID>`
- Sheets chi tiêu: `<SPREADSHEET_ID>` (Ngày | Số tiền | Mô tả | Category)

## Calendar

```bash
gws-run.sh calendar +agenda --today
gws-run.sh calendar +agenda --days 7
gws-run.sh calendar +insert --summary 'Họp X' \
  --start '2026-05-20T09:00:00+07:00' --end '2026-05-20T09:30:00+07:00'   # GHI → hỏi trước
```

## Gmail

```bash
gws-run.sh gmail +triage --max 20
gws-run.sh gmail +triage --max 30 --query 'newer_than:7d'
gws-run.sh gmail +send --to <email> --subject 'S' --body 'B'        # GHI → hỏi trước
gws-run.sh gmail +reply --message-id <id> --body '...'              # GHI → hỏi trước
```

## Tasks

```bash
gws-run.sh tasks tasks list --params '{"tasklist":"@default","showCompleted":false}'
gws-run.sh tasks tasks insert --params '{"tasklist":"@default"}' \
  --json '{"title":"..."}'                                          # GHI → hỏi trước
gws-run.sh schema tasks.tasks.insert
```

## Sheets / Drive / Docs

```bash
gws-run.sh sheets read --spreadsheet <id> --range 'Sheet1!A1:D20'
gws-run.sh sheets +append --spreadsheet <id> --values 'a,100,note'  # GHI → hỏi trước
gws-run.sh drive +upload ./file.pdf --parent <folder-id>            # GHI → hỏi trước
gws-run.sh docs +write --document <doc-id> --text '...'             # GHI → hỏi trước
```
