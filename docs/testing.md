# Kiểm thử

**Phiên bản**: 0.6.0 · **Cập nhật**: 2026-09-26

Ba tầng, một quy tắc: **mỗi tính năng ra kèm một test ở tầng thấp nhất có thể thấy nó.**
Bản thân các tệp test là bản kiểm kê; trang này chỉ nói mỗi tầng dùng để làm gì và
chạy ra sao. Số lượng và tên tệp không giữ ở đây — chạy lệnh.

| Tầng | Chạy bằng | Thấy được gì |
|---|---|---|
| pytest (`tests/`) | `uv run pytest -q` | vòng lặp, tool, store, provider, profile, scheduler, kênh, HTTP API và các stream SSE của nó — mọi thứ server làm, với model thay bằng `MY_AGENT_ROUTES=fake:echo` |
| vitest (`web/`) | `cd web && npm test` | parser, reducer, API client, từng component, và cả App chạy trên một fake server trong bộ nhớ |
| Playwright (`web/e2e/`) | `cd web && npm run e2e` | trình duyệt thật trên Vite dev server thật, `/api` do một mock trong test trả lời; dùng cho các luồng chỉ hỏng trong trình duyệt (SSE reconnect, layout ở bề rộng điện thoại, bàn phím) |

Ưu tiên tầng thấp nhất: một quy tắc của vòng lặp thuộc về pytest, một reducer thuộc về vitest, và
Playwright chỉ cho những gì chỉ DOM mới cho thấy. Hành vi vắt qua nhiều tầng (một duyệt
tạm dừng vòng lặp *và* thanh hiện ra) có một test ở mỗi bên ranh giới.

## Test bảo vệ

Vài test bảo vệ repo chứ không phải một tính năng:

- **ngân sách kích thước tệp**: không tệp nguồn nào quá 200 dòng, để module đọc gọn trong một màn hình;
- **bundle** trong `my_agent_crew/server/static` có mặt và được phục vụ ở `/`, với 404 của `/api/*`
  vẫn là JSON;
- **khởi động chỉ nạp thứ cần**: một tiến trình con import server rồi kiểm tra `pypdf` và
  `pypdfium2` chưa được nạp — chúng chỉ nạp khi có PDF cần đọc;
- **chi phí ngoài model** có test riêng: store mở ở chế độ WAL và có index cho các truy vấn
  nóng, hub không ghi và không phát từng token, một watcher ngừng đọc bị cắt, trang wiki
  chỉ parse lại khi tệp đổi, `/api/stats` không tính lại giữa hai lần ghi, tài sản có hash
  được nén gzip và cache vĩnh viễn còn luồng SSE không bị nén;
- CI dựng lại bundle và fail khi `git diff --exit-code`, nên thay đổi web không bao giờ
  được commit mà thiếu bundle của nó.

## Chạy các cổng

`./scripts/gates.sh` chạy mọi cổng CI theo thứ tự và dừng ở cổng đỏ đầu tiên; xem
[code-standards.md](code-standards.md#4-cổng-phải-chạy-trước-khi-commit). Danh sách cổng
là `.github/workflows/ci.yml`.

## Benchmark model trên vòng lặp thật

`scripts/llm_bench.py` đo các model ứng viên ngay trên vòng lặp agent, tách khỏi crew đang
chạy: mỗi model một home tạm dưới `--out`, một server riêng trên `--port` (mặc định 8797,
không bao giờ là cổng live), không có token Telegram, không có tuyến live; chỉ
`OPENROUTER_API_KEY` được kế thừa. Hai bộ việc, chọn bằng `--tasks short`, `--tasks multi`
hoặc liệt kê id (mặc định chạy cả hai):

- `scripts/llm_bench_tasks.py`, bộ ngắn: trả lời suông, ghi rồi đọc tệp, lệnh shell, giao
  việc cho agent `helper`, tóm tắt tài liệu.
- `scripts/llm_bench_tasks_multi.py`, bộ chuỗi: `pipeline` (tính, ghi, đọc lại), `revise`
  (đọc, tạo bản sửa, grep kiểm tra, trả lời từ nguồn), `shell_chain` (ba lệnh shell nối
  nhau), `delegate_write` (helper làm nhiều bước rồi master đọc lại), `delegate_twice` (hai
  lần giao việc nối tiếp), `delegate_fanout` (giao cho `helper` và `auditor` cùng lúc).

Mỗi việc được chấm đúng/sai (việc giao việc còn phải để lại đủ số run con) và đo thời gian
tường, số lần gọi model, thời gian tới token đầu (`first_token_ms` của bước model), phần
prompt được cache và chi phí, đọc từ `/api/activity/runs`. Kết quả ghi ra `results.json` và
`results.md` sau mỗi model:

```bash
uv run python scripts/llm_bench.py --models deepseek/deepseek-v4-flash,qwen/qwen3.7-flash --out /tmp/llm-bench
uv run python scripts/llm_bench.py --models deepseek/deepseek-v4-flash --tasks multi --out /tmp/llm-bench
uv run python scripts/llm_bench.py --models deepseek/deepseek-v4-flash@deepinfra --out /tmp/llm-bench
```

Dạng `model@provider` ghim một provider OpenRouter (`openrouter_providers`, không dự phòng) trong
home tạm, để so cùng một model qua các bên khác nhau.

Một lượt hỏi người dùng (`ask_user`) tính là hỏng — bench không có ai trả lời; yêu cầu duyệt
tool thì bench tự duyệt và tính vào thời gian lượt. Cổng bận thì script từ chối chạy thay vì
giết chủ cổng.

## Smoke trực tiếp (thủ công)

`MY_AGENT_ROUTES=fake:echo` trên một `MY_AGENT_HOME` tạm, rồi qua UI hoặc curl:
chat → `/tool workspace_list {"path":"."}` → `/tool workspace_write {...}` → duyệt → tệp tồn tại
trong `MY_AGENT_HOME/workspace`. Với profile agent có lịch: `POST /api/jobs/<agent>/<schedule>/run`
phải tạo ra một run trên `/api/activity/runs` và một thẻ trong rail. Với ít nhất một agent
khác đã cài: `POST /api/inbound {"text": "Nhờ kongming …"}` (với `fake:echo`, viết thẳng
`/tool delegate {"agent": "kongming", "task": "…"}` vì provider giả không tự chọn tool) phải trả
lời bằng tóm tắt của master và để lại một run con có `source` là `delegate:<conversation id>` trên
`/api/activity/runs`. Đây là bước kiểm tra cần lặp lại trước khi gắn tag phát hành. Duyệt tool
qua API: id nằm trong sự kiện SSE `approval_required` của luồng tin nhắn, vì `GET /api/approvals`
chỉ liệt kê các yêu cầu đã được quyết.
