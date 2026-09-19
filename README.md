# my-agent-crew

Một agent vạn năng, chạy local, có web UI thân thiện. Agent đọc/ghi tệp trong thư mục làm việc,
tải trang web, tìm kiếm, ghi nhớ — và **hỏi bạn trước** mọi thao tác thay đổi dữ liệu.

Đây là bản viết lại tinh gọn của [my-crew](https://github.com/phuc-nt/my-crew): bỏ đội nhiều vai,
router, DAG; giữ một agent + công cụ + kỹ năng, đặt web UI làm mặt tiền chính.

## Chạy

```bash
uv sync
OPENROUTER_API_KEY=... uv run python -m my_agent_crew
# mở http://127.0.0.1:8765
```

Không có khoá? Chạy thử với provider echo (không gọi model thật):

```bash
MY_AGENT_ROUTES=fake:echo uv run python -m my_agent_crew
```

Trong chế độ echo, gõ `/tool <tên> {json}` để gọi công cụ trực tiếp, ví dụ
`/tool workspace_list {"path":"."}`.

## Cấu hình

Bí mật **chỉ** đọc từ biến môi trường; `config.yaml` chỉ chứa các khoá không nhạy cảm.

| Biến môi trường | Ý nghĩa | Mặc định |
|---|---|---|
| `MY_AGENT_HOME` | thư mục dữ liệu (db, workspace/, skills/, config.yaml) | `~/.my-agent-crew` |
| `MY_AGENT_ROUTES` | chuỗi tuyến `provider:model`, cách nhau bởi dấu phẩy, thử theo thứ tự | `openrouter:deepseek/deepseek-v4-flash` |
| `MY_AGENT_COST_CAP_USD` | ngân sách mặc định mỗi cuộc trò chuyện (0 = không giới hạn) | `0.5` |
| `MY_AGENT_MAX_STEPS` | số lượt gọi model tối đa trong một lượt | `12` |
| `MY_AGENT_AUTONOMOUS` | `1` để công cụ ghi/thay đổi chạy không cần duyệt | tắt |
| `OPENROUTER_API_KEY` | bật provider OpenRouter | — |
| `TAVILY_API_KEY` / `BRAVE_API_KEY` | bật công cụ `web_search` | — |

`config.yaml` trong `MY_AGENT_HOME` nhận `routes`, `cost_cap_usd`, `max_steps`, `language`,
`autonomous_default`. Kỹ năng tự viết: thêm tệp `.md` có frontmatter `name` vào `skills/`.

## Phát triển

```bash
uv run pytest -q                 # backend
cd web && npm ci
npm run typecheck && npm test    # frontend unit
npm run e2e                      # Playwright (mock /api trong trình duyệt)
npm run bundle                   # dựng lại bundle vào my_agent_crew/server/static (đã commit)
```

Đọc [docs/design.md](docs/design.md) để hiểu các quyết định thiết kế và
[docs/testing.md](docs/testing.md) để biết tính năng nào được test ở tầng nào.
