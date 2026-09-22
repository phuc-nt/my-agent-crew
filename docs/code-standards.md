---
layout: default
title: Quy ước code
---

# Quy ước code

**Phiên bản**: 0.3.0 · **Cập nhật**: 2026-09-22

## 1. Python

- Python 3.12+, `uv` quản lý môi trường. `uv sync` rồi `uv run …`.
- `ruff` với `line-length = 100`, rule `E, F, I, UP, B`. Trước khi commit: `uv run ruff check --fix . && uv run ruff format .`.
- Định danh (module, hàm, biến, key YAML, cột DB, tên event, id agent) **100% tiếng Anh**. Tiếng Việt chỉ xuất hiện trong `texts.py` / `texts_*.py` (backend) và `web/src/i18n/vi.ts` (web). Không viết chuỗi hiển thị trực tiếp trong code logic.
- Mỗi tệp một mối quan tâm; tệp trên ~200 dòng thì cân nhắc tách theo ranh giới có sẵn (`routes_*.py`, `telegram_*.py`, `texts_*.py` là ví dụ).
- Docstring đầu module nói *vì sao* module tồn tại, không lặp lại tên hàm.
- Không đưa id plan, số phase, nhãn audit vào comment, tên test, hay commit message.

## 2. Web

- TypeScript strict, React 19, không thư viện state ngoài reducer trong `state/`.
- `npm run typecheck && npm test` trước khi commit; `npm run bundle` khi đổi web để cập nhật `my_agent_crew/server/static` (CI kiểm diff).
- Chuỗi hiển thị trong `i18n/vi.ts`. Tên component kebab-case, một component một tệp.

## 3. Test

- Mỗi tính năng có test cùng lúc với code; bộ test phải đi theo code, không để sau.
- Backend: pytest + provider giả (`fake:echo`) và home tạm (`tmp_path`). Không đụng `~/.my-agent-crew` thật.
- Web: vitest cho component/hook; Playwright cho luồng người dùng với `e2e/mock-api.ts` mock toàn bộ `/api` bằng regex neo gốc (glob `**/api/**` nuốt cả module nguồn Vite).
- Neo test vào failure mode (điều gì sai thì test đỏ), không neo vào ngưỡng số tuỳ ý.
- Xem [testing.md](testing.md) cho lệnh và bố cục.

## 4. Commit

- Conventional commits: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`. Tiếng Việt hay tiếng Anh đều được, ngắn gọn, nói việc gì và vì sao.
- Một commit một việc. Không commit `node_modules/`, tệp env, DB, log.
- Không thêm dòng attribution.

## 5. Bí mật và dữ liệu cá nhân

- Token, API key, chat id, dữ liệu người dùng (persona thật, `MEMORY.md`, facts, workspace) sống trong `~/.my-agent-crew/` — **ngoài repo**. Repo chỉ chứa mẫu (`agents/templates/`) và tài liệu.
- Cấu hình chỉ ghi tên biến môi trường (`token_env`), không ghi giá trị.
- Log đi qua redact (`TelegramApi.redact`, filter trên logger `httpx`). Khi thêm client HTTP mới có secret, thêm redact tương ứng và một test khẳng định secret không xuất hiện trong log.
- Tài liệu và ví dụ dùng placeholder (`<chat>`, `<token>`), không dùng giá trị thật kể cả đã thu hồi.

## 6. Tài liệu

- `docs/` giữ sáu tài liệu chuẩn (index, system-architecture, codebase-summary, deployment-guide, project-overview-pdr, code-standards) và các tài liệu tham chiếu theo mảng. Cập nhật khi hành vi người dùng thấy, lệnh, cấu trúc, hay hợp đồng API đổi; không ghi lại thay đổi nội bộ thuần tuý.
- Đầu mỗi tài liệu chuẩn: front matter `layout: default` + `title`, dòng **Phiên bản** · **Cập nhật**. Cuối: `## Câu hỏi mở`.
- Sơ đồ: spec `.json` là nguồn; `.html` và `.svg` là sản phẩm sinh ra, commit cả ba. Nhúng SVG trong markdown, link HTML cho bản động. Không commit `*.visual-check.*`.
- Kiểm tra link và số liệu trước khi commit ([deployment-guide.md §10](deployment-guide.md#10-kiểm-tra-bộ-doc)).

## Câu hỏi mở

- Chưa có pre-commit hook; ruff và typecheck hiện dựa vào CI và kỷ luật cá nhân.
