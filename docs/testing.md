# Kiểm thử

**Phiên bản**: 0.8.0 · **Cập nhật**: 2026-09-26

Ba tầng, một quy tắc: **mỗi tính năng ra kèm một test ở tầng thấp nhất có thể thấy nó.**
Bản thân các tệp test là bản kiểm kê; trang này chỉ nói mỗi tầng dùng để làm gì và
chạy ra sao. Số lượng và tên tệp không giữ ở đây — chạy lệnh.

| Tầng | Chạy bằng | Thấy được gì |
|---|---|---|
| pytest (`tests/`) | `uv run pytest -q` | vòng lặp, tool, store, provider, profile, scheduler, kênh, HTTP API và các stream SSE của nó — mọi thứ server làm, với model thay bằng `MY_AGENT_ROUTES=fake:echo` |
| vitest (`web/`) | `cd web && npm test` | parser, reducer, API client, từng component, và cả App chạy trên một fake server trong bộ nhớ |
| Playwright (`web/e2e/`) | `cd web && npm run e2e` | trình duyệt thật trên Vite dev server thật, `/api` do một mock trong test trả lời; dùng cho các luồng chỉ hỏng trong trình duyệt (SSE reconnect, layout ở bề rộng điện thoại, drawer điện thoại là modal, bàn phím) |

Ưu tiên tầng thấp nhất: một quy tắc của vòng lặp thuộc về pytest, một reducer thuộc về vitest, và
Playwright chỉ cho những gì chỉ DOM mới cho thấy. Hành vi vắt qua nhiều tầng (một duyệt
tạm dừng vòng lặp *và* thanh hiện ra; nâng trần chi phí gỡ `over_budget` ở server *và* mở lại
ô soạn; lưu lịch trả về lý do cần khởi động lại bằng một câu trọn vẹn ở server *và* trình sửa
agent hiện nguyên câu đó) có một test ở mỗi bên ranh giới. Fake server của vitest và mock
của Playwright tự tính
lại những trường server suy ra (như `over_budget` từ trần), để test không tin vào một con số
cũ. Route của Playwright trả cả thân một lần, nên một stream còn đang chạy khi bấm Dừng được
dựng ngay trong trang bằng `addInitScript` (test Dừng trong `chat-smoke.spec.ts`); còn run do
kênh khác chạy và nút Thử lại của luồng trực tiếp có test App riêng trong
`app-thread-refresh.test.tsx`; những lần tải lại chạy đua với lượt của chính tab này (một tin
gửi khi lần tải còn trên đường; một run của kênh khác đã chạy từ trước khi gửi, hay được một
quyết định ở nơi khác tiếp tục trong lúc quyết định ở đây nhận 409; một lần tải hay một 409 của
cuộc trò chuyện vừa rời trả về khi cuộc khác đã mở) nằm ở
`app-thread-refresh-races.test.tsx`, nơi mỗi fetch lấy
câu trả lời lúc gửi nhưng chỉ trao ra khi test mở "cửa" của nó; các lần đọc danh sách run
chồng lên nhau (câu trả lời đọc trước khi run kết thúc lại về sau cùng) được giữ cửa theo cùng
cách trong `hooks/use-activity.test.ts`. Việc dò bản mới so entry có hash của trang với entry mà `/`
đang phục vụ, nên nó im trên Vite dev server; `version-refresh.spec.ts` và test App của nó
gắn một entry giả vào trang để trang trông như bản build. Bố cục những gì chat nói về trạng
thái của nó ở bề rộng điện thoại (dòng trạng thái giữ một chiều cao khi nút Thử lại hiện ra)
nằm ở `chat-state-phone.spec.ts`; luồng trực tiếp được một route giữ lại để bắt được cả lúc
đang kết nối lẫn lúc đã mất.

Fake server của vitest giữ yêu cầu duyệt đang mở như server thật: một lượt dừng ở
`approval_required` để lại yêu cầu trên cuộc trò chuyện, và quyết định cho một yêu cầu đã đóng
nhận 409. Nhờ vậy việc duyệt ngay trong Quản lý › Duyệt được test ở vitest cả khi tab khác hay
lượt quét hết hạn giành trước (báo "đã được xử lý", không báo bận), cả khi đồng hồ đếm về 0
(nút khoá, danh sách tải lại), còn Playwright chỉ giữ phần chỉ trình duyệt thấy: bấm Cho phép
trên bề rộng 390px mà trang không cuộn ngang, và trên màn điện thoại thấp 390×664 mở đầy đủ một
tệp 120 dòng mà các nút quyết định vẫn trên màn hình, trang không cuộn. Lịch sử duyệt bên dưới
được đọc lại mỗi khi một yêu cầu có thể vừa khép: run của nó chạy tiếp, run kết thúc (kể cả khi
chạy tiếp và kết thúc đến trong cùng một lần cập nhật), một run trang chưa từng thấy chờ đến nơi
đã xong, hay hàng vừa quyết định thấy run dừng chờ yêu cầu kế tiếp; mỗi đường có một ca trong
`app-attention.test.tsx`.

## Test bảo vệ

Vài test bảo vệ repo chứ không phải một tính năng:

- **ngân sách kích thước tệp**: không tệp nguồn nào quá 200 dòng, để module đọc gọn trong một màn hình;
- **bundle** trong `my_agent_crew/server/static` có mặt và được phục vụ ở `/`, với 404 của `/api/*`
  vẫn là JSON; mọi icon và manifest mà trang và manifest trỏ tới đều có trong bundle và được
  phục vụ đúng content-type;
- **khởi động chỉ nạp thứ cần**: một tiến trình con import server rồi kiểm tra `pypdf` và
  `pypdfium2` chưa được nạp — chúng chỉ nạp khi có PDF cần đọc;
- **chi phí ngoài model** có test riêng: store mở ở chế độ WAL và có index cho các truy vấn
  nóng, hub không ghi và không phát từng token, một watcher ngừng đọc bị cắt, trang wiki
  chỉ parse lại khi tệp đổi, `/api/stats` không tính lại giữa hai lần ghi, tài sản có hash
  được nén gzip và cache vĩnh viễn còn luồng SSE không bị nén;
- **đọc được**: `web/e2e/legibility-smoke.spec.ts` đo trong trình duyệt thật, trên style đã
  tính, độ tương phản WCAG (≥4.5:1) của chữ trên nền tô và nền trũng ở cả sáng lẫn tối, kể cả
  khi hover nút chính và nút "Xem đầy đủ" cỡ nhỏ trên nền vàng của thanh duyệt; yêu cầu đặt
  trong một dòng của thẻ "Cần bạn" mang màu chữ thường chứ không màu vàng của thẻ; vòng focus
  của checkbox, công tắc và ô tìm kiếm; bố cục của notice ở chat và ở màn quản lý; cỡ chữ ô soạn trí nhớ ≥16px để iPhone không phóng to trang; và khối tham số
  đầy đủ của một tool call xuống dòng trong bề rộng 390px thay vì cuộn ngang. jsdom không
  tính cascade, nên các thứ này chỉ đo được ở đây;
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
lời bằng chính lời của agent con (lượt chỉ có một lần giao việc thì không kể lại) và để lại một
run con có `source` là `delegate:<conversation id>` trên `/api/activity/runs`. Đây là bước kiểm tra cần lặp lại trước khi gắn tag phát hành. Duyệt tool
qua API: id nằm trong sự kiện SSE `approval_required` của luồng tin nhắn, vì `GET /api/approvals`
chỉ liệt kê các yêu cầu đã được quyết.
