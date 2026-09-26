---
layout: default
title: Bản đồ mã nguồn
---

# Bản đồ mã nguồn

**Phiên bản**: 0.8.0 · **Cập nhật**: 2026-09-26

Đọc [system-architecture.md](system-architecture.md) trước để biết các khối là gì; tài liệu này
chỉ nói khối nào nằm ở **gói** nào. Tên tệp, hàm và số liệu không ghi ở đây: mã nguồn là nguồn
sự thật, mở thư mục là thấy.

## 1. Bố cục repo

```
my-agent-crew/
├── my_agent_crew/        # backend Python
│   ├── server/static/    # bundle web đã build, commit cùng repo
│   ├── skills/builtin/   # skill có sẵn
│   └── agents/templates/ # mẫu agent cho `agent add`
├── web/                  # SPA React + Vite; vitest + Playwright
├── tests/                # pytest
├── docs/                 # tài liệu này + diagrams/
├── scripts/gates.sh      # mọi cổng CI, chạy trước khi commit
├── pyproject.toml        # uv, ruff
└── .github/workflows/ci.yml
```

## 2. Backend `my_agent_crew/`

| Gói | Chịu trách nhiệm |
|---|---|
| `agent/` | vòng lặp một lượt: ghép lời nhắc, gọi mô hình, chạy tool, dừng chờ duyệt, chạy tiếp, cắt ngữ cảnh dài, sự kiện của lượt |
| `agents/` | hồ sơ agent từ đĩa: đọc/ghi `agent.yaml` giữ chú thích, vá và kiểm tra, roster cho master, đọc kit `.agents/`, mẫu agent |
| `activity/` | run và step của mọi lượt, phát cho web qua SSE |
| `channels/` | Telegram: poll, tin vào, ảnh và album, tin ra, lệnh `/…`, câu trả lời cho `ask_user`, offset, che token |
| `inbound.py` | một cổng vào chung cho mọi nền tảng |
| `llm/` | provider: OpenRouter, Ollama, provider giả; chuỗi tuyến và fallback |
| `memory/` | ghi chú ngày, facts chung, gom 7 ngày thành đề xuất, tìm kiếm, tóm tắt cuộc trước, vault wiki |
| `scheduler/` | cron: phân tích lịch, job đến hạn, chạy job, giao kết quả ra kênh |
| `server/` | FastAPI: dựng runtime, lắp provider và tool cho từng agent, áp dụng kết nối không cần restart, kiểm tra khoá, ghi `<home>/env`, hàng rào Host/Origin, các nhóm route |
| `skills/` | nạp skill markdown, chỉ mục trong lời nhắc |
| `store/` | SQLite: cuộc trò chuyện, tin, duyệt, run, trạng thái job, đề xuất trí nhớ, sổ chi tiêu |
| `tools/` | mọi tool: workspace, shell và sandbox, web, trí nhớ, wiki, giao việc, hỏi người dùng, PDF, ảnh, skill, hook |
| `config*.py` | cài đặt từ env + `config.yaml` |
| `texts*.py` | mọi chuỗi tiếng Việt của backend |
| `__main__.py` | CLI: `python -m my_agent_crew`, `agent list-templates`, `agent add` |

Một lượt phát ra một chuỗi sự kiện (chữ, tin trợ lý, gọi tool, kết quả tool, cần duyệt, xong,
dừng, lỗi, đổi tuyến). Cùng một chuỗi vừa là SSE cho web, vừa là step ghi vào run.

## 3. API

| Nhóm | Đường |
|---|---|
| Sức khoẻ | `GET /api/health` |
| Cổng vào | `POST /api/inbound` |
| Cuộc trò chuyện | `GET/POST/DELETE /api/conversations[/{id}]`, `POST …/{id}/messages` (SSE), `GET …/{id}/summary` |
| Duyệt | `GET /api/approvals`, `POST /api/conversations/{id}/approvals/{aid}` (`{"approve": bool}`), `POST …/approvals/{aid}/answer` (câu hỏi của `ask_user`) |
| Run | `GET /api/activity/runs`, `GET …/runs/{id}`, `GET …/stream` (SSE), `GET /api/stats` |
| Agent | `GET /api/agents`, `GET …/{id}`, `GET …/{id}/files`, `POST /api/agents/install`, `GET /api/templates` |
| Sửa agent | `POST /api/agents`, `PATCH …/{id}`, `DELETE …/{id}` |
| Tệp tính cách | `PUT /api/agents/{id}/files/{name}`, `GET …/{id}/prompt` (lời nhắc hệ thống đã ghép), `POST /api/agents/reload` |
| Tool & kết nối | `GET /api/tools`, `GET /api/connections` |
| Khoá & biến môi trường | `GET /api/credentials`, `PUT/DELETE …/{name}` (ghi `<home>/env`, áp dụng ngay), `POST …/{name}/check`; không trả giá trị bí mật; thay đổi làm đội không chạy được bị từ chối 409, không ghi gì |
| Tuyến mô hình chung | `PUT /api/connections/routes` (lưu vào `config.yaml` giữ chú thích; khi `MY_AGENT_ROUTES` đặt thì chỉ xem, không sửa) |
| Trí nhớ agent | `GET/PUT /api/agents/{id}/memory`, `GET/PUT …/memory/notes/{day}`, `POST …/memory/consolidate` |
| Wiki | `GET /api/agents/{id}/memory/wiki`, `GET/PUT/DELETE …/wiki/pages/{slug}`, `GET …/wiki/report`, `POST …/wiki/compile` |
| Trí nhớ người dùng | `GET/PUT /api/memory/user`, `…/user/facts/{name}`, `GET /api/memory/proposals[/{id}]`, `GET /api/memory/search` |
| Job | `GET /api/jobs`, `GET …/{id}/runs`, `PATCH …/{id}/state` (tạm dừng/chạy lại), `POST …/{id}/run` |
| Cài đặt | `GET /api/settings` |

Mọi đường không phải `/api/*` trả SPA. Web định tuyến bằng hash, nên một lượt chạy có đường
riêng: `#/manage/activity/<run_id>` mở đúng lượt đó, tải lại vẫn ở đó, và chia sẻ được.

## 4. Web `web/`

| Thư mục | Nội dung |
|---|---|
| `src/api/` | client HTTP, đọc SSE, kiểu dữ liệu |
| `src/screens/` | hai màn: chat và quản lý (chín tab) |
| `src/hooks/` | tải và giữ trạng thái từng mảng: hội thoại, hoạt động, agent, trí nhớ, wiki, kết nối, route hash, phím tắt |
| `src/state/` | reducer cho luồng chat và hoạt động |
| `src/components/` | mọi thành phần giao diện, mỗi mảng quản lý một nhóm |
| `src/lib/` | hàm thuần dùng chung (diff, tiến độ run, kết quả giao việc) |
| `src/i18n/` | mọi chuỗi tiếng Việt của web |
| `src/styles/` | CSS theo mảng; `tokens.css` giữ thang chữ, khoảng cách, màu sáng/tối |
| `public/` | favicon, icon cài app và manifest, chép nguyên vào gốc bundle |
| `scripts/` | `render-icons.mjs`: vẽ các PNG icon từ `public/favicon.svg` |
| `e2e/` | spec Playwright + mock `/api` |

Script: `dev`, `typecheck`, `test` (vitest), `bundle` (build → `my_agent_crew/server/static`), `e2e`,
`icons` (vẽ lại icon sau khi sửa logo).

## 5. Test

Ba tầng (pytest, vitest, Playwright) và cách chạy ở [testing.md](testing.md). Provider giả
`MY_AGENT_ROUTES=fake:echo` cho phép chạy cả harness không cần mạng.

## 6. Mẫu agent và skill có sẵn

- `agents/templates/`: `fullstack-developer`, `kongming`, `researcher`, và `_shared_skills/` dùng chung.
- `skills/builtin/`: `cite-sources`.

Cài bằng `python -m my_agent_crew agent add <template> [--id <id>] [--force] [--workspace <dir>]` hoặc `POST /api/agents/install`.

## 7. Bộ tài liệu

| Tệp | Cho ai |
|---|---|
| [index.md](index.md) | điểm vào, thứ tự đọc |
| [system-architecture.md](system-architecture.md) | người mới, giải phẫu harness với 5 sơ đồ |
| [codebase-summary.md](codebase-summary.md) | định hướng theo gói trước khi mở code |
| [deployment-guide.md](deployment-guide.md) | người cài và vận hành, cách publish doc |
| [project-overview-pdr.md](project-overview-pdr.md) | vấn đề, phạm vi, tiêu chí |
| [code-standards.md](code-standards.md) | quy ước code, test, commit, bí mật, tài liệu |
| [CHANGELOG.md](../CHANGELOG.md) | thay đổi của từng bản phát hành |
| [design.md](design.md), [agents.md](agents.md), [tools.md](tools.md), [memory.md](memory.md), [channels.md](channels.md), [testing.md](testing.md) | tham chiếu từng mảng |
| [diagrams/](diagrams/README.md) | spec, HTML, SVG của 5 sơ đồ |

## Câu hỏi mở

- `server/static/` được commit và CI kiểm `git diff --exit-code` sau `bundle`; khi web đổi nhiều, diff commit sẽ lớn — chưa quyết có chuyển sang build lúc cài hay không.
