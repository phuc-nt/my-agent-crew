---
layout: default
title: Quy ước code
---

# Quy ước code

**Phiên bản**: 0.6.0 · **Cập nhật**: 2026-09-25

## 1. Python

- Python 3.12+, `uv` quản lý môi trường. `uv sync` rồi `uv run …`.
- `ruff` với `line-length = 100`, rule `E, F, I, UP, B`. Trong lúc làm: `uv run ruff check --fix . && uv run ruff format .`. Trước khi commit thì chạy đủ bộ cổng ở [§4](#4-cổng-phải-chạy-trước-khi-commit).
- **Ngôn ngữ: tiếng Anh ở mọi nơi, trừ `docs/`.** Định danh (module, hàm, biến, key YAML, cột DB, tên event, id agent), comment, docstring, thông báo script, README, CHANGELOG, commit message đều tiếng Anh. Tiếng Việt chỉ ở hai chỗ: chuỗi hiển thị cho người dùng (`texts.py` / `texts_*.py`, `web/src/i18n/vi.ts`, prompt và persona của agent) và bộ tài liệu `docs/` — viết cho đội maintain người Việt. Không viết chuỗi hiển thị trực tiếp trong code logic.
- Mỗi tệp một mối quan tâm; tệp trên ~200 dòng thì cân nhắc tách theo ranh giới có sẵn (`routes_*.py`, `telegram_*.py`, `texts_*.py` là ví dụ).
- Docstring đầu module nói *vì sao* module tồn tại, không lặp lại tên hàm.
- Không đưa id plan, số phase, nhãn audit vào comment, tên test, hay commit message.

## 2. Web

- TypeScript strict, React 19, không thư viện state ngoài reducer trong `state/`.
- `npm run typecheck && npm test` trong lúc làm; `npm run bundle` khi đổi web để cập nhật `my_agent_crew/server/static` (CI kiểm diff). Trước khi commit: đủ bộ cổng ở [§4](#4-cổng-phải-chạy-trước-khi-commit).
- Chuỗi hiển thị trong `i18n/vi.ts`. Tên component kebab-case, một component một tệp.

## 3. Test

- Mỗi tính năng có test cùng lúc với code; bộ test phải đi theo code, không để sau.
- Backend: pytest + provider giả (`fake:echo`) và home tạm (`tmp_path`). Không đụng `~/.my-agent-crew` thật.
- Web: vitest cho component/hook; Playwright cho luồng người dùng với `e2e/mock-api.ts` mock toàn bộ `/api` bằng regex neo gốc (glob `**/api/**` nuốt cả module nguồn Vite).
- Neo test vào failure mode (điều gì sai thì test đỏ), không neo vào ngưỡng số tuỳ ý.
- Xem [testing.md](testing.md) cho lệnh và bố cục.

## 4. Cổng phải chạy trước khi commit

Tám cổng dưới đây **là chính xác những gì CI chạy**, theo đúng thứ tự trong
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml). Chạy đủ cả tám ở máy trước khi đẩy;
cổng nào bỏ qua thì CI sẽ là nơi phát hiện, và đó là lúc đắt nhất.

Một lệnh chạy hết, dừng ở cổng đỏ đầu tiên và gọi tên nó:

```bash
./scripts/gates.sh
```

Danh sách dưới đây là để biết mỗi cổng làm gì và vì sao nó tồn tại; muốn chạy thì dùng script,
vì danh sách nằm trong tệp thì không bỏ sót được, còn nằm trong đầu thì có.

```bash
uv sync
uv run ruff check .
uv run ruff format --check .     # ← dễ quên nhất: `ruff check` xanh không có nghĩa cổng này xanh
uv run pytest -q

cd web
npm ci                            # hoặc npm install khi đang phát triển
npm run typecheck
npm test
npx playwright install --with-deps chromium   # lần đầu thôi
npm run e2e
npm run bundle
git diff --exit-code --stat -- ../my_agent_crew/server/static
```

Hai cổng hay bị bỏ sót và vì sao:

| Cổng | Vì sao hay quên | Dấu hiệu |
|---|---|---|
| `ruff format --check .` | khác hẳn `ruff check`; một tệp lint sạch vẫn có thể sai định dạng | in `unformatted: File would be reformatted` kèm diff (**không** phải `Would reformat:`) |
| `git diff` trên `server/static` | bundle được commit, nên quên `npm run bundle` là CI đỏ dù code đúng | diff khác rỗng ở `my_agent_crew/server/static` |

Sửa định dạng bằng `uv run ruff format .` rồi **chạy lại `pytest`** — định dạng có đụng vào code.

## 5. Commit

- Conventional commits: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`. Viết tiếng Anh, ngắn gọn, nói việc gì và vì sao.
- Một commit một việc. Không commit `node_modules/`, tệp env, DB, log.
- Không thêm dòng attribution.

## 6. Bí mật và dữ liệu cá nhân

- Token, API key, chat id, dữ liệu người dùng (persona thật, `MEMORY.md`, facts, workspace) sống trong `~/.my-agent-crew/` — **ngoài repo**. Repo chỉ chứa mẫu (`agents/templates/`) và tài liệu.
- Cấu hình chỉ ghi tên biến môi trường (`token_env`), không ghi giá trị.
- Log đi qua redact: lỗi API Telegram bị che token trước khi ném, và một filter trên logger HTTP che mọi token tiến trình từng dùng. Khi thêm client HTTP mới có secret, thêm redact tương ứng và một test khẳng định secret không xuất hiện trong log.
- Tài liệu và ví dụ dùng placeholder (`<chat>`, `<token>`), không dùng giá trị thật kể cả đã thu hồi.

## 7. Tài liệu

- `docs/` giữ sáu tài liệu chuẩn (index, system-architecture, codebase-summary, deployment-guide, project-overview-pdr, code-standards) và các tài liệu tham chiếu theo mảng. Cập nhật khi hành vi người dùng thấy, lệnh, cấu trúc, hay hợp đồng API đổi; không ghi lại thay đổi nội bộ thuần tuý.
- **Code là nguồn sự thật; tài liệu chỉ mô tả khái niệm, luồng và hợp đồng người dùng thấy** (khoá YAML, tên tool, lệnh CLI, biến môi trường, endpoint, tên tab). Không ghi tên tệp, hàm, hằng, component hay tệp test, không ghi số test hay số dòng, không ghi thời gian chạy: những thứ đó đổi theo mỗi commit và chỉ có `ls`/`grep` mới nói đúng. Tên gói (`agent/`, `tools/`, `channels/`…) là mức chi tiết tối đa. Viết cho người mới vào và người quyết định, không phải để thay việc đọc code.
- Đầu mỗi tài liệu chuẩn: front matter `layout: default` + `title`, dòng **Phiên bản** · **Cập nhật**. Cuối: `## Câu hỏi mở`.
- Sơ đồ: spec `.json` là nguồn; `.html` và `.svg` là sản phẩm sinh ra, commit cả ba. Nhúng SVG trong markdown, link HTML cho bản động. Không commit `*.visual-check.*`.
- Kiểm tra link trước khi commit ([deployment-guide.md §10](deployment-guide.md#10-kiểm-tra-bộ-doc)).

## Câu hỏi mở

- Chưa có pre-commit hook: `scripts/gates.sh` vẫn phải tự gõ. Gắn vào hook thì mọi commit nhỏ cũng chờ cả bộ cổng, nên hiện để người chạy tự quyết lúc nào.
