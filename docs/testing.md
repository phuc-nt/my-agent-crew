# Kiểm thử

**Phiên bản**: 0.10.0 · **Cập nhật**: 2026-09-30

Ba tầng, một quy tắc: **mỗi tính năng ra kèm một test ở tầng thấp nhất có thể thấy nó.**
Bản thân các tệp test là bản kiểm kê đầy đủ; trang này nói mỗi tầng dùng để làm gì, chạy ra
sao, và — ở mục cuối trang — tính năng nào được test ở đâu, để người sửa một tính năng biết
test nào phải đổi theo. Số lượng test không giữ ở đây — chạy lệnh.

| Tầng | Chạy bằng | Thấy được gì |
|---|---|---|
| pytest (`tests/`) | `uv run pytest -q` | vòng lặp, tool, store, provider, profile, scheduler, kênh, HTTP API và các stream SSE của nó — mọi thứ server làm, với model thay bằng `MY_AGENT_ROUTES=fake:echo` (hoặc `fake:slow`: cùng model giả, nhưng chờ giữa hai mảnh để nhìn được stream tới dần) |
| vitest (`web/`) | `cd web && npm test` | parser, reducer, API client, từng component, và cả App chạy trên một fake server trong bộ nhớ. Worker tắt web storage riêng của Node, nên máy Node 26 và CI Node 24 cùng dùng storage của jsdom, và mỗi test bắt đầu với storage rỗng (`test-environment.test.ts`) |
| Playwright (`web/e2e/`) | `cd web && npm run e2e` | trình duyệt thật trên Vite dev server thật, `/api` do một mock trong test trả lời; dùng cho các luồng chỉ hỏng trong trình duyệt (SSE reconnect, layout ở bề rộng điện thoại, drawer điện thoại là modal, bàn phím). Proxy `/api` của dev server khi chạy e2e trỏ vào một cổng không ai nghe (`API_ORIGIN`), nên spec nào quên mock sẽ hỏng chứ không gọi vào đội đang chạy trên máy (`dev-proxy.spec.ts`) |

Ưu tiên tầng thấp nhất: một quy tắc của vòng lặp thuộc về pytest, một reducer thuộc về vitest, và
Playwright chỉ cho những gì chỉ DOM mới cho thấy. Hành vi vắt qua nhiều tầng (một duyệt
tạm dừng vòng lặp *và* thanh hiện ra; nâng trần chi phí gỡ `over_budget` ở server *và* mở lại
ô soạn; lưu lịch trả về lý do cần khởi động lại bằng một câu trọn vẹn ở server *và* trình sửa
agent hiện nguyên câu đó, kể cả khi xoá lịch; câu ấy chỉ viết một lần ở mỗi bên, và
`tests/test_api_agents_edit.py::test_the_web_fakes_answer_a_schedule_edit_with_the_servers_own_reason`
giữ bản của fake khớp bản của server) có một test ở mỗi bên ranh giới. Fake server của vitest và mock
của Playwright tự tính
lại những trường server suy ra (như `over_budget` từ trần), để test không tin vào một con số
cũ. Route của Playwright trả cả thân một lần, nên một stream còn đang chạy khi bấm Dừng được
dựng ngay trong trang bằng `addInitScript` (test Dừng trong `chat-smoke.spec.ts`), và luồng
hoạt động cũng vậy khi một số đếm phải đổi sau khi trang đã mở (`manage-row-phone.spec.ts`, spec
này còn chờ font tải xong rồi mới mở mục, vì font đến muộn làm mọi pill rộng ra); còn run do
kênh khác chạy và nút Thử lại của luồng trực tiếp có test App riêng trong
`app-thread-refresh.test.tsx`; những lần tải lại chạy đua với lượt của chính tab này (một tin
gửi khi lần tải còn trên đường; một run của kênh khác đã chạy từ trước khi gửi, bắt đầu sau run
của tab, hay được một quyết định ở nơi khác tiếp tục trong lúc quyết định ở đây nhận 409; hai
lượt liền nhau của tab, và run mà quyết định ở đây tiếp tục, vẫn là của tab nên không tải thêm
lần nào; một lần tải, một lần tải hỏng (500 hay mất mạng) hay một 409 của cuộc trò chuyện vừa
rời trả về khi cuộc khác đã mở; lời báo "đã được xử lý" còn nguyên qua lần tải do run được tiếp
tục hay luồng kết nối lại, và chỉ mất khi lần tải mang về một yêu cầu mới hay khi mở cuộc khác)
nằm ở
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
(nút khoá, danh sách tải lại, rồi yêu cầu được đọc lại cho tới khi lượt quét — có thể trễ vài
phút sau hạn — khép nó), còn Playwright chỉ giữ phần chỉ trình duyệt thấy: bấm Cho phép
trên bề rộng 390px mà trang không cuộn ngang, và trên màn điện thoại thấp 390×664 mở đầy đủ một
tệp 120 dòng mà các nút quyết định vẫn trên màn hình, trang không cuộn. Lịch sử duyệt bên dưới
được đọc lại mỗi khi một yêu cầu có thể vừa khép: run của nó chạy tiếp, run kết thúc (kể cả khi
chạy tiếp và kết thúc đến trong cùng một lần cập nhật), run của nó chạy tiếp đúng lúc run của một
cuộc khác bắt đầu chờ (trong một snapshot khi luồng kết nối lại hay hai run đến cùng lúc: số run
chờ và số run xong đều giữ nguyên, chỉ run nào đang chờ là đổi), một run trang chưa từng thấy chờ
đến nơi đã xong, hay hàng vừa quyết định thấy run dừng chờ yêu cầu kế tiếp; mỗi đường có một ca
trong `app-attention.test.tsx`.

Run dừng chờ duyệt sống qua lần khởi động lại: `tests/test_activity_restart.py` dựng một
activity hub thứ hai trên cùng store như một tiến trình mới sẽ dựng, rồi kiểm tra quyết định
đến sau đó chạy tiếp chính run đã dừng (kể cả sau hai lần khởi động lại), còn run chờ duyệt
không còn gì để chờ (yêu cầu đã được quyết khi không tiến trình nào giữ run, run không thuộc
cuộc nào, một lần dừng cũ hơn của cùng cuộc, hay yêu cầu đang chờ thuộc cuộc khác) bị đóng là
`interrupted`; một step chạy tiếp sau khi máy khởi động lại không bao giờ báo thời lượng âm. Xoá
một cuộc chỉ đóng run chờ duyệt của chính cuộc đó, không đụng run đang chờ ở cuộc khác hay lượt
còn đang chạy. Xoá cuộc đang chờ duyệt cũng đánh thức những ai đang chờ nó:
`tests/test_memory_conversation_title.py` kiểm tra không trả tiền cho model đặt tên một cuộc đã
bị xoá, hay đã được người dùng tự đặt tên, trong lúc chờ; `tests/test_tools_delegate.py` kiểm
tra agent cha đọc được lời báo cuộc con đã bị xoá thay vì một `KeyError` trần.

## Test bảo vệ

Vài test bảo vệ repo chứ không phải một tính năng:

- **ngân sách kích thước tệp**: không tệp nguồn nào quá 200 dòng, của gói lẫn của `scripts/`, để
  module đọc gọn trong một màn hình; thư mục nào được kiểm cũng phải còn tệp nguồn, để dời thư
  mục đi không làm test đạt trên rỗng;
- **bundle** trong `my_agent_crew/server/static` có mặt và được phục vụ ở `/`, với 404 của `/api/*`
  vẫn là JSON; mọi icon và manifest mà trang và manifest trỏ tới đều có trong bundle và được
  phục vụ đúng content-type;
- **không trang nào của site khác nhúng được app**: trang, API, asset có băm, 404 và cả 403 của hàng
  rào cục bộ đều mang `Content-Security-Policy: frame-ancestors 'self'`, thành một header riêng đứng
  sau policy mà route tự đặt (raw, tệp của agent và trang chạy của canvas giữ nguyên policy sandbox
  của chúng); luồng SSE vẫn tới client lúc còn mở (`tests/test_security_headers.py`,
  `tests/test_artifact_render.py`);
- **trang 500 của một lỗi không ai bắt cũng không cho site khác nhúng**: một route ném
  `RuntimeError` (đặt trước route bắt mọi địa chỉ để phục vụ trang) trả 500 "Internal Server
  Error" vẫn mang đúng một header `Content-Security-Policy: frame-ancestors 'self'`. Header được
  bọc quanh cả chồng middleware bằng `SecuredApp` chứ không thêm bằng `add_middleware`, vì
  Starlette đặt bộ xử lý lỗi máy chủ ở ngoài mọi middleware đã thêm, nên trang 500 đi ra không có
  header (`tests/test_security_headers.py`);
- **API từ chối request mà trình duyệt báo đến từ site hay cổng khác**: `Sec-Fetch-Site` là
  `cross-site`, `same-site` hay một giá trị lạ thì 403 `CROSS_SITE_REQUEST` ở mọi method và cả khi
  đường dẫn viết bằng `%61` hay `%2F`; `same-origin`, `none` và không có header (curl, eval,
  Telegram) thì qua; trang, asset và đường dẫn chỉ bắt đầu giống `/api` không bị chặn, vì link từ
  nơi khác vào app phải mở được; lý do này không bị ghi log như một tên host cần cho phép, còn tên
  host lạ vẫn nhận lời khuyên `MY_AGENT_ALLOWED_HOSTS` dù request cũng là cross-site; ngoại lệ duy
  nhất là đúng địa chỉ `/api/artifacts/{id}/render`, vì trang chạy của canvas có origin ẩn danh nên
  tải lại nó là `cross-site`: `/render/`, `/render` kèm xuống dòng (`%0A`), `/render/x`,
  `a%2Fb/render`, `raw`, `versions`, danh sách và canvas không đi theo ngoại lệ ấy, Origin hay host
  lạ vẫn bị chặn, và địa chỉ đó chỉ nhận `GET` nên cho qua không đổi được gì
  (`tests/test_local_guard.py`);
- **khởi động chỉ nạp thứ cần**: một tiến trình con import server rồi kiểm tra `pypdf` và
  `pypdfium2` chưa được nạp — chúng chỉ nạp khi có PDF cần đọc;
- **chi phí ngoài model** có test riêng: store mở ở chế độ WAL và có index cho các truy vấn
  nóng, hub không ghi và không phát từng token, một watcher ngừng đọc bị cắt, trang wiki
  chỉ parse lại khi tệp đổi, `/api/stats` không tính lại giữa hai lần ghi và mang sẵn cache
  theo agent (trang Chi phí không tải lại 500 run kèm các bước của chúng chỉ để cộng hai con
  số), tài sản có hash được nén gzip và cache vĩnh viễn còn luồng SSE không bị nén;
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

Dev server của Playwright nghe ở cổng 4173. Khi hai checkout cùng chạy e2e,
`E2E_PORT=<cổng> npm run e2e` dời nó sang cổng khác: trên cùng một cổng, lần chạy sau dùng lại
server của lần trước và lặng lẽ test mã nguồn của checkout kia. Vitest (qua `TZ`) và Playwright
(qua `timezoneId`) đều chạy ở múi giờ Asia/Ho_Chi_Minh, nên ranh giới ngày ("Hôm nay",
"Hôm qua", ghi chú hôm nay) rơi cùng một chỗ trên máy và trên CI, vốn chạy UTC; test về ngày cứ
viết theo giờ Việt Nam, không tự đặt múi giờ.

## Benchmark model trên vòng lặp thật

`scripts/llm_bench.py` đo các model ứng viên ngay trên vòng lặp agent, tách khỏi crew đang
chạy: mỗi model một home tạm dưới `--out`, một server riêng trên `--port` (mặc định 8797,
không bao giờ là cổng live), không có token Telegram, không có tuyến live. Từ môi trường của
người chạy, server chỉ nhận những biến một chương trình cần để chạy (`PATH`, `HOME`, `LANG` và
các `LC_*`, `TERM`, `TMPDIR`, `USER`, `LOGNAME`, `SHELL`, `TZ`) cùng `OPENROUTER_API_KEY`; hook
và lệnh server chạy cũng chỉ thấy chừng ấy. Hai bộ việc, chọn bằng `--tasks short`,
`--tasks multi` hoặc liệt kê id (mặc định chạy cả hai):

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

## Kiểm thử hành vi bằng model thật

Bench ở trên so các model với nhau; kiểm thử hành vi hỏi câu khác: **agent của mình** — đúng
persona, đúng bộ tool, đúng model mà crew thật đang dùng — có làm điều nó phải làm và tránh điều
nó không được làm không. Đó là chỗ duy nhất bắt được kiểu hỏng "sửa persona xong, agent quên một
luật cũ" hay "thêm tool xong, agent gọi nó bừa"; model giả không thấy được những thứ đó.
`scripts/run_evals.py` chơi các case viết tay trên một **bản sao** của home và chấm cái agent
*cố làm*: gọi tool nào, xin duyệt việc gì, nói gì. Nó không chấm một lệnh in ra gì, vì lệnh cần
duyệt bị từ chối theo mặc định.

Chạy tay, không nằm trong CI: tốn tiền thật, và một model không trả lời hai lần giống nhau. Chạy
trước mỗi lần phát hành và sau mỗi lần đổi persona, prompt hay bộ tool của một agent:

```bash
export OPENROUTER_API_KEY=...      # bí mật duy nhất server eval được nhận
uv run python scripts/run_evals.py --runs 3 --max-usd 0.5
uv run python scripts/run_evals.py --only <id>,<id> --runs 1
uv run python scripts/run_evals.py --dry-run
```

- **Case** nằm trong `<home>/evals/*.yaml`, cạnh các agent nó thử (`--cases` chỉ một tệp hay
  thư mục khác, `--home` chọn home khác); `scripts/eval_example_cases.yaml` là mẫu có chú thích.
  Một case có `id`, `agent`, `messages` (mỗi tin một lượt), `approvals` (`deny` mặc định, hoặc
  `approve`), `answers` (trả lời lần lượt cho câu hỏi của agent) và `expect`: `calls_tool`,
  `not_calls_tool`, `asks_approval` (mỗi mục là `{name, args_regex?, agent?, turn?}`; regex tìm
  trong tham số viết thành JSON, lượt đếm từ 1 theo các tin case đã gửi, nên ghi chú server tự
  viết vào vai người, như của loop guard, không mở lượt mới), `max_calls`, `reply_contains`,
  `reply_not_contains` (không phân biệt hoa thường và dấu), `delegates_to` (`{agent, outcome?}`;
  `outcome` là một trong năm giá trị của dòng `outcome=` trong kết quả giao việc) và `max_cost_usd`.
  Khoá lạ, regex hỏng hay id trùng bị từ chối *trước* khi tốn đồng nào. Việc một agent con làm
  tính vào lượt của cha đã giao nó. Cuộc trò chuyện không giữ đủ các tin đã gửi thì lần chơi
  hỏng, thay vì đếm lệch lượt.
- **Bước canvas** nằm giữa các tin trong `messages`: đó là việc người làm trên panel giữa hai
  lượt, đi qua đúng các route REST mà web dùng, với tư cách người. `create_canvas: {title,
  content, kind?}` tạo canvas trong cuộc trò chuyện và mở nó (`kind` là `markdown`, mặc định, hay
  `code`). `edit_canvas: {old, new}` thay chỗ duy nhất có `old` trong canvas đang mở rồi lưu trên
  đúng bản vừa đọc, như editor. `select_canvas: <đoạn>` chọn chỗ duy nhất có đoạn ấy, đếm dòng
  như panel. Chưa mở canvas nào thì bước làm trên canvas mới đổi gần nhất của cuộc trò chuyện. Từ
  lúc có canvas mở, mọi tin gửi đi mang canvas đó như tin từ web; vùng chọn chỉ đi cùng tin ngay
  sau, nên một bước chọn phải có tin theo sau. Một tin có `: ` phải để trong ngoặc kép, không thì
  YAML đọc nó thành một bước. Bước không làm được (cuộc trò chuyện chưa có canvas, `old` hay đoạn
  chọn không có đúng một lần, server từ chối lần lưu hay trả lời ở dạng panel không đọc được)
  làm lần chơi hỏng và không gửi tin sau; mất server thì dừng cả cuộc eval như một lượt.
  `edit_canvas` có `new` trùng `old` bị từ chối, vì lần sửa ấy không đổi gì.
- **Bước canvas phải tới được agent** (`eval_note.py`). Agent chỉ biết một bước canvas qua ghi
  chú canvas server lưu cùng tin kế của người. Nên tin chứa mỗi chữ case gửi phải có ghi chú
  nêu mọi canvas người đã tạo hay lưu kể từ tin trước, ở đúng bản người để lại, theo một trong
  các dạng ghi chú báo thay đổi (canvas chưa đọc, đoạn diff, đã lên bản, sửa nhiều chỗ), và
  trích đoạn tin ấy mang theo đúng như ghi chú trích; dòng nêu canvas đang mở thì không tính.
  Thiếu thì lần chơi hỏng, vì kỳ vọng của case sẽ chấm một agent chưa hề nghe về bước ấy. Case
  lưu canvas về đúng nội dung agent đã nghe trước tin kế, hay đổi nhiều canvas tới mức ghi chú
  phải dồn vào dòng đếm cuối, cũng hỏng ở đây: ghi chú không nêu riêng canvas ấy.
- **Kỳ vọng về canvas** chấm mọi canvas liên kết với cuộc trò chuyện gốc khi lần chơi xong:
  `canvas_count` (số canvas), `canvas_contains` và `canvas_not_contains` (có trong một canvas nào
  đó, hay không còn trong canvas nào; không phân biệt hoa thường và dấu) và `canvas_not_in_chat:
  true`. Kỳ vọng cuối hỏng khi các tin agent viết trong cuộc trò chuyện gốc, ở mọi lượt, lặp lại
  từ một nửa số cụm ba chữ liền nhau của một canvas (`eval_paste.py`). Canvas và từng tin được
  đọc như một dải chữ, bỏ dấu đầu dòng, số thứ tự, chữ đậm, hoa thường và dấu, nên dán nguyên
  văn, thành bảng, đổi dấu phân cách hay dồn về một dòng đều bị bắt. Không tính tiêu đề và đề
  mục canvas mở đầu bằng, vì đó là cách chat gọi tên canvas; mọi cụm lặp lại nằm gọn trong một
  dòng là trích dẫn (dòng vừa sửa chẳng hạn), không phải dán; không cụm nào nối hai tin. Dán mà
  bỏ nhãn của mọi dòng ngắn (thứ trong tuần của một kế hoạch mỗi ngày một phòng) thì còn quá ít
  cụm để bắt. Canvas là chỗ làm việc, chat là chỗ nói về nó.
- **Mỗi case chơi `--runs` lần** (mặc định 3) và đạt khi ít nhất hai phần ba số lần đạt. Số tiền
  là mức sổ cái của server tăng lên kể từ lúc bắt đầu, lời gọi bên cạnh lượt cũng tính; xoá một
  cuộc trò chuyện thì sổ cái mất các lượt của nó, nên runner cộng giá các lượt ấy trước khi xoá.
  Trước mỗi lần chơi mà đã hết `--max-usd` (mặc định 0.5) thì dừng. Có lời gọi provider không
  báo giá thì tổng chỉ là cận dưới và báo cáo nói vậy.
- **Mỗi lần chơi bắt đầu từ server như lần đầu thấy** (`eval_reset.py`). Các lần chơi dùng
  chung một server, và không có bước này thì lần sau chấm cả những gì lần trước để lại: cuộc
  trò chuyện mới mở đầu bằng tóm tắt của cuộc trước trong cùng kênh, `conversation_search` và
  `artifact_list` thấy chat và canvas cũ, `memory_save` để lại ghi chú. Nên trước mỗi lần,
  runner xoá mọi canvas rồi mọi cuộc trò chuyện, kiểm server không còn cái nào, rồi đặt lại các
  tệp bộ nhớ (những gì crew biết về người, ghi chú và wiki của từng agent cùng mục lục) như lúc
  eval bắt đầu, không bao giờ ngoài thư mục chạy và không theo symlink. Không đặt lại được thì
  lần chơi không chạy và eval dừng như mất server. Bước này không đặt lại những gì một tool cần
  duyệt đổi trong case `approve`, tệp agent con trả về workspace, lịch agent tạo hay đề xuất bộ
  nhớ chờ người: case cần những thứ đó sạch thì đừng gây ra chúng.
- **Kết quả** ghi vào `<out>/results/` (`--out`, mặc định `$TMPDIR/my-agent-crew-evals`, không
  được nằm trong repo): `results.md` nêu kỳ vọng nào hỏng ở lần chơi nào, kèm lời đáp rút gọn;
  `results.json`; `server.log`. Ghi sau mỗi lần chơi, nên cuộc chạy bị cắt vẫn để lại số của
  những lần đã xong. `transcripts/` giữ mỗi lần chơi một tệp JSON (`<thứ tự case>-<id>-<lần>.json`):
  cuộc trò chuyện gốc, các cuộc con, các canvas và các lần xin duyệt, để xem lại agent đã nói và
  làm gì sau khi bản sao đã xoá. Những tệp ấy có thể chứa mọi thứ các agent biết (bộ nhớ,
  persona, dữ liệu workspace), nên tự xoá tay khi xong, như với `--keep-home`.
- **Một lượt quá `--turn-timeout`** (300 giây, tính cả khi luồng SSE vẫn gửi keep-alive) hay một
  lỗi HTTP dừng cả cuộc eval: nó không còn biết server có sống không. Ctrl-C và SIGTERM cũng
  dừng server và xoá bản sao. Đừng đặt `--turn-timeout` lớn hơn thời gian `delegate` chờ một
  agent con (hạn duyệt cộng 300 giây, mặc định 900): khi đó lượt cha có thể xong trong lúc con
  còn chạy, và bước canvas hay tin kế tiếp đua với con. Case có giao việc hay lượt dài thì chạy
  với `--turn-timeout 900`.
- **`--dry-run`** đổi model bằng `fake:echo` trên một home tổng hợp và bộ case mẫu, chỉ để kiểm
  dây nối; chỉ một lần chơi *không kết thúc được* (lỗi, hết giờ, mất server) mới tính là hỏng,
  vì model giả không thể thoả các kỳ vọng.

Không có gì chạy trên crew thật. Home và các workspace mà agent dùng được chép vào `<out>/run`
(chỉ chủ sở hữu đọc được); một server khởi động trên bản sao ở `--port` (mặc định 8798, không
bao giờ là cổng live) với `--no-schedule` — không scheduler, không Telegram hay kênh nào — và
`HOME` trỏ vào bản sao. Cả hai biến mất khi xong; `--keep-home` giữ bản sao lại, và vì nó chứa
dữ liệu của các agent, tự xoá tay. Bản sao:

- **bỏ** `env`, `agent.sqlite3*`, `backups`, `logs`, `channels`, `run-server.zsh`, `evals`,
  `spill`, tệp offset, mọi `.env*`, thư mục git, `.venv`, `node_modules`, `__pycache__`, kit nằm
  ngoài các thư mục crew đọc, symlink (không chép cũng không theo) và những gì giữ một phiên
  đăng nhập: cookie, token, khoá riêng, hồ sơ trình duyệt. Báo cáo đếm những gì bị bỏ;
- **bỏ** `schedules`, `telegram`, `memory_consolidate` và `shell_allow_patterns` khỏi manifest
  của từng agent (`shell_allow_patterns` cũng bị bỏ khỏi `config.yaml`), và viết lại mọi đường
  dẫn cho nằm trong thư mục chạy. Đường dẫn ra ngoài home và các workspace bị từ chối trước khi
  chép gì; một workspace là hay chứa thư mục home của bạn cũng vậy;
- **giữ** cấu hình, persona, bộ nhớ, kỹ năng, workspace và cơ sở dữ liệu nằm trong workspace.
  Cơ sở dữ liệu đang được ghi lúc chép có thể hỏng nửa chừng; dữ liệu đó chỉ để đọc;
- chỉ nhận model key từ shell của người chạy: `env` của home không bao giờ được đọc hay chép,
  và từ môi trường của người chạy server chỉ nhận đúng danh sách biến của server bench. Token
  bot, khoá của dịch vụ khác, socket của ssh-agent hay thiết lập `MY_AGENT_*` dành cho server
  live, kể cả `MY_AGENT_SHELL_ALLOW_PATTERNS`, đều ở ngoài, nên hook và lệnh của bản sao cũng
  không thấy.

Mọi cuộc trò chuyện của eval không tự động (`autonomous` tắt) và bản sao không còn danh sách
cho phép lệnh shell, nên mọi `shell_run` đều hỏi trước. Danh sách cho phép mà còn sót thì một
lệnh khớp nó chạy không ai hỏi, kể cả lệnh nêu đường dẫn live, nên `build_home` từ chối một bản
sao còn danh sách ấy. Runner từ chối hoặc duyệt theo `approvals` của case; kể cả khi duyệt, một
lệnh nêu đường dẫn của home hay workspace live vẫn bị từ chối, vì lệnh ấy có thể đọc hay ghi cây
live. Câu hỏi của agent lấy câu trả lời kế tiếp trong `answers`; hết câu trả lời thì lần chơi
hỏng. Agent con xin duyệt trong cuộc trò chuyện *của nó*, luồng của cha không mang những yêu cầu
ấy, nên runner hỏi các cuộc con mỗi nửa giây và trả lời theo cùng chính sách; không có nó, lượt
của cha chờ mãi.

Rủi ro còn lại, đã thu hẹp chứ chưa xoá: persona của vài agent gõ lệnh kèm đường dẫn tuyệt
đối vào cây live. Mọi lệnh shell đều hỏi và runner không duyệt lệnh nêu đường dẫn ấy, nên một
lệnh như vậy không chạy; nhưng runner chỉ nhận ra đường dẫn viết nguyên văn, nên một lệnh dựng
đường dẫn bằng cách khác vẫn có thể lọt nếu case duyệt. Vì thế mọi case mặc định `deny` và chấm
cái agent *thử* làm; `approve` chỉ dành cho việc không đụng đường dẫn live. Các lớp chặn còn
lại: `HOME` của server trỏ vào bản sao, môi trường của server, và của mọi hook hay lệnh nó
chạy, chỉ có một danh sách nhỏ biến, bản sao không có `.venv` và không có symlink. Một chuỗi trong manifest hay `config.yaml` vẫn nêu
đường dẫn live được báo trong cảnh báo của lần chạy chứ không bị viết lại.

Model giả (`fake:echo`) cấp cho mỗi lệnh gọi một mã riêng, như provider thật vẫn làm: agent con
được tìm lại theo mã lệnh gọi của cha, nên hai cuộc trò chuyện giao việc ở cùng một chỗ mà cùng
mã thì cuộc sau nhận nhầm agent con của cuộc trước.

Mã nằm trong `scripts/`, tách theo việc để mỗi tệp ≤ 200 dòng như mã của gói (cùng một test
kiểm cả hai): `run_evals.py` (điểm vào), `eval_cli.py` (tuỳ chọn, chọn case, từ chối sớm),
`eval_play.py` (chơi một lần, chạy hết các case, bản ghi), `eval_reset.py` (đưa server và bộ
nhớ về như lúc đầu trước mỗi lần chơi), `eval_home.py` + `eval_copy.py` + `eval_layout.py` (bản sao), `eval_cases.py` +
`eval_expect.py` + `eval_check.py` (đọc và chấm case), `eval_shape.py` (dạng giá trị chung của
case, kỳ vọng và bước), `eval_canvas.py` (bước canvas), `eval_note.py` (bước canvas có tới
agent không), `eval_paste.py` (luật chép canvas vào chat), `eval_observe.py` (biến một cuộc trò chuyện thành thứ chấm được), `eval_client.py` (duyệt, câu
hỏi, sổ cái, canvas), `eval_report.py` (báo cáo). Server và client HTTP chia với bench: `llm_bench_server.py`, `llm_bench_client.py`.

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

## Tính năng nào được test ở đâu

CLAUDE.md đòi trang này nối mỗi tính năng với test giữ nó. Tệp vitest tính từ `web/src/`, spec
Playwright từ `web/e2e/`; test Python ghi theo node id của pytest, chạy thẳng được bằng
`uv run pytest <node id>`. Chữ trong ngoặc kép đứng sau một tệp là tiêu đề `describe`, `it` hay
`test` trong tệp đó, chép nguyên văn để `grep` tìm thấy. Bản đồ bắt đầu từ các tính năng ra sau
bản 0.8.0; phần có từ trước được kể theo tầng ở trên và vào đây khi được sửa tới. Thêm hay đổi
tên một test thì sửa dòng của nó trong cùng commit.

- **Nâng hay bỏ trần chi phí**
  - vitest: `components/cap-editor.test.tsx` ("raises the cap by a step above the current one",
    "takes a typed 0 as no cap at all", "refuses a negative cap without asking the server");
    `app-budget-notices.test.tsx` ("the budget notices",
    "the keyboard after a raise from a budget notice"); `app.test.tsx`
    ("raises a spent cap from the over-budget notice and lets the composer write again",
    "offers the cap on a budget halt and says when the server refused it");
    `components/activity-chrome.test.tsx`
    "says a spent budget locks the thread over an earlier note, until a turn runs"
  - Playwright: `chat-smoke.spec.ts`
    "a spent cap is raised from the budget pill's card and the composer writes again";
    `chat-state-phone.spec.ts` "a spent budget's notice keeps its raise on one line"
- **Lỗi request nói bằng lời: giữ câu server viết, dịch dump kiểm tra, 404 soạn sẵn, lỗi 5xx và
  lỗi mạng**
  - vitest: `lib/error-text.test.ts`; `hooks/use-thread.test.ts` nhóm "a request of the thread that
    fails" ("tells a conversation that cannot be loaded in our words", "tells a decision that cannot
    be sent in our words too": mất kết nối ở hai chỗ ấy hiện câu của ta, không phải câu tiếng Anh
    của trình duyệt); `components/cap-editor.test.tsx`
    ("says in words why the server refused a cap, not in its validation dump",
    "keeps a refusal the server wrote as a sentence",
    "says the conversation is gone when the server no longer has it",
    "says the server could not be reached rather than the browser's own words")
  - pytest:
    `tests/test_server_api.py::test_raising_a_spent_cap_lifts_the_budget_block_and_a_negative_cap_is_refused`
- **Duyệt, từ chối hay trả lời ngay trong Quản lý; "Đã xem" cho lỗi**
  - vitest: `components/attention-center.test.tsx`
    ("decides a waiting tool call where it is listed and lets the row go once the turn ends",
    "answers a waiting question with one of its choices and lets the row go",
    "counts down to the deadline, then disables the buttons, says it expired and reloads",
    "does not read the list again while an expired request cannot be read",
    "reads a request the sweep is late for less often as it waits, and never gives up",
    "says which ask pattern stopped a command",
    "keeps the %s of two requests of one second where it was listed while its turn resumes", với
    first và second — hàng vừa duyệt giữ đúng chỗ trong lúc lượt chạy tiếp, không tụt xuống dưới
    một yêu cầu khác bắt đầu cùng giây, nên nút của yêu cầu kia không trượt vào dưới con trỏ);
    `components/expiry-countdown.test.tsx`;
    `components/attention-seen.test.tsx`
    ("hides a failure once it is marked as read and keeps the others",
    "points to the requests waiting in another section instead of saying nothing waits");
    `lib/seen-runs.test.ts`; `app-attention.test.tsx`
    "counts a waiting request in the title, lands on it and settles it in place",
    "lists a request settled elsewhere %s",
    "lists a request settled elsewhere as another run starts waiting, %s",
    "lists a request settled elsewhere whose run waits again on its next tool, %s" (lịch sử duyệt
    đọc lại cả khi yêu cầu được quyết ở chỗ khác và chính run đó dừng lại ở tool kế tiếp — cùng
    id, cùng trạng thái, chỉ số bước tăng; khoá là `lib/run-progress.ts` `waitingKey`, test ở
    `lib/run-progress.test.ts` "waitingKey");
    `components/conversation-activity.test.tsx`
    "asks for the approvals again when a decided turn waits on its next tool" (lịch sử duyệt
    trong dải hoạt động của cuộc trò chuyện cũng vậy);
    `hooks/use-attention-badge.test.tsx`
    "prefixes the tab title with the requests waiting, not the failures";
    `screens/manage-screen.test.tsx`
    "counts waiting requests on Duyệt and failures on Hoạt động, each named";
    `app-activity.test.tsx`
    "counts a run waiting for approval as waiting, not as running, on the chat and the crew";
    `components/components.test.tsx` "ApprovalHistory" (trang lớn dần mỗi lần bấm Xem thêm)
  - Playwright: `activity-smoke.spec.ts`
    "a waiting request is approved from Quản lý without opening the chat";
    `legibility-smoke.spec.ts`
    "a request in an attention row reads in body text, not the card's amber"
  - pytest:
    `tests/test_server_api.py::test_a_request_the_ask_list_stopped_still_says_why_when_read_back`
- **Trình sửa agent lưu được lịch**
  - vitest: `components/agent-editor/schedules-section.test.tsx`
    ("saves a new row as exactly one timing and one action, with no kind",
    "holds the save and names the box while a timing cannot be read",
    "holds the save and names the box while two rows are given the same id");
    `components/agent-editor/channel-section.test.tsx`; `hooks/agent-draft-checks.test.ts`;
    `hooks/schedule-ids.test.ts`; `hooks/use-agent-draft.test.ts`
    ("never sends the derived kind, even on a row that still carries it",
    "reads the list again when the save's answer lacks `declared`",
    "sends an emptied consolidation cron as null, which takes the key out of the file"). Fake server
    của vitest và mock của Playwright cùng kiểm lịch theo luật của server, lấy từ
    `test/schedule-contract.ts`
  - Playwright: `schedule-editor-smoke.spec.ts`; `jobs-list-smoke.spec.ts` (Sửa lịch mở đúng phần
    lịch, tiêu đề dừng ngay dưới thanh của trình sửa chứ không thấp hơn, thanh dính sát mép trên);
    `manage-smoke.spec.ts`
    "a schedule is added from the jobs list through the agent's editor"
  - pytest: `tests/test_api_agents_edit.py::test_a_schedule_carrying_its_derived_kind_is_refused`,
    `tests/test_api_agents_edit.py::test_a_timing_the_clock_cannot_read_is_refused_before_it_is_written`,
    `tests/test_api_agents_edit.py::test_a_blank_row_that_lands_on_a_kept_rows_id_is_refused`,
    `tests/test_api_agents_edit.py::test_rows_an_edit_leaves_alone_do_not_hold_the_save`,
    `tests/test_api_agents_edit.py::test_a_schedule_cannot_take_the_consolidation_jobs_id`,
    `tests/test_api_agents_edit.py::test_a_saved_schedule_comes_back_in_the_shape_it_can_be_resent_in`,
    `tests/test_api_agents_edit.py::test_clearing_memory_consolidation_removes_the_key`
- **Toàn bộ tham số của một tool call**
  - vitest: `components/tool-args-detail.test.tsx`; `components/components.test.tsx`
    "opens a tool row's full arguments from under its summary"
  - Playwright: `legibility-smoke.spec.ts`
    "a tool call's full arguments wrap at phone width instead of widening the page";
    `phone-smoke.spec.ts`
    "a request's full arguments leave its buttons on screen in a short phone view"
- **Thẻ của lời gọi tool hỏng vẫn là "lỗi" khi thread được đọc lại từ server**
  - vitest: `state/thread-reducer.test.ts` nhóm "itemsFromMessages"
    ("keeps a call that failed as failed when the thread is read back": lời đáp mở bằng câu của
    registry khi tool báo lỗi, tool sập, không có tool tên đó hay hook của kit chặn thì thẻ giữ
    trạng thái `failed`, "reads a reply that only resembles a failure as a call that finished",
    "reads a reply that only quotes the refusal as a call that finished, read back or as it
    arrives": lời đáp chỉ trích lại câu từ chối ở giữa chữ thì thẻ là `done`, cả khi dựng lại từ tin
    đã lưu lẫn khi lời đáp vừa tới,
    "gives a reply the same status read back as it had when it arrived": cùng một lời đáp cho
    cùng một trạng thái ở luồng trực tiếp và khi dựng lại từ tin đã lưu);
    `state/thread-stored-status.test.tsx` nhóm "a call that failed, read back from the stored
    thread" ("stays failed when …": mười một kiểu server làm hỏng một lời gọi — tool báo lỗi,
    không có tool tên đó, hook chặn, tham số không phải JSON hợp lệ, tham số bị cắt, lượt hết số
    bước, lượt bị dừng vì lặp, id đã được duyệt cho lời gọi khác, hết thời gian chờ agent con,
    hội thoại rẽ nhánh trước khi lệnh chạy, lời gọi bị ngắt giữa chừng — đều cho thẻ `failed` và
    dấu lỗi trên thẻ; "has the status it had as it arrived when …": chín kiểu có lời đáp tới
    trong luồng trực tiếp cho cùng một trạng thái ở cả hai đường; "is not a reply that only holds
    the words further in, as when …" và "reads a reply that only resembles one as a call that
    finished": lời đáp chỉ chứa câu đó ở phía sau, câu thiếu ký tự cuối, hay kết quả hết thời
    gian chờ nằm dưới một tool không phải `delegate` thì thẻ là `done`) và nhóm "a handed-off
    task whose wait ran out, read back from the stored thread" ("is failed, and still names its
    canvases, with the sentence …": kết quả `delegate` hết thời gian chờ là `failed` mà vẫn hiện
    đủ chip canvas, cả khi câu báo đứng sau dòng đếm canvas bị lược lẫn ở dạng đã lưu trước khi
    kết quả có dòng canvas; "is not …": agent con dừng dở, agent con tự viết lại đúng câu đó, kết
    quả `done` hay `blocked`, câu đứng một mình không có kết quả phía trên, câu bị trích lại ở
    giữa một đoạn, hay câu đứng sau một đoạn chỉ chứa `(+` ở giữa chữ thì thẻ là `done`)
  - pytest: `tests/test_tool_reply_openings.py` (mỗi lời mở web dùng trong
    `web/src/lib/tool-reply.ts` đúng là phần chữ cố định của chuỗi server tương ứng, tính tới giá
    trị đầu tiên server điền vào, hoặc là cả câu khi câu không điền gì: `DENIED_TOOL` và
    `EXPIRED_TOOL`, `TOOL_FAILED`, `UNKNOWN_TOOL`, `TOOL_BLOCKED_BY_HOOK`, `TOOL_ARGS_INVALID`,
    `TOOL_ARGS_CUT_OFF`, `STEPS_HALTED_TOOL`, `LOOP_HALTED_TOOL`, `APPROVAL_CALL_MISMATCH`,
    `FORK_CALL_NOT_RUN`, `INTERRUPTED_TOOL`
    (`test_each_opening_the_web_reads_as_a_failure_is_how_the_server_words_one`), và registry
    chạy thật trả đúng các lời mở đó, nên hai bên không lệch nhau khi một bên đổi chữ);
    `tests/test_tool_reply_openings_turn.py` (qua cả một lượt: tham số không đọc được hoặc bị
    cắt, lượt hết số bước, lượt bị dừng vì lặp, id đã được duyệt cho lời gọi khác đều phát ra với
    `ok=False`, mở đúng lời web chờ và được lưu nguyên văn);
    `tests/test_tool_reply_delegate_wait.py` (bốn hằng web dùng để nhận ra `delegate` hết thời
    gian chờ khớp tên tool, giá trị `outcome` và phần chữ cố định của `DELEGATE_TIMEOUT`,
    `DELEGATE_CANVAS_MORE`; kết quả `timed_out` là `ok=False` với câu báo đứng đầu thân hoặc ngay
    sau dòng đếm canvas bị lược; một lượt thật lưu đúng kết quả đó dưới tên tool; agent con dừng
    dở thì `ok=True` và thân mở bằng `DELEGATE_UNFINISHED`, không phải câu web đọc)
- **Sự kiện của luồng mà bản web đang chạy chưa biết thì bị bỏ qua, thread không vỡ**
  - vitest: `state/thread-reducer.test.ts` nhóm
    "threadReducer on an event of a kind this build does not know" (server mới hơn bundle gửi một
    loại sự kiện thêm về sau: reducer trả lại đúng state đã nhận, vẫn là object đó, ở thread đang
    rảnh, đang nhận chữ, đang suy nghĩ và đang chờ duyệt, và sự kiện đã biết tới sau vẫn có tác
    dụng); `app-unknown-event.test.tsx` (một lượt có sự kiện lạ nằm giữa hai mảnh chữ vẫn kết bằng
    cả câu trả lời và không có thông báo lỗi nào; bong bóng đang viết có chữ ở cả hai phía của sự
    kiện; dòng trạng thái vẫn nói agent đang suy nghĩ)
- **Dừng thật, thread tự làm mới, pill kết nối lại**
  - vitest: `hooks/use-thread.test.ts` "Stop on a stream that resumed after a person answered";
    `state/thread-reducer.test.ts`
    "stopping ends the turn at once, drops the spent decision and says it stopped",
    "keeps that note through the loads that follow it, until one brings a new request",
    "opening another conversation starts from nothing, not even that note";
    `api/client.test.ts` "forwards the abort signal on a decision and on an answer";
    `app-thread-refresh.test.tsx`; `app-thread-refresh-races.test.tsx`;
    `hooks/use-activity.test.ts`; `app-activity.test.tsx`
    "learns how a run ended while the stream was down once the stream reconnects";
    `components/activity-chrome.test.tsx`
    "names the stream's four states in one case, as they take turns in one slot"
  - Playwright: `chat-smoke.spec.ts`
    ("Stop on an approved call cuts its stream and leaves nothing spinning",
    "a dropped live stream offers a thumb-sized retry that opens it again");
    `chat-state-phone.spec.ts`
    "the retry takes no room of its own, so the composer stays put when the stream drops"
- **Chép, chia sẻ, xuất Markdown, tệp gửi qua Telegram**
  - vitest: `components/copy-button.test.tsx`
    ("shows the text to copy by hand when the browser refuses the write",
    "has the hand-copy box take the focus in the commit that shows it", "BubbleActions");
    `components/markdown-body.test.tsx`
    ("keeps a fence with no language a block, not a run of inline code",
    "gives each fenced block a copy of its own that takes the code and nothing else");
    `components/agent-editor/prompt-section.test.tsx`
    "hands the prompt over to copy by hand where the browser has no clipboard";
    `components/conversation-options.test.tsx`; `lib/conversation-markdown.test.ts` (khối code
    hay HTML thô bị cắt giữa chừng được đóng lại để không nuốt các lượt sau);
    `components/message-thread.test.tsx` ("what the person sent through Telegram",
    "the actions under a reply")
  - Playwright: `phone-smoke.spec.ts` ("a copy the phone cannot make opens a box a thumb can close",
    "a code block's copy button stays in its corner, clear of the code",
    "the export in a conversation's options is big enough for a thumb")
  - pytest:
    `tests/test_channels_telegram.py::test_the_web_finds_saved_file_lines_by_the_words_the_channel_writes`
- **Sidebar: nhóm theo ngày, thời gian tương đối, chấm chưa đọc, bản nháp**
  - vitest: `components/conversation-list.test.tsx` ("the sidebar's day groups", "the unread dot");
    `lib/relative-time.test.ts`
    "puts 23:00 local in yesterday although it shares the UTC date with now";
    `hooks/use-draft.test.ts`; `components/composer-draft.test.tsx`;
    `hooks/use-conversations.test.ts` "takes its unsent draft with it, and only its own". Trình
    duyệt nhớ được hay từ chối lưu trữ đều dựng bằng `test/memory-storage.ts`
  - Playwright: `phone-smoke.spec.ts`
    "a half-written message waits in its conversation across drawer switches"
  - pytest (ghi sổ chạy nền không đẩy `updated_at`):
    `tests/test_store.py::test_background_bookkeeping_can_leave_a_conversation_dated_where_it_was`,
    `tests/test_memory_session_summary.py::test_a_recap_leaves_the_conversation_dated_by_its_last_message`,
    `tests/test_memory_conversation_title.py::test_the_models_name_arrives_without_making_the_conversation_look_new`
- **Lệnh `/` trong ô soạn**
  - vitest: `components/slash-popover.test.tsx`; `lib/slash-filter.test.ts`;
    `app-slash-commands.test.tsx`
  - Playwright: `keyboard-smoke.spec.ts`
    ("'/' lists the agent's commands and Enter puts the chosen one in the box",
    "a click into the thread puts the command list away, and the box brings it back");
    `phone-smoke.spec.ts` "the '/' button offers the agent's commands to a thumb, and the list fits"
- **Lịch sử run đã lưu và bộ lọc**
  - vitest: `components/recent-runs-log.test.tsx`; `components/activity-filters.test.tsx`;
    `hooks/use-run-history.test.ts`; `components/conversation-activity.test.tsx`
    "fetches its history on mount and merges it with live runs, each run once" và nhóm
    "the focus of whoever pressed the retry" (bấm Thử lại xong, focus quay về nút Thử lại, sang
    run đầu tiên vừa tải về, sang nút mở dải trên điện thoại hay sang dòng báo chưa chạy lần nào —
    trên điện thoại dải giữ lại dòng đó chứ không ẩn đi mang theo focus; không giành lại focus người dùng đã đặt chỗ khác, không kéo sang cuộc trò chuyện vừa mở — hai test "không đổi" này cho câu trả lời về trong `act`, nên effect có thể dời focus đã chạy xong trước khi kiểm, chứ không kiểm lúc effect còn chưa tới);
    `state/activity-reducer.test.ts` "runGroups" (run con nằm dưới đúng lượt đã giao nó, kể cả
    khi hai lượt chạm cùng một giây hay run con bắt đầu ở giây cuối của lượt)
  - Các run bắt đầu cùng một giây (giờ bắt đầu chỉ đến giây): run còn chạy đứng trước, rồi run
    kết thúc muộn hơn, còn lại giữ thứ tự trang nghe thấy, mới nhất trước — mọi danh sách xếp
    như nhau: vitest `lib/run-order.test.ts` nhóm "newestFirst" (kể cả "gives the opposite answer
    for a pair compared the other way round": mỗi quy tắc đúng cả khi so theo chiều ngược lại) và
    nhóm "withHeld" (hàng đang giữ quay về chỗ cũ); `state/activity-reducer.test.ts`
    "keeps runs of the same second in the list's order, behind one it hears start" và trong
    "runGroups" "keeps runs that share their start and their end in the order given, a lone child
    included"; `hooks/use-run-history.test.ts` nhóm "mergeRuns" (run luồng trực tiếp đã biết giữ
    thứ tự trang nghe thấy, không theo thứ tự kho lưu lần cuối; run chỉ kho có xếp sau);
    `components/conversation-activity.test.tsx`
    "names the same run on its line and its first card when two ran in the same second" (dòng
    "Lượt chạy gần nhất" và thẻ đầu tiên nói cùng một run, trước và sau khi lịch sử về) và
    "keeps the order the page heard runs of the same second in once the history lands", với run
    còn chạy và run đã kết thúc (thẻ và thanh trạng thái của dải không đổi sang run khác khi lịch
    sử về theo thứ tự kho lưu)
  - Playwright: `activity-smoke.spec.ts`
    "the activity log narrows to one agent on the server, then reaches further back";
    `phone-smoke.spec.ts`
    ("the activity log's chips fold on a phone, then wrap and stay big enough to tap",
    "a chat whose run history cannot be read says so, with a retry big enough to tap")
  - pytest: `tests/test_activity.py::test_one_agents_runs_are_not_crowded_out_by_a_busier_agent`
- **Sổ cái sử dụng đầy đủ: lời gọi bên cạnh lượt**
  - pytest: `tests/test_side_calls.py` (ghi mục đích và agent, lần gọi rơi tuyến không ghi,
    lần gọi bỏ dở sau chunk đầu hay hết giờ ghi giá không rõ, sổ hỏng không làm mất câu trả
    lời, mục đích lạ bị từ chối, tổng theo ngày/model/mục đích cộng cả hai bảng, một tên model
    sau hai provider vẫn là hai dòng, tool trả phí cộng giá vào run và step);
    `tests/test_side_calls_wiring.py` (ảnh, PDF scan, tóm tắt output, tiêu đề, tóm tắt phiên,
    cô đọng, wiki đều ghi đúng mục đích và đúng cuộc trò chuyện; bảo trì không thuộc cuộc
    nào và chỉ đếm một lần);
    `tests/test_tools_registry.py::test_a_summary_without_a_price_is_charged_as_one_of_unknown_cost`;
    `tests/test_memory_session_summary.py::test_a_recap_that_came_back_blank_is_still_charged`;
    `tests/test_server_agents_activity_jobs.py::test_stats_carry_the_ledger_with_tokens_and_what_each_call_was_for`
  - vitest: `components/stats-panel.test.tsx` "splits the whole ledger by what each call was
    for, named in words", "leaves the purpose card out while the ledger is empty or the server
    has none"; `components/activity-cards.test.tsx` "prices a tool that asked a model itself,
    and says nothing on one that did not"
  - Playwright: `phone-smoke.spec.ts`
    "the costs page fits, cache columns and today's tiles included" (bảng theo mục đích vừa
    màn hình điện thoại)
- **Dừng lượt cứ gọi lại y hệt một lệnh**
  - pytest: `tests/test_loop_guard.py` (lần thứ ba liên tiếp thì nhắc, lần thứ sáu thì dừng; đổi
    tham số, hai lệnh xen kẽ, ghi chú tiến độ, câu hỏi hay câu trả lời xen giữa đều đếm lại từ
    đầu; ghi chú đi kèm lệnh lặp không che được lần lặp; lệnh song song đổi thứ tự vẫn là một
    lệnh; lời nhắc nằm sau kết quả lần thứ ba, chỉ nêu tên công cụ, không chép tham số hay kết
    quả; lệnh thứ sáu không chạy mà nhận kết quả từ chối nên mọi lệnh đều có kết quả; lượt đổi
    hướng sau lời nhắc chạy tiếp; "chạy test, sửa, chạy lại" không bị nhắc; lý do dừng đọc bằng
    lời); `tests/test_channels_telegram.py::test_deliver_reports_a_run_that_stopped_without_a_reply`,
    `tests/test_channels_telegram.py::test_a_reply_from_a_run_that_stopped_early_carries_a_notice`
    (Telegram nêu lý do dừng bằng lời, không bằng mã)
  - vitest: `lib/run-summary.test.ts`
    "reads the halt reasons and the interrupted marker as sentences"; `app.test.tsx`
    "says in words why a turn halted on %s" (với `max_steps` và `loop`)
- **Lượt hết số bước tối đa**
  - pytest: `tests/test_agent_loop.py` ("test_max_steps_halts_a_tool_loop",
    "test_a_turn_that_answers_on_its_last_allowed_call_is_done",
    "test_a_turn_out_of_steps_closes_the_calls_it_never_ran": lệnh mà lần gọi cuối xin không
    chạy mà nhận kết quả nói lượt đã hết bước, và tin kế tiếp không đóng lại chúng thành lệnh
    bị ngắt)
- **Token, cache và thời gian tới token đầu**
  - vitest: `components/run-timeline.test.tsx`; `lib/format-usage.test.ts`;
    `components/stats-panel.test.tsx`; `state/activity-reducer.test.ts`
    "keeps the prompt and cached tokens of a finished call, and that it thought first"
  - Playwright: `phone-smoke.spec.ts`
    "the costs page fits, cache columns and today's tiles included"
  - pytest:
    `tests/test_server_agents_activity_jobs.py::test_stats_add_up_each_agents_cache_over_the_same_runs_as_its_spend`,
    `tests/test_server_agents_activity_jobs.py::test_stats_count_apart_the_calls_that_gave_a_prompt_but_no_cache_figure`,
    `tests/test_server_agents_activity_jobs.py::test_stats_say_when_the_calls_gave_tokens_but_no_cache_figure`
- **Duyệt đề xuất trí nhớ: diff và fact chính xác**
  - vitest: `components/memory-panel.test.tsx` "MemoryPanel proposal review";
    `components/compile-proposal-view.test.tsx`; `lib/line-diff.test.ts`
  - Playwright: `memory-phone-smoke.spec.ts`
    "the history toggle and a compiled page's disclosure are full touch targets that still look openable"
  - pytest:
    `tests/test_memory_proposals_apply.py::test_a_late_approval_of_a_rejected_proposal_writes_nothing`,
    `tests/test_memory_proposals_apply.py::test_a_decision_arriving_during_an_approval_waits_for_it_and_is_refused`,
    `tests/test_memory_proposals_apply.py::test_approving_an_append_twice_writes_the_line_once`,
    `tests/test_server_memory_api.py::test_approving_from_a_stale_tab_after_a_reject_is_a_conflict_that_writes_nothing`,
    `tests/test_server_memory_api.py::test_approving_for_an_agent_that_left_the_crew_is_not_a_conflict`,
    `tests/test_memory_wiki_compile.py::test_an_autonomous_agent_leaves_a_decision_made_first_alone`
    (agent tự chủ cũng ghi theo cùng luật một-quyết-định-một-lúc, nên đề xuất bị từ chối ngay khi
    vừa hiện thì không trang nào được ghi), `tests/test_memory_jobs_decide_off_loop.py` (việc dọn
    bộ nhớ và dựng wiki chờ một quyết định đang ghi ở web mà không chặn event loop)
- **Vệ sinh bộ nhớ: ngày trên từng dòng, cổng tự áp dụng do mã kiểm tra chứ không phải model,
  đề xuất mới thay chỗ đề xuất cũ, và vệ sinh fact người dùng luôn chờ duyệt**
  - vitest: `components/memory-panel.test.tsx`
    ("shows why the model changed or dropped each line, before the person decides",
    "shows nothing extra for a proposal with no reasons to give",
    "drops whichever bullet marker the model used in front of a reason",
    "shows a superseded rewrite in the history, with no undo since nothing of it was applied",
    "flags a fact nobody has confirmed in over ninety days", "does not flag a fact confirmed recently")
  - pytest:
    `tests/test_memory_hygiene.py` (các hàm thuần của `fact_dates.py`: danh sách xem lại gồm
    dòng thiếu ngày và dòng cũ, một ngày không có thật tính như thiếu ngày, mỗi nhóm tối đa 40 dòng
    và đếm phần còn lại; lý do được tách trước khi cắt bớt, dấu tách viết thường không dấu hay ở
    dạng NFD vẫn nhận; dòng bị bỏ hay bị viết lại khác với chỉ đổi ngày hay chỉ thêm dòng; ngày
    bịa ra không khớp nguồn nào), `test_consolidate_stores_reasons_and_the_prompt_carries_the_review_list_and_today`
    (prompt mang danh sách xem lại và đúng ngày hôm nay của lần cô đọng),
    `test_an_autonomous_agent_with_a_dropped_line_stays_pending_and_leaves_the_file`
    (một agent autonomous làm rơi một dòng vẫn dừng ở đề xuất chờ duyệt, tệp giữ nguyên),
    `test_an_autonomous_agent_with_only_an_addition_still_auto_applies`,
    `test_an_autonomous_agent_with_only_a_date_change_still_auto_applies`
    (hai trường hợp vẫn tự áp dụng vì không dòng nào mất và không ngày nào bịa ra),
    `test_a_rewrite_with_an_invented_date_stays_pending_and_names_the_date`,
    `test_a_dropped_line_and_an_invented_date_are_both_named` (tóm tắt run nêu đủ cả hai lý do bị
    giữ), `test_a_date_equal_to_the_consolidation_today_is_not_invented`;
    `tests/test_memory_proposal_stale.py` (`supersede` cần ít nhất một bộ lọc và chỉ đổi đề xuất
    đang chờ của đúng agent; duyệt một bản viết lại khi `MEMORY.md` đã đổi là lỗi stale, qua HTTP
    là 409 và tệp giữ nguyên; duyệt một đề xuất đã bị thay cũng là 409; lần cô đọng thứ hai thay
    chỗ bản viết lại cũ còn chờ; hoàn tác ghi thẳng, không bị cổng chặn; fact cũ hơn 90 ngày được
    báo `stale` trong `GET /api/memory/user`);
    `tests/test_memory_fact_review.py` (chỉ master mới xem lại fact người dùng, và agent khác
    không gọi model lần hai; kể cả khi autonomous vẫn chỉ tạo đề xuất chờ duyệt; mỗi lần xem lại
    tính một side call phí `consolidate`; fact cũ đứng trước, cũ nhất trước, fact không đọc được
    ngày tính là cũ nhất, phần còn lại mới nhất trước; chỉ 60 fact được đưa vào và tên nằm ngoài
    phần cắt bị bỏ qua; mỗi dòng fact mang mô tả và thân đã gộp dòng, cắt ở 400 ký tự; mảng JSON
    đầu tiên được đọc ra dù nằm trong đoạn văn hay khối code; lý do cắt ở 300 ký tự; tên lạ, bản
    cập nhật rỗng hay không đổi gì bị bỏ qua; quá 10 mục thì cắt; json hỏng không tạo đề xuất
    nào; tóm tắt run đếm số đề xuất fact, nêu câu trả lời hỏng, và nói rõ khi bước xem lại lỗi mà
    bản viết lại vẫn còn; bước xem lại đọc cùng khối ghi chú đã cắt theo ngân sách và cùng ngày
    hôm nay với bước viết lại; đề xuất giống hệt không bị nhân đôi),
    `tests/test_memory_fact_review.py::test_a_different_body_supersedes_the_old_pending_hygiene_proposal`
    (một đề xuất vệ sinh fact mới thay chỗ đề xuất cũ cùng loại còn đang chờ),
    `tests/test_memory_fact_review.py::test_a_forget_supersedes_a_pending_update_of_the_same_fact`
    (một đề xuất quên thay chỗ đề xuất cập nhật cùng fact, còn đề xuất tạo từ cuộc trò chuyện giữ
    nguyên)
- **Ảnh từ trang khác trong câu trả lời và trang wiki chỉ tải khi bấm, không gửi referrer; lời đồng
  ý chỉ cho đúng địa chỉ đã bấm**
  - vitest: `components/markdown-body.test.tsx` "an image in a reply" (kể cả
    "asks again when the image it showed gives way to one at another address": trang vẽ lại với
    ảnh ở địa chỉ khác tại cùng chỗ, dù cùng site, thì nút hỏi quay lại và ảnh mới không tải;
    "asks again when the address only adds to the one agreed to, or is that one cut short": địa
    chỉ đang viết dở tới từng mảnh, đồng ý với một mảnh không phải đồng ý với địa chỉ dài hơn hay
    ngắn hơn nó, và ảnh được hỏi lần hai cũng nhận focus của nút như ảnh đầu;
    "shows an image again unasked when the page comes back to the address agreed to, and takes no
    focus for it": quay về đúng địa chỉ đã đồng ý thì ảnh hiện lại mà không hỏi, vì người dùng đã
    đồng ý với chính địa chỉ đó, và focus ở yên chỗ cũ;
    nhóm "when the image the keyboard is on gives way to its button": ảnh đang giữ focus mà đổi địa
    chỉ thì nút hỏi lại nhận focus thay vì để focus rơi về trang ("puts the keyboard on the button,
    not on the page"), focus người dùng đã chuyển đi chỗ khác thì ở yên ("leaves the keyboard where
    the person has since put it"), và ảnh hiện lại không hỏi sau đó không kéo focus về nút khi nó
    đổi địa chỉ lần nữa ("takes the keyboard for the image it replaced only, not for one shown
    unasked later");
    "never holds the app's own image, and showing one agrees to nothing from outside";
    "asks about each image of a page on its own": hai ảnh trong một trang được hỏi riêng, một ảnh
    đổi địa chỉ thì chỉ ảnh đó hỏi lại)
- **Wiki đọc được: link, đánh dấu ổn, câu hỏi mở, ghi chú hôm nay; theo dõi compile và consolidate**
  - vitest: `components/wiki-read-view.test.tsx`; `lib/wiki-links.test.ts`;
    `components/wiki-section.test.tsx` ("WikiSection read mode", "WikiSection compile tracking");
    `components/memory-panel.test.tsx`
    "follows the consolidation it started, then re-reads the memory and the proposals"
  - Playwright: `manage-smoke.spec.ts`
    ("a wiki page reads as prose, its link leads to the next page, and one tap marks it fine",
    "a compile that ends while the stream is down lets go of its chip on the reconnect");
    `memory-phone-smoke.spec.ts`
    ("a page followed from the bottom of a long one opens at its title, with focus there",
    "an open question holding a long link wraps on a phone instead of running off the screen")
- **Job đọc được và badge job hỏng**
  - vitest: `components/jobs-panel.test.tsx` ("a job read at a glance",
    "where the jobs list sends a person to change a schedule"); `lib/cron-text.test.ts`;
    `screens/manage-screen.test.tsx`
    "counts the jobs whose last run failed beside the jobs entry, and nothing otherwise";
    `hooks/use-route.test.ts` "reads the job a page was opened from out of the query"
  - Playwright: `manage-smoke.spec.ts`
    "a job reads its schedule in words, shows its last run, and a failure is counted on the nav";
    `jobs-list-smoke.spec.ts` ("a job off in its profile dims its text but not its buttons",
    "the back link of a job's editor or run returns to that job's row")
- **Hàng mục Quản lý trên điện thoại: pill đang mở trong tầm nhìn, hàng người dùng đã cuộn thì
  đứng yên**
  - vitest: `screens/manage-screen.test.tsx` ("brings the current section's entry into view",
    "brings the current section's entry back into view when %s change" — mỗi số đếm một ca: run
    đang chạy, run lỗi, yêu cầu chờ duyệt, đề xuất bộ nhớ, lịch lỗi;
    "leaves the row where the person scrolled it when a count changes")
  - Playwright: `manage-row-phone.spec.ts`
    ("a count arriving leaves the row where the person scrolled it",
    "the current pill stays in view as the counts before it widen the row")
- **Thanh "Có bản mới" và phiên bản trong Cài đặt**
  - vitest: `hooks/use-version-check.test.ts` (kể cả "makes no look of its own on a reconnect when a look since the drop reached the server", "looks at most every half minute on a stream that keeps dropping, the last look made late"); `components/update-bar.test.tsx`; `app.test.tsx`
    ("offers a reload once the server runs a newer build than the page",
    "asks the server again when settings open, and names both builds there")
  - Playwright: `version-refresh.spec.ts`
- **Câu tóm tắt vì sao run dừng**
  - vitest: `lib/run-summary.test.ts`; `components/run-chip.test.tsx`;
    `components/activity-cards.test.tsx` "reads a halt or interruption code as the run card does"
- **Run dừng chờ duyệt qua khởi động lại, và khi cuộc của nó bị xoá**
  - pytest: `tests/test_activity_restart.py`;
    `tests/test_memory_conversation_title.py::test_a_conversation_deleted_or_renamed_while_naming_waited_costs_nothing`;
    `tests/test_tools_delegate.py::test_a_child_deleted_while_the_parent_waits_is_reported_in_words`
- **Màn Quản lý báo mất kết nối, thử lại, và đọc lại đội khi nối lại**
  - vitest: `app-manage-connection.test.tsx`
    ("says the pages stopped following the server when the stream drops, and a retry opens a fresh one",
    "says nothing while the stream first connects",
    "says the device is offline instead of offering a retry that cannot work",
    "reads the crew, the schedules and the totals again when the stream comes back, not when it first opens")
- **Vùng chạm ≥40px trên điện thoại**
  - Playwright: `touch-targets-phone.spec.ts` — quét mọi nút, link, ô nhập, select, summary, công tắc và
    tab trên từng trang (chat, mười trang Quản lý) và trong drawer cuộc trò chuyện ở 390×844 cảm ứng;
    checkbox đo theo label bọc nó, link nằm trong câu được miễn như WCAG ("every control on %s is big
    enough for a finger", "every control in the phone's conversation drawer is big enough for a
    finger"); phép quét nằm ở `small-targets.ts`, quét được riêng một vùng, và `canvas.spec.ts` dùng nó
    cho dock canvas, `canvas-note.spec.ts` cho chip ghi chú dưới tin (cả ở 1000 px cảm ứng, nơi chỉ
    `touch-targets.css` giữ nút chép ghi chú ở 40px)
- **Agent con kết lượt bằng một dòng `MEDIA:` trần vẫn đưa lời khuyên tới người dùng**
  - pytest:
    `tests/test_delegate_attachments.py::test_an_answer_written_beside_a_tool_call_is_not_lost_to_a_bare_chart_line`;
    `tests/test_delegate_attachments.py::test_only_a_chart_only_ending_reaches_back_for_the_words`
    (lời nháp trước một câu trả lời thật vẫn bị bỏ, dòng đính kèm không gửi hai lần);
    `tests/test_delegate_attachments.py::test_the_words_are_looked_for_only_since_the_task_was_given`
- **Agent con chạy lại sau duyệt, câu hỏi hay khởi động lại vẫn không giao việc tiếp được**
  - pytest: `tests/test_resumed_child_depth.py` (cuộc con chạy lại không truyền độ sâu vẫn ở độ
    sâu 1, cuộc người mở giữ độ sâu 0, con lấy lại tool `delegate` qua `deps_for_conversation` vẫn
    nhận lỗi quá sâu và không tạo cuộc cháu nào)
- **Kiểm thử hành vi bằng model thật, chạy trên bản sao của home**
  - pytest: `tests/test_eval_cases.py` (đọc case từ tệp hay thư mục; khoá lạ, thiếu id hay
    agent, tin nhắn không phải chuỗi, regex hỏng, id trùng bị từ chối trước khi tốn tiền; từng
    loại kỳ vọng: gọi và không gọi tool theo tên, tham số, agent và lượt, xin duyệt, số lần gọi tối đa,
    câu đáp chứa và không chứa, giao việc cho agent nào và việc đi tới outcome nào (không nêu
    outcome thì outcome nào cũng được, outcome lạ bị từ chối), giá tối đa; "hai phần ba số lần
    chơi đạt thì case đạt"; bước canvas đọc đúng chỗ giữa các tin, bước lạ, tin có `: ` không
    ngoặc, bước thiếu hay thừa khoá, `kind` lạ, đoạn chọn rỗng, `edit_canvas` có `new` trùng
    `old`, bước chọn không có tin sau và case chỉ có bước bị từ chối, kỳ vọng canvas sai dạng
    cũng vậy);
    `tests/test_eval_canvas.py` (tạo canvas trong cuộc trò chuyện và mở nó, sửa lưu trên đúng bản
    vừa đọc, chưa mở thì lấy canvas mới đổi gần nhất, không có canvas hay `old` không có đúng một
    lần thì hỏng mà không lưu, server từ chối hay trả lời ở dạng không đọc được (thiếu id hay
    bản, không phải JSON) thì hỏng mà eval đi tiếp, mất server thì ném lỗi như
    một lượt, vùng chọn mang đúng dòng và chỉ đi với tin kế, mở canvas khác thì bỏ vùng chọn; chấm
    canvas: chứa, không chứa, số canvas, dán ở lượt nào hay chia ra hai tin cũng hỏng và nêu tên
    canvas bị dán, trích một dòng hay nêu dòng ngắn thì không tính, mỗi canvas chấm riêng; mỗi tin
    ghi lại phần ghi chú nợ agent: canvas người tạo hay lưu kể từ tin trước, ở bản server trả về
    khi lưu, và đoạn tin mang theo; tin trước khi có canvas không nợ gì, hai canvas mới đều nợ);
    `tests/test_eval_note.py` (ghi chú nêu canvas ở bản người để lại, dạng nào cũng được: canvas
    chưa đọc, đoạn diff, đã lên bản, sửa nhiều chỗ; không có ghi chú, ghi chú rỗng hay chỉ nêu
    canvas đang mở thì hỏng; bản cũ hơn, canvas có id dài hơn cùng đầu, bản có cùng chữ số đầu,
    dòng vùng chọn và dòng trích không tính, kể cả dòng trích trông như một dòng báo thay đổi;
    mỗi canvas phải được nêu riêng; đoạn mang theo phải được trích như ghi chú trích, kể cả ngắt
    dòng dán từ trình soạn thảo, đoạn quá dài chỉ cần phần ghi chú trích; ghi chú đọc từ tin chứa
    chữ case gửi chứ không từ tin loop guard; tin cuộc trò chuyện không giữ để observe báo);
    `tests/test_eval_paste.py` (tỉ lệ cụm ba chữ chat lặp lại: canvas dòng ngắn nói lại nguyên văn,
    thành bảng hay dồn một dòng không dấu đều là dán hết; nêu tiêu đề, đề mục mở đầu kể cả sau
    dòng trống, dòng chính là tiêu đề dù markup nào, trích dòng vừa sửa dù nó chiếm gần hết
    canvas, dòng canvas lặp hai lần vẫn là một dòng, trích hai dòng vừa đổi của canvas dài hơn,
    nêu các đề mục hay việc vừa thêm thì không phải dán; nói lại cả danh sách, dàn ý đổi cách
    đánh số, dòng dài bỏ nhãn vẫn là dán; canvas quá ngắn thì không bao giờ);
    `tests/test_eval_observe.py` (mỗi lệnh gọi mang số lượt và agent, việc của agent con tính
    vào lượt của cha đã giao, outcome của mỗi lần giao việc đọc từ dòng hai kết quả của nó, kết
    quả cũ không có dòng đó thì không có outcome; lời đáp cuối, lỗi và giá, tìm ra các cuộc con;
    mọi câu agent nói trong cuộc gốc, tiêu đề và nội dung từng canvas; lượt đếm theo tin case đã
    gửi: ghi chú loop guard không mở lượt cũng không cắt lời đáp, agent nói trước tin kế của
    người không mở lượt đó, cuộc trò chuyện thiếu tin đã gửi thì hỏng trừ khi lần chơi đã hỏng);
    `tests/test_eval_client.py` (duyệt và từ chối được ghi lại, lệnh nêu đường dẫn live bị từ
    chối kể cả khi chính sách là duyệt, câu hỏi lấy câu trả lời kế tiếp và hết thì hỏng, một
    lượt vẫn bị cắt khi luồng cứ gửi keep-alive, yêu cầu duyệt của agent con được trả lời, được
    hỏi lại khi nó xin lần nữa, và hỏng rõ ràng khi không trả lời được; giá các lượt của cuộc
    trò chuyện bị xoá vẫn nằm trong sổ cái, lời gọi miễn phí không tính là không báo giá, lần
    xoá bị từ chối thì ném lỗi và không cộng gì; mọi cuộc trò chuyện và canvas được liệt kê và
    xoá theo id; phần `paid` cộng đúng bằng phần sổ cái thật mất khi xoá một cuộc);
    `tests/test_eval_reset.py` (bộ nhớ trở lại như cũ dù lần chơi ghi thêm, sửa hay xoá; gốc vốn
    không có thì lại không có; tệp hoá thư mục và ngược lại được đặt lại; symlink lần chơi để lại
    bị xoá mà không theo; gốc ngoài thư mục chạy, kể cả qua symlink, và symlink có sẵn lúc bắt
    đầu bị từ chối; các gốc là bộ nhớ của người và ghi chú của từng agent; đặt lại xoá mọi canvas
    rồi mọi cuộc trò chuyện, kiểm lại rồi mới đặt bộ nhớ; còn sót gì trên server hay không đặt
    lại được bộ nhớ thì hỏng, nói rõ cái gì, và không đụng gì bên ngoài);
    `tests/test_eval_home.py` (bản sao bỏ bí mật, trạng thái, cơ sở dữ liệu của server, lịch sử,
    phiên đăng nhập, symlink, kit ngoài thư mục crew; giữ cấu hình, persona, bộ nhớ, workspace
    và cơ sở dữ liệu của workspace; nạp lại được bằng đúng bộ đọc của server; không còn lịch,
    Telegram, cô đọng bộ nhớ; không manifest nào nêu đường dẫn home live; không agent nào còn
    danh sách cho phép lệnh shell, ở manifest lẫn `config.yaml`; chuỗi còn nêu đường dẫn live
    được báo chứ không viết lại; từ chối đường dẫn ra ngoài, thư mục chạy nằm trong home hay
    workspace, một workspace là hay chứa thư mục home của người dùng; cây live không đổi; thư
    mục chạy chỉ chủ sở hữu đọc được; chép hỏng thì dọn sạch);
    `tests/test_eval_report.py` (luật đạt, đếm khi chạy thử, tiền là cận dưới khi có lời gọi
    không báo giá, dạng dòng, bảng, markdown và json);
    `tests/test_run_evals.py` (một lần chơi đạt hay hỏng và vì kỳ vọng nào, cuộc trò chuyện
    không tự động, lỗi ở lượt đầu chặn lượt sau, tiền tính theo mức tăng của sổ cái, hết ngân
    sách thì dừng trước lần chơi kế, Ctrl-C để lại số của các lần đã xong, một lượt quá giờ hay
    mất server dừng cả cuộc, các từ chối trước khi chép gì, chạy thử qua một server thật; bước
    canvas chạy giữa các lượt và mọi tin sau mang canvas đang mở, bước hỏng chặn tin sau mà không
    dừng eval, tin trước khi có canvas chỉ có chữ, bước canvas không tới agent thì lần chơi hỏng; khi chạy thử, server đặt vùng chọn đúng dòng eval
    đếm trên bản đã sửa, ghi chú thật của server nêu canvas ở bản đã lưu và trích vùng chọn,
    người sửa canvas agent vừa tạo thì agent nhận diff của đúng lần sửa ấy, và một lần dán ba
    dòng bị bắt từ JSON thật của server; mỗi lần chơi bắt
    đầu sau một lần đặt lại, không đặt lại được thì không chơi và dừng eval; mỗi lần chơi để lại
    bản ghi tên theo thứ tự case, id và lần, giữ cuộc trò chuyện, cuộc con, canvas và lần xin
    duyệt; bộ nhớ không đặt lại được bị từ chối trước lần chơi đầu; khi chạy thử, lần sau không
    thấy canvas, cuộc trò chuyện hay ghi chú của lần trước);
    `tests/test_llm_bench_client.py` (server bench và eval chỉ nhận từ môi trường của người
    chạy những biến một chương trình cần và model key; home, thiết lập live, danh sách cho phép
    lệnh shell, token bot, khoá của dịch vụ khác và socket ssh-agent ở ngoài);
    `tests/test_serve_flags.py` (`--no-schedule` tắt cả scheduler lẫn kênh, không đụng `--port`);
    `tests/test_echo_provider.py` (mỗi lệnh gọi của model giả có mã riêng, như provider thật,
    nên hai cuộc trò chuyện giao việc ở cùng một chỗ không nhận nhầm agent con của nhau; dòng
    cuối cùng mở đầu bằng `/tool`, khi nó cùng tham số kết thúc tin, là lời gọi dù phía trên có
    gì, kể cả ghi chú canvas;
    dòng `/tool` nằm trong ghi chú mà người chỉ viết chữ thường thì không gọi gì; tham số có chữ
    `/tool` được giữ nguyên)
  - Thủ công, tốn tiền thật: `scripts/run_evals.py` trên các case trong `<home>/evals/`
- **Kết quả giao việc nói việc đi tới đâu (`outcome=` ở dòng hai), không chỉ run kết thúc ra sao;
  chỉ việc đi tới `done` mới được chuyển thẳng cho người dùng**
  - pytest: `tests/test_delegate_outcome.py` (dòng `Status:` theo mọi kiểu model viết,
    `DONE_WITH_CONCERNS` không bị đọc thành `DONE`, dòng cuối thắng, trạng thái lạ bị bỏ qua, lý do
    lấy từ `Summary:` khi dòng `Status:` không có, chữ `BLOCKED` trần chỉ tính khi không có dòng
    `Status:`; dòng `Status:` trong khối code không lấn dòng khép lại bên ngoài, khối khép lại con
    bọc trong code vẫn tính, `status: blocked` viết thường trong một tệp con cho xem thì không;
    runtime thắng lời khai: run không xong là `failed`, approval tool quyết định gần nhất bị từ chối
    hay hết hạn là `blocked`, câu hỏi không ai trả lời thì không; hết giờ chờ vẫn giữ dòng một);
    `tests/test_tools_delegate.py::test_the_first_two_lines_are_the_ones_the_web_card_reads`
    (Python và regex của thẻ web đọc cùng hai dòng),
    `::test_a_child_that_needs_more_context_is_not_handed_on`,
    `::test_a_child_done_with_concerns_goes_back_to_the_parent_whole`,
    `::test_a_child_that_declares_done_is_handed_on_word_for_word`,
    `::test_a_child_whose_last_approval_was_refused_is_blocked`,
    `::test_a_question_after_a_refused_tool_does_not_hide_the_refusal`,
    `::test_a_child_still_waiting_when_the_wait_runs_out_failed`;
    `tests/test_store_approvals_jobs_usage.py::test_history_can_be_narrowed_to_tool_approvals`;
    `tests/test_delegate_relay.py::test_a_child_that_needs_more_context_goes_back_through_the_boss`,
    `::test_a_child_halted_for_repeating_itself_is_reported_as_failed`,
    `::test_a_status_in_a_code_block_never_lets_a_blocked_child_through`;
    `tests/test_delegation_contract.py::test_every_status_the_skill_offers_is_one_the_parent_reads`
  - vitest: `lib/delegate-result.test.ts` ("reads what the task came to, and why, from the second
    line", "reads an outcome with no reason, and one with no reply after it", "leaves the outcome
    out for a result written before there was one", "goes by the outcome when there is one", "goes
    by how the run ended for a result that has no outcome", và mục `delegateReason`: mã dừng, hết
    giờ chờ khi con còn chạy, tool bị từ chối hay hết hạn thành câu, lời của con giữ nguyên);
    `components/delegate-cards.test.tsx` ("says in words what the task came to, and marks one that
    is not done", "marks a task that failed apart from one that only stopped short", "says why in
    words, not in the codes the delegating agent reads", "reads a finished task as done, with
    nothing more to explain")
  - Playwright: `delegate-smoke.spec.ts`
    "a task that came back short of done says so, and why, on the card"
  - Thủ công, tốn tiền thật: case `a-lookup-is-handed-to-the-researcher` trong
    `<home>/evals/delegation.yaml` (`delegates_to: {agent: researcher, outcome: done}`)
- **Kết quả giao việc nêu các canvas agent con đã viết, ngay dưới dòng `outcome=` và trên một dòng
  trống luôn có**
  - pytest: `tests/test_delegate_canvases.py`
    ("test_the_canvases_the_child_wrote_stand_right_under_the_outcome": mỗi canvas một dòng ở phiên
    bản lớn nhất con viết, theo thứ tự viết lần đầu, thẻ khớp `TAG_RE` và cả dòng khớp regex
    `CANVAS` của web, `reply` vẫn đúng là câu trả lời,
    "test_a_child_that_wrote_no_canvas_leaves_only_the_blank_line",
    "test_an_answer_that_opens_like_a_canvas_line_stays_below_the_blank_line",
    "test_a_long_title_is_cut_like_any_field_quoted_in_a_result",
    "test_canvases_past_the_twelfth_are_counted_in_the_first_line_of_the_body",
    "test_a_canvas_deleted_while_the_parent_waited_is_not_named",
    "test_a_task_that_is_not_done_still_names_what_was_written",
    "test_a_child_stopped_short_names_its_canvases_above_the_unfinished_note",
    "test_a_wait_that_runs_out_still_names_what_the_child_had_written": mười hai dòng đầu và câu
    đếm phần còn lại, như mọi kết quả khác,
    "test_carrying_a_canvas_to_or_from_a_file_unchanged_names_nothing": xuất và nhập không đổi
    không sinh dòng, cũng không chia sẻ canvas sang cuộc gốc,
    "test_naming_a_canvas_to_the_master_is_not_the_master_having_read_it": lượt kế của cuộc gốc vẫn
    nhận ghi chú canvas mới đúng một lần, `artifact_rewrite` của master vẫn bị từ chối,
    "test_the_count_of_the_rest_says_how_many_and_which_tool_lists_them": câu đếm nêu số và tool
    `artifact_list` có thật, và không đọc nhầm thành một dòng canvas,
    và `canvas_lines` gọi thẳng: cuộc không ai viết, mười hai dòng đầu rồi câu đếm phần còn lại,
    bản người lưu và bản ghi ở cuộc khác không được nêu);
    `tests/test_delegate_outcome.py`
    ("test_the_blank_line_is_there_whether_or_not_a_canvas_was_written",
    "test_a_wait_that_runs_out_names_the_canvases_written_so_far");
    `tests/test_tools_delegate.py::test_the_first_two_lines_are_the_ones_the_web_card_reads`
    (dòng ba là dòng trống khi con không viết canvas nào);
    `tests/test_delegation_contract.py::test_the_parent_is_told_what_the_canvas_lines_under_the_outcome_are`
  - vitest: `lib/delegate-result.test.ts`, mục "the canvases a delegate result names" (khối đọc
    tới dòng trống, dòng trống ngay dưới outcome là không canvas nào, kết quả cũ không có dòng
    trống hay không có dòng outcome đọc như trước, dòng chỉ có dấu cách không phải dòng trống,
    câu trả lời mở đầu bằng dòng giống thẻ, dòng giống thẻ ở dưới hay lẫn với chữ khác, thẻ không
    đúng dạng chuẩn, dòng dừng ở dấu cách sau thẻ là canvas không tiêu đề, quá 12 canvas, hết giờ
    chờ)
- **Hạn chờ duyệt đặt theo lịch và theo kênh Telegram; duyệt hết hạn là từ chối mà chưa có gì
  thay đổi**
  - pytest: `tests/test_approval_ttl.py` (lịch và khối `telegram` nhận số giây nguyên từ một phút
    tới nửa ngày; số trong ngoặc kép, bool, số lẻ và số ngoài khoảng bị từ chối kèm chỗ sai; khối
    `telegram` không có khoá đọc như trước và khoá mới không nới hai khoá bắt buộc; cuộc trò
    chuyện giữ và báo hạn của nó, cơ sở dữ liệu cũ có thêm cột rỗng; sửa lịch khác hay đổi
    `chat_id` qua API không làm mất hạn; danh sách khoá của lịch ở fake web khớp server; câu hết
    hạn giữ đoạn mở đầu của câu từ chối);
    `tests/test_approval_ttl_runs.py` (job hỏi thì chờ đúng hạn của lịch, câu hỏi sau khi khởi
    động lại vẫn chờ chừng ấy; cuộc mở từ Telegram chờ theo kênh, từ web thì theo cấu hình; con
    chép hạn của cha và cha chờ đúng chừng đó cộng biên, không có thì theo agent con, con được tìm
    lại giữ hạn lúc mở; cha thôi chờ khi hạn của con đã qua);
    `tests/test_api_agents_edit.py::test_a_saved_schedule_comes_back_in_the_shape_it_can_be_resent_in`
  - vitest: `components/agent-editor/schedules-section.test.tsx` ("keeps how long a row's
    approvals wait when another row is edited"); `components/agent-editor/channel-section.test.tsx`
    ("stays when the chat id changes", "comes back with the channel when it is turned off and on
    again"); `hooks/use-agent-draft.test.ts` (dòng server khai lại mang `approval_ttl_seconds`)
- **Tool không trả kết quả rỗng: `fetch_url` báo 202 và trang không còn chữ là lỗi, markdown rỗng
  của firecrawl vẫn rơi về tải trực tiếp; `shell_run` không in gì vẫn nói lệnh kết thúc ra sao**
  - pytest: `tests/test_tools_web.py::test_a_page_accepted_but_not_ready_is_an_error_not_an_empty_read`,
    `::test_a_page_with_no_readable_text_is_an_error`,
    `::test_a_script_page_with_a_title_still_reads_as_its_title`,
    `::test_a_blank_scrape_falls_back_to_the_page_itself`,
    `::test_a_blank_scrape_of_a_blank_page_is_an_error`;
    `tests/test_tools_shell.py::test_a_command_that_prints_nothing_still_says_how_it_ended`
- **Tải một lượt chạy về dạng JSON hay Markdown: đúng tin của run, agent con của nó, khoá được
  che, kết quả tool dài bị cắt**
  - pytest: `tests/test_trajectory.py` (mỗi run ghi cuộc trò chuyện đang ở tin nào khi nó bắt đầu
    và chỉ lấy tin của mình, run tiếp tục sau khi duyệt giữ mốc cũ, run có từ trước khi có mốc
    thì cắt theo giờ và lấy cả tin đúng giây kết thúc, hai run bắt đầu cùng giây được phân theo
    mốc tin, run không ghi gì vẫn giữ chỗ khi được lưu lại nên không nhận tin của run sau nó cùng
    giây, agent con đi theo còn con của cuộc khác trùng mã lời gọi thì không, chỉ con do chính
    run mở mới đi theo, hai run cùng gọi `call_0` mỗi run chỉ mang con của mình, lời gọi chưa có
    kết quả chỉ mang con mở trong lúc run chạy và do chính cuộc này giao, run không có cuộc trò
    chuyện vẫn xuất bản ghi và các bước, Markdown có mọi lời gọi tool kèm tham số và kết quả, kết
    quả dài bị cắt và nói dài bao nhiêu trừ khi xin bản đầy đủ, Markdown giữ tiêu đề và tóm tắt
    trên một dòng và đóng khối code bị bỏ dở trước tin sau còn khối tự đóng và code trong dòng
    thì giữ nguyên, tin đọc sau một ghi chú canvas mang ghi chú đó với bí mật đã che và Markdown
    đặt ghi chú trong khối code ngay trước tin, tin không có ghi chú thì không có trường này);
    `tests/test_trajectory_redact.py` (chỉ gom giá trị dài của biến có tên như
    bí mật, gom cả dạng gộp khoảng trắng, dạng JSON đã thoát và dạng có cả hai, bí mật chứa bí
    mật khác được che trọn, phần đầu bị cắt ở cuối chữ hay trước dấu `…` và phần đuôi ở đầu chữ
    đều được che, chữ chỉ trùng đầu hay đuôi bí mật mà không phải chỗ cắt thì để nguyên, dạng
    khoá quen thuộc được che dù không biết giá trị, chữ chỉ hơi giống khoá thì để nguyên; run
    không có là 404, hai dạng đến như tệp để lưu với `no-store`, bí mật trong môi trường và chuỗi
    dạng khoá được che ở cả hai dạng, bí mật nằm ở chỗ bị cắt vẫn được che trước khi cắt, bí mật
    bị bản ghi cắt ngắn ở tiêu đề, tóm tắt, output và tham số của bước, ở tên và giá trị tham số
    lời gọi hay trong tin của agent con đều được che ở cả hai dạng, bí mật có ngoặc kép hay gạch
    chéo ngược được che cả khi JSON đã thoát nó, không gì từ môi trường đi theo nếu tin không
    chứa nó, bản đầy đủ giữ nguyên kết quả dài)
  - vitest: `components/run-replay.test.tsx` ("offers the run as a JSON and a Markdown file to
    save, with a word to check before sharing", "offers no download while there is no run to
    download")
  - Playwright: `replay-smoke.spec.ts` "a run downloads as a JSON file and as a Markdown file from
    its own page" (bấm là tải chứ không điều hướng, tới đúng URL với đúng tên tệp; trình duyệt tự
    tải `a[download]` mà không qua route nào của spec, nên thân tệp và header do pytest giữ)
- **Tin gửi khi cuộc trò chuyện bận: tin thường xếp hàng rồi thành một lượt riêng, `/steer` và
  lệnh kit chèn vào lượt đang chạy, chờ duyệt vẫn từ chối, Stop trả lại chữ**
  - pytest: `tests/test_busy_queue.py` (tin gửi lúc lượt chạy chờ rồi có lượt riêng, còn lượt đang
    chạy đi tiếp như chưa có gì; các tin chờ cùng nhau thành một tin theo thứ tự, đường dẫn và lệnh
    không ai định nghĩa là tin thường; `/steer` trơn bị từ chối cả khi rảnh lẫn khi bận; tin quá
    trần bị từ chối và hàng giữ nguyên; tin gửi trước khi lượt kịp được đọc vẫn chờ, dù đi cửa
    nào; cuộc chờ duyệt từ chối tin mới; tin gửi ngay sau một quyết định chờ lượt nó tiếp tục; tin
    đã chờ qua một lần dừng duyệt được trả lời sau quyết định; quyết định thứ hai bị từ chối; lượt
    quét hết hạn bỏ qua yêu cầu mà một quyết định đang giữ);
    `tests/test_steer.py` (steer tới lượt đang chạy sau tool nó chờ, model nhận nó ngay sau kết quả
    tool, run có step `steer`; các steer gửi trong cùng một bước tới cùng nhau, một dòng trên
    timeline; steer gửi lúc câu trả lời đang stream được chính lượt đó trả lời; lệnh kit gửi khi
    bận được expand rồi chèn; lấy steer để nguyên tin thường và đếm lặp lại từ đầu);
    `tests/test_queue_store.py` (vị trí trong hàng và trần; đọc không lấy; chuyển vào một tin người
    dùng theo thứ tự, cùng một transaction với nhật ký; chỉ chuyển các dòng được nêu tên; ghi tin
    hỏng hay cuộc đã xoá thì dòng còn nguyên; dòng đã bị lấy thì không chuyển gì; chỉ lấy steer; lấy
    hết mà không ghi; cuộc chờ lâu nhất đứng đầu; xoá cuộc trò chuyện xoá hàng; hàng sống qua
    restart);
    `tests/test_queue_drain.py` (claim chỉ bị gỡ bởi token của chính nó và hết hạn sau thời gian
    chờ; tin còn chờ khi drain dừng được trả lời sau lần khởi động kế; khởi động drain mọi hàng trừ
    cuộc chờ duyệt và dọn hàng của cuộc đã xoá; claim không ai đọc hết hạn và tin sau nó được trả
    lời; chat Telegram nghe câu trả lời từ bot của nó và chờ khi chưa có bot; tin từ web vào chat
    Telegram được trả lời ở server; runner lỗi thì nhả cuộc trò chuyện; huỷ dừng lượt do hàng
    chạy, không đụng lượt người khác đang đọc);
    `tests/test_busy_queue_api.py` (event `queued` kèm vị trí, `queued` trong chi tiết cuộc trò
    chuyện và đọc hai lần không đổi; `/steer` trơn nhận 422, tin quá trần nhận 429 ở cả `/messages`
    lẫn `/api/inbound`, kèm câu lý do;
    `stop` trả lại chữ và làm rỗng hàng, 404 cho cuộc không có; relay nghe mình đã xếp hàng; quyết
    định thứ hai nhận 409; `stop` huỷ lượt do hàng chạy và để nguyên lượt web đang đọc; server khởi
    động thì trả lời tin đã chờ qua restart, còn server `--no-schedule` để tin ấy tới sau lượt kế);
    `tests/test_kit_commands.py::test_steer_text_renders_kit_commands_and_leaves_everything_else_alone`,
    `::test_inbound_expands_a_kit_command_before_the_turn` (lúc rảnh `/steer X` là tin `X`)
  - vitest: `state/thread-reducer.test.ts` nhóm "threadReducer queue and steer"
    ("loaded reads waiting from detail.queued, defaulting to empty",
    "opened clears waiting along with the rest of the thread",
    "queued adds a chip and drops the matching local bubble, but only on a text match",
    "queue_cleared empties waiting", "elsewhere sets a notice of that kind",
    "a steer event adds one user message and drops the oldest matching count of steer chips",
    "a steer count larger than the number of steer chips only drops the steer chips there are",
    "a queued event reaching the reducer directly is a no-op: the hook intercepts it first",
    "queue_failed sets an error notice without touching busy, streaming or items" — lỗi từ POST
    xếp hàng không đụng luồng đang chạy, chỉ để lại một thông báo và giữ chip nguyên tại chỗ);
    `hooks/use-thread.test.ts`
    ("goes a second POST instead of runTurn, and the running turn keeps working and can still be
    stopped", "aborts a queueing POST still in flight when the conversation is switched" — và request
    bị cắt không để lại thông báo nào ở hội thoại đang hiện, nhóm
    "send while the conversation is busy elsewhere (this tab thought it was idle)"
    "catches the queued event on the plain send path and turns the temp bubble into a chip", nhóm
    "send while busy hits the queue's own limits", và nhóm "Stop, redesigned: server first, then
    abort, chip text back in order"
    ("calls the server before aborting, returns the cleared texts in queue order and clears the
    chips", "shows no notice when Stop only had chips to clear and nothing was running",
    "says `elsewhere` on an external run the server could not cancel, and still clears the chips",
    "aborts locally once STOP_WAIT_MS elapses when the server hangs, driven by fake timers") — hạn
    chờ giả bằng fake timers, không chờ thật ba giây;
    `lib/steer-hint.test.ts` "steerHint" (bảng `/tmp/x`, `/Users/a/b`, lệnh lạ, `/steer`,
    `/steer x`, lệnh đã biết, chữ thường — cùng dạng regex với server);
    `components/queued-chips.test.tsx`
    ("renders nothing when there is nothing waiting",
    "carries the full text in the DOM even though the row itself is a single truncated line",
    "announces itself with aria-live so a chip appearing is read out without moving focus",
    "labels a follow-up chip and a steer chip differently for someone using a screen reader",
    "offers no button: a chip is confirmation only, nothing here can be cancelled");
    `components/components.test.tsx` nhóm "Composer"
    ("still sends on Enter while busy: the box is never locked, only Stop is offered beside it",
    "labels the send button by what a busy send will do: queue a plain message, steer a /steer
    one", "offers both Stop and send while busy with text typed, but only Stop once the box is
    empty", "hides Stop when the caller says the busy turn cannot be stopped from here",
    "prepends restored text to whatever is already in the box, then focuses it",
    "restores alone with no join when the box was empty" — hai test cuối `waitFor` việc focus
    dời sang ô soạn sau khi `restore` đổi `nonce`);
    `lib/run-steer-step.test.ts` nhóm "a steer event on a live run"
    ("becomes a steer step, shortened exactly as the server shortens it",
    "cuts a long steer text at the same length the server cuts at") — cùng độ dài cắt với
    `note_text` phía server; nhóm "a queued event on a live run"
    "never reaches the activity stream, but a run read from a stale tab is not thrown"; nhóm
    "a steer step in the timeline"
    ("is labelled with its own sentence and painted done",
    "never merges with the steer step beside it: two turns of steering differ even when they read
    alike", "is left out of the progress counter, like a note: it is what a person said, not a
    piece of work");
    `hooks/use-external-run-refresh.test.ts` nhóm "a run first seen running while a drain's chip is
    still on screen"
    ("reloads the thread right away instead of waiting for the run to change status",
    "does not reload when there is no chip waiting: a plain external run keeps its old, quieter
    behaviour",
    "reloads even when the run is first seen already finished: an echo reply or a turn halted on
    budget never renders as running at all",
    "reloads when the run is first seen halted: the same instant turn can also stop on its own
    budget cap",
    "does not reload while the stream is behind: the reload on catching up already covers it")
  - Playwright: `queue.spec.ts`
    ("a plain message queues as a chip, clears the box, and leaves Stop and send both showing",
    "a /steer message queues as a chip that will cut in, then becomes a user message once the held
    turn steers it",
    "Stop hands both queued texts back to the box in order and the chips go",
    "a reload still shows the chip: the conversation's own queued field carries it",
    "chips wrap instead of forcing the page wider, and Stop and send stay tappable")
- **`send` báo kết quả ngay khi server nói gì đó: tin server giữ trong hàng không quay về ô soạn
  tin, tin server không nhận thì chữ ở lại nơi người gõ**
  - vitest: `app-queued-send.test.tsx` nhóm "a message sent while this tab thought the conversation
    idle" ("stays out of the box once the server queued it: the chip stands for it" — tab không
    thấy lượt đang chạy ở tab khác nên gửi theo đường rảnh và chỉ nhận một event `queued`: chip
    đứng thay tin, ô soạn tin trống, không có bong bóng thứ hai; "stays out of the box too when it
    is the first message of a new conversation, and the server queued it" — lượt ở tab khác chiếm
    cuộc trò chuyện mới trước khi tin đầu tới: chip cũng đứng thay tin và ô soạn tin trống; "takes
    its bubble back and leaves the words in the box when the server refuses it before saying
    anything" — 429 trước event đầu:
    bong bóng tạm biến mất, chữ ở lại ô và thông báo giữ câu của server; "hands the first message
    of a new conversation back to the box when it cannot be sent" — cuộc trò chuyện mới đã tạo,
    chữ về ô của nó);
    `hooks/use-thread.test.ts` nhóm "send settles at the first thing the server says"
    ("answers sent at the first event while the turn goes on", bảng "%s before any event takes the
    bubble back and reports the send as failed" cho hàng đầy, chờ duyệt, server hỏng, hội thoại
    mất và mất kết nối, "keeps the bubble and its error once the server has said anything: the
    text is not given back", "answers sent, not failed, when the person leaves before the server
    says anything" — rời đi hay bấm Stop không phải lỗi nên không trả chữ về ô của hội thoại khác,
    "answers sent when the stream ends with nothing to say: the server took the message",
    "has nowhere to send without a conversation"); nhóm "send while busy hits the queue's own
    limits" ("a %d from the queueing POST shows the server's own text in the notice and fails the
    send in our words" — thông báo giữ câu của server, `error` là câu của ta) và ba test xếp hàng
    cũ nay kiểm cả kết quả (`queued`, `sent`, `queued`);
    `hooks/use-thread-send.test.ts` nhóm "a message queued behind this tab's own turn" ("is held
    among the queueing requests only while its request is in flight" — request xếp hàng nằm trong
    tập để rời hội thoại thì cắt được, và rời tập khi xong; "answers sent when its request closes
    having said nothing: the server took the message"; "says nothing of a request it was cut off
    from: the person left, nothing was refused" — bị cắt vì người rời đi thì không báo lỗi và không
    đặt thông báo), nhóm "a message sent on this tab's own stream that the server queues instead"
    ("is turned into its chip by the send itself: the turn's stream is handed no queued event" —
    đường gửi thường tự đổi bong bóng tạm thành chip, luồng của lượt không nhận event `queued` lần
    hai; "hands every other event on to the turn's stream") và nhóm "a message queued behind this
    tab's own turn that the server refuses"
    ("is worded as any refused message is: a validation dump never reaches the notice" — tin xếp
    hàng sau lượt đang chạy ở tab này mà server từ chối bằng danh sách lỗi kiểm tra dữ liệu, như
    tin dài quá 20000 ký tự, thì thông báo nói câu của ta giống đường gửi thường, không in nguyên
    danh sách JSON);
    `state/thread-reducer.test.ts` "user_unsent takes back the local bubble for that text, and
    only that one" (chỉ bong bóng `local-` cuối cùng đúng chữ; tin server đã lưu hay có thứ gì
    đứng sau thì ở lại);
    `lib/send-result.test.ts` nhóm "settlement" (chốt một lần, ở việc đến trước trong ba: nghe
    event, lỗi, kết thúc; `queued` chỉ cho event `queued`) và "sendErrorText" (đổi trạng thái
    thành câu tiếng Việt của ta, kể cả khi server trả câu tiếng Anh)
- **Lượt Telegram chạy nền: chat được đọc trong lúc lượt chạy**
  - pytest: `tests/test_telegram_background.py` (`/status` trả lời giữa lượt, tin thứ hai xếp
    hàng không kèm "đang gõ…" rồi được trả lời riêng, `/new` bị từ chối khi đang chạy; `/steer`
    tới lượt đang chạy, `/steer` trơn bị từ chối và không vào hàng; lượt qua nửa đêm giữ cuộc trò
    chuyện; dừng bot chờ lượt xong trong hạn, quá hạn thì huỷ và báo một lần; lượt hỏng chỉ nêu tên
    loại lỗi; Telegram từ chối cả câu báo lượt hỏng thì lượt vẫn kết thúc, không lỗi nào thoát ra
    và log ghi một lần kèm nguyên nhân; bot trả lời tin chờ từ lúc start tới lúc stop; "đang gõ…" treo không giữ câu trả
    lời; `/approve` tìm cuộc chờ duyệt nằm sau cuộc mới hơn, gửi hai lần chỉ tiếp tục một lần);
    `tests/test_queue_drain.py::test_a_telegram_chat_hears_its_answer_from_its_bot_and_waits_while_there_is_none`
    (claim của drain giữ cuộc trò chuyện tới khi run nhận);
    `tests/test_telegram_drain_wiring.py` (runtime giao drain cho bot dựng lúc khởi động và cho
    bot dựng lại khi đổi kết nối, nên tin chờ trong chat được bot đang chạy trả lời); các test
    Telegram cũ gửi từng tin một bằng `poll_each` (`tests/telegram_fake.py`)
- **Lời gọi tool bị bỏ dở được đóng trước tin mới, không bao giờ chạy lại mà không ai hỏi**
  - pytest: `tests/test_interrupted_calls.py` (call không có kết quả nhận kết quả thay thế nằm
    trước tin mới và không chạy; call đã duyệt mà chưa báo lại không chạy lần nữa; call bị từ chối
    hay hết hạn đóng bằng lời từ chối của nó; câu hỏi đóng bằng câu trả lời hoặc mặc định; call còn
    chờ duyệt để nguyên; không làm gì khi mọi call đã có kết quả);
    `tests/test_queue_drain.py::test_what_waited_through_a_restart_comes_after_the_calls_it_cut_short`
- **Voice note Telegram được chép lời bằng tuyến riêng, "Đã nghe" trước khi vào lượt, không bao
  giờ đọc như lệnh slash hay `/steer`**
  - pytest: `tests/test_telegram_voice.py` (`find_voice` đọc voice note và audio file, bỏ qua ảnh
    hay message trống; voice hợp lệ được chép, "Đã nghe: …" gửi trước, rồi lượt tới master mang
    cả đường dẫn tệp lẫn lời chép; chưa cấu hình `audio_routes` thì báo cách bật, không tải về;
    quá 300 giây hay định dạng không nhận ra bị từ chối trước khi tải; quá 10 MB chỉ lộ ra sau
    khi tải thì vẫn bị chặn trước lúc chép lời; tải hỏng báo lỗi và không mở cuộc trò chuyện nào;
    tuyến chép lời lỗi báo bằng lý do cố định, không lộ lỗi gốc của provider; lời chép trống hay
    "không nghe rõ" vẫn tính tiền vào sổ chi phí; chép lời hết giờ báo timeout và không mở lượt;
    voice tới lúc agent đang bận thì xếp hàng, không bao giờ chen ngang thành `/steer`; hai voice
    trong một nhóm mỗi cái có lượt chép và lượt riêng của nó; message vừa có voice vừa có document
    thì đi theo đường voice; tuyến audio đọc thẳng từ deps của kênh, thêm route sau khi khởi động
    vẫn có tác dụng ngay); `tests/test_side_calls.py` ghi nhận purpose `transcribe` trong
    `PURPOSES`
  - vitest: `components/connections-panel.test.tsx`
    ("shows the providers that were built and the routes in order" — cũng khẳng định
    `noAudioRoutes` hiện khi chưa cấu hình, "lists the audio route used for voice note
    transcription"); `components/stats-panel.test.tsx`
    "names a voice note transcription row by its own purpose"; `components/global-routes-editor.test.tsx`,
    `test/fake-backend.ts`, `e2e/mock-api.ts` mang trường `audio_routes` trong mọi fixture
    `ConnectionsInfo` để không mock nào lệch kiểu thật
- **"Sửa và gửi lại từ đây": rẽ nhánh hội thoại ở một tin user đã lưu, giữ gốc nguyên vẹn**
  - pytest: `tests/test_store_fork.py`
    (`test_copies_every_message_before_the_cut_with_its_columns`,
    `test_cutting_at_the_first_user_message_makes_an_empty_fork_with_the_right_draft`,
    `test_tool_calls_and_tool_messages_survive_the_copy`,
    `test_provider_cost_and_token_columns_are_null_on_the_copy`,
    `test_the_fork_has_zero_spend_and_zero_unknown_cost_calls`,
    `test_usage_totals_are_identical_before_and_after_forking` (`by_model`, `by_purpose`, `by_day`
    và `/api/stats` không đổi vì bản chép không mang `provider`, nên không lượt gọi model nào bị
    đếm hai lần), `test_agent_id_cost_cap_and_skills_are_copied_others_are_reset`,
    `test_autonomous_follows_the_agent_default_not_the_source` (nhánh không thừa hưởng
    `autonomous` hay `auto_approve` của gốc dù gốc đã bật),
    `test_the_suffix_is_added_once_and_not_doubled_on_a_fork_of_a_fork`,
    `test_a_default_titled_source_stays_default_on_the_fork`,
    `test_cutting_at_an_assistant_or_tool_message_is_a_value_error`,
    `test_a_message_of_another_conversation_is_a_key_error`,
    `test_an_unknown_message_id_is_a_key_error`, `test_an_unknown_conversation_is_a_key_error`,
    `test_a_delegated_child_conversation_cannot_be_forked`,
    `test_the_source_conversation_is_unchanged_after_forking`,
    `test_a_pending_approval_on_the_source_survives_forking_at_an_earlier_point`,
    `test_forking_a_telegram_conversation_makes_a_web_fork_and_keeps_the_channel`,
    `test_an_open_call_is_copied_still_open_ready_for_the_route_to_close_it` (lịch sử thật
    `[assistant(A,B), tool(A), user]` khi một lượt bị ngắt giữa chừng rồi người nhắn tiếp; call B
    còn mở sau khi chép, chờ route đóng lại),
    `test_a_failed_copy_leaves_no_fork_behind` (chép tin hay chép liên kết canvas lỗi đều không
    để lại nhánh hay hàng nào),
    `test_only_the_source_conversations_own_messages_are_copied` (tin của hội thoại khác có
    `seq` nhỏ hơn điểm cắt không lọt vào nhánh),
    `test_forked_from_marks_the_conversation_so_the_recap_can_be_skipped`,
    `test_deleting_the_source_clears_forked_from_and_the_fork_keeps_its_messages`,
    `test_deleting_the_fork_does_not_touch_the_sources_delegate_children`,
    `test_a_shared_line_finds_a_single_hit_belonging_to_the_fork` (chỉ mục FTS của tính năng tìm hội thoại gộp
    phần chữ chung của gốc và nhánh về một hit, thuộc về nhánh vì `id` lớn hơn));
    `tests/test_api_fork.py`
    (`test_forking_returns_the_new_conversation_and_the_cut_messages_own_text`,
    `test_unknown_conversation_is_404`, `test_unknown_message_id_is_404`,
    `test_a_message_belonging_to_another_conversation_is_404`,
    `test_cutting_at_a_non_user_message_is_400`, `test_forking_a_delegated_child_is_400`,
    `test_before_message_id_must_be_a_positive_integer`,
    `test_an_open_call_is_closed_and_never_run_again` (chạy một lượt ở nhánh với tool đếm số lần
    gọi: tool bị đóng ở điểm cắt không được gọi lại),
    `test_a_refusal_that_fails_to_write_leaves_no_fork_behind` (`refuse_unanswered` ném lỗi thì
    route trả 500 và không còn nhánh),
    `test_the_fork_runs_on_its_own_only_when_the_agent_default_says_so` (cả hai giá trị của
    `autonomous_default`, gốc luôn mang giá trị ngược lại));
    `tests/test_memory_session_summary.py::test_a_fork_is_not_told_about_the_conversation_it_was_cut_from`
    (hội thoại liền trước nhánh thường là chính gốc của nó; tóm tắt của gốc kể phần sau điểm cắt
    mà nhánh sinh ra để bỏ, nên không vào prompt của nhánh)
  - vitest: `hooks/use-fork.test.ts`
    ("uses a numeric id straight away, with no extra read of the conversation",
    "resolves a local-N id by reading the conversation once and counting from the end" (bubble vừa
    gửi chưa nạp lại nên còn giữ id `local-N`; khớp theo vị trí tin user tính từ cuối và đúng
    chữ của nó),
    "gives up without ever calling the fork API when the text at that position no longer matches",
    "saves the fork's draft, refreshes the list, and selects the fork",
    "shows forkFailed and stays put when the server refuses the fork",
    "only on the conversation it failed in, and not again on the way back to it",
    "never, when it fails after the person has already moved to another conversation" — lỗi rẽ
    nhánh chỉ hiện ở đúng cuộc trò chuyện vừa lỗi, không theo người sang cuộc khác);
    `app-fork.test.tsx` (cả app trên `FakeBackend`: "opens the branch with the old words ready to
    edit, and links back to an untouched source" — ô soạn tin mang chữ cũ và có focus, nhánh được
    chọn trong sidebar, dòng "Rẽ nhánh từ" dẫn về gốc còn đủ bốn tin và gốc không có dòng đó;
    "reports a refused fork on its own conversation only");
    `components/message-thread.test.tsx`
    ("sits under the user bubble but not under the assistant's reply",
    "is absent without an onFork handler, even while idle", "is hidden while the thread is busy",
    "calls onFork with the item it sits under, not the conversation as a whole");
    `components/conversation-header.test.tsx`
    ("is absent when the conversation is not a fork",
    "is absent when the conversation carries no forked_from field at all",
    "names the source conversation and opens it on click",
    "falls back to the generic label when the source is not in the loaded list");
    `hooks/use-draft.test.ts`
    ("is read back by useDraft once it mounts on that key",
    "is picked up by a useDraft already mounted, the moment its key switches to it",
    "forgetDraft still empties what saveDraft wrote")
  - Playwright: `e2e/fork.spec.ts`
    ("forking at the second saved message keeps the first turn, prefills the composer, and links
    back" — gốc không có dòng "Rẽ nhánh từ" cả trước khi rẽ lẫn lúc quay về, "forking right after sending, before any reload, still resolves to the real message" —
    ca `local-N` trên mock, riêng với self-test thủ công trên server thật)
- **Tìm hội thoại FTS5: gõ không dấu khớp có dấu, `conversation_search` cho model, "Trong nội
  dung" trong sidebar cho người**
  - pytest: `tests/test_search_index.py` (thiếu module fts5 báo lỗi rõ; tin `user`/`assistant`
    vào chỉ mục ngay, tin `tool` thì không; xoá cuộc trò chuyện dọn đúng theo nó; backfill lập
    chỉ mục cho tin ghi trước khi có bảng; mở lại một CSDL hai lần không nhân đôi chỉ mục;
    backfill lỗi giữa chừng không để lại bảng hay trigger mồ côi, lần chạy sau thành công; không
    có chỗ nào `UPDATE messages` — chỉ mục chỉ có trigger insert/delete);
    `tests/test_conversation_search.py` (gõ "doc" khớp "đọc"; dấu nặng tiếng Nhật không bị bỏ
    như dấu tiếng Việt; dạng NFD vẫn tìm được và đoạn trích giữ nguyên ký tự gốc; đoạn trích chỉ
    đánh dấu đầu/cuối thật sự bị cắt; ký tự đặc biệt của FTS5 không làm câu truy vấn vỡ; nội dung
    trùng ở nhiều cuộc trò chuyện của cùng một agent gộp về bản mới nhất, khác agent thì giữ cả
    hai; một cuộc trò chuyện không góp quá ba kết quả; `limit` chặn tổng số; `since` lọc theo
    ngày; `agent_ids` lọc đúng các agent được nêu; `exclude_conversation` bỏ đúng cuộc đang chạy
    khỏi kết quả);
    `tests/test_conversation_search_api.py` (kết quả trả về 200 dù `conversation_id` không có
    thật, không phải 404 của route cuộc trò chuyện; `agent_id` thu hẹp về đúng một agent; agent
    không tồn tại trả kết quả rỗng, không lỗi; câu rỗng cũng vậy; `limit` dưới 1 hay trên 50 là
    422; không truyền `agent_id` thì tìm khắp cả đội vì người gọi route là chủ của cả đội)
  - vitest: `hooks/use-content-search.test.ts`
    ("waits 250ms of no typing before calling the API, and skips a call the next keystroke
    cancels", "never calls the API for a query under 2 characters, and clears any earlier
    hits", "aborts the in-flight request when the query changes again before it answers",
    "reports a real failure as an error, but a cancelled request as no error at all",
    "does not call the API at all while disabled, even for a long query", "retries the same
    query immediately, without waiting out another debounce window");
    `components/content-hits.test.tsx`
    ("shows a loading state while the search is in flight", "shows an error state, distinct
    from an empty result, with a retry button", "shows nothing at all once settled with no
    hits, not an error", "names each row's agent with a badge, and gives the button an
    accessible name naming the conversation", "shows when each hit happened, relative to now",
    "calls onSelect with the hit's conversation_id, not its message_id, when clicked");
    `components/conversation-list.test.tsx`
    ("shows a 'Trong nội dung' section once the debounced content search answers", "never
    calls the content search API without an agentName", "keeps the row list's own 'no
    matches' message off when a title misses but content still hits")
- **Agent đề xuất lịch chạy qua `schedule_create`, người duyệt nguyên văn prompt**
  - pytest: `tests/test_cron_next_after.py` (`next_after` nhảy so với một bản quét từng phút viết
    riêng trong test, trên khoảng 30 biểu thức cron × 9 mốc bắt đầu; không có lần chạy nào trong 366
    ngày trả `None`; ngày-trong-tháng và thứ vẫn là AND qua một ca 29/2 rơi vào thứ Hai; kết quả
    luôn sau mốc bắt đầu kể cả khi mốc đó đã tròn phút); `tests/test_schedule_words.py` (đọc lịch
    bằng lời y hệt từng ca của `lib/cron-text.test.ts`: hằng ngày, một khoảng thứ, cuối tuần, một
    danh sách thứ, ngày-trong-tháng, mỗi phút/giờ và bước `*/N` chia hết chu kỳ; một dạng không nằm
    trong các ca trên, kể cả bước không chia hết giờ hay ngày, trả về nguyên văn cron hoặc `every`);
    `tests/test_schedule_proposal.py::TestRejections` (mỗi phút, mỗi 5 phút, cron không có lần chạy
    trong hạn, `every` dưới 15 phút hay dài hơn 366 ngày, một `every` khổng lồ bị từ chối bằng lời
    thay vì tràn `timedelta`, `every` sai dạng báo lỗi bằng tiếng Việt, thiếu hoặc thừa cả `cron`
    lẫn `every`, cron sai hay dài quá 100 ký tự, tên hoặc prompt rỗng hay quá dài, `skills` không
    phải danh sách, skill không có thật đều bị từ chối); `::TestAcceptance` (`*/15`, cron hằng ngày,
    `every 15m`, `every 30d`, cron hằng năm đều được chấp nhận; một tên skill đứng riêng là một
    skill chứ không phải từng chữ cái; skill lặp chỉ giữ một, đúng thứ tự; đúng bằng từng giới hạn —
    cron dài đúng 100 ký tự, `every 366d`, tên 60 và prompt 2000 ký tự — vẫn được chấp nhận);
    `::TestUpcoming` (ba lần chạy kế tiếp của cron, dừng sau một lần khi lần đầu đã xa hơn hạn,
    `every` là `now + k`×chu kỳ); `::TestReasonLine` (`reason_line` là đúng từng dòng: tên, lịch
    bằng lời, ba lần chạy, nguyên văn prompt, lời cảnh báo; thẻ `every` ghi giờ là "khoảng", thẻ
    cron thì không; cron dài nhất hợp lệ vẫn chỉ liệt kê ba lần chạy; đề xuất sai có reason đúng
    bằng lời báo lỗi; không bao giờ rỗng và không vượt trần ký tự Telegram dù là cron hằng năm);
    `test_min_gap_minutes_documented_cases` và
    `test_min_gap_minutes_is_a_lower_bound_that_only_under_rejects` (khoảng cách hai lần chạy liền
    nhau của cron là cận dưới, chỉ có thể từ chối thừa);
    `tests/test_schedule_create.py::TestAlwaysAsks` (`ask_reason` không bao giờ rỗng cho tool này;
    `needs_decision` vẫn đúng dù cuộc trò chuyện `autonomous`, dù tool nằm trong `auto_approve`; một
    lượt không người trông vẫn dừng dù mọi cổng khác đã cho qua; đề xuất sai dạng có reason đúng
    bằng lời báo lỗi, không phải tên tool trơ trọi; những tham số từng làm đổ thẻ — `skills` là số,
    `every` khổng lồ, tên rỗng — vẫn dừng chờ người kèm reason; một tool trả reason rỗng hoặc lỗi
    khi dựng reason (lỗi số học hay lỗi tra khoá) vẫn dừng chờ người, không đổ lượt; reason không bị
    bọc bởi câu dành cho lệnh shell); `::TestUnattendedProposalExpires` (job prompt tự đề xuất lịch
    mà không ai duyệt thì approval hết hạn và không để lại dòng DB); `::TestApprovalToRun` (duyệt
    xong có dòng, `describe()` hiện `origin=chat`, đồng hồ giả tiến tới hạn thì `run_job` chạy mà
    không cần khởi động lại `Scheduler`, `jobs()` cũng có job đó; một `Scheduler` mới trên cùng CSDL
    vẫn thấy dòng đó; tạm dừng qua `job_state` khiến `due` không chọn job chat);
    `::TestDenialAndLimits` (từ chối thì không có dòng, vượt trần 20 thì lỗi, hai lần `add` chạy đua
    ở biên trần chỉ một cái qua; trần và số đếm tính riêng từng agent; bị từ chối ở trần không để
    transaction treo, CSDL vẫn ghi tiếp được; các dòng trả về đúng thứ tự thêm dù cùng một giây;
    agent đã đủ trần thì thẻ duyệt báo ngay điều đó mà vẫn dừng chờ người, và trần đã đủ của agent
    khác không tính; thiếu một lịch mới tới trần vẫn ra thẻ đầy đủ; tool báo đủ trần bằng lời và
    không lưu gì); `::TestOwnershipAndSkills` (tool không có tham số `agent`, dòng luôn mang
    `agent_id` của người gọi; skill không có bị từ chối; skill bị xoá sau khi lịch đã tạo không chặn
    job chạy, dòng chat thành job prompt mang đúng tên, cron, prompt; `run` lưu dòng dưới `agent_id`
    của người gọi — tham số `agent` lạc bị bỏ qua — đúng cuộc trò chuyện của lượt, đúng skill, và
    trả lời kèm lần chạy kế tiếp); `::TestAssembly` (agent nào cũng có tool này, gắn đúng id và danh
    sách skill của chính agent đó); `::TestOrphanRowsAndConcurrentDescribe` (dòng của agent đã bị gỡ
    không xuất hiện trong `describe()`; gọi `describe()` từ thread pool trong lúc luồng khác
    `add`/`remove` không lỗi và cho kết quả nhất quán); `::TestDeleteRoute` (xoá bỏ đúng dòng
    `created_schedules` và `job_state`, giữ nguyên lịch sử run; id không có hay id của agent khác
    báo không xoá gì; qua HTTP trả 204 và xoá luôn trạng thái tạm dừng của job, 409 cho job
    `origin=profile`, 404 khi không có; xoá được cả dòng mồ côi); `::TestTelegramCardLength` (thẻ
    duyệt Telegram mang nguyên văn prompt và không vượt 4096 ký tự kể cả ở ca prompt dài nhất với
    cron hằng năm); `test_existing_shell_ask_pattern_gate_is_unaffected` (cổng hỏi của lệnh shell
    hiện có không đổi kết quả sau khi thêm `ask_reason`)
  - vitest: `components/jobs-panel.test.tsx` ("labels a chat-origin row and leaves a profile row
    unlabelled", "offers no delete button for a profile job even when onDelete is supplied",
    "deletes a chat job once the confirm dialog is accepted", "keeps the job when the confirm dialog
    is declined", "offers no edit button on a chat job, whose schedule is not in the profile
    editor"); `app.test.tsx` ("withholds always-allow on a proposed schedule / a shell command
    on the ask list, which stopped for a reason, and shows that reason": thẻ có reason hiện đủ từng
    dòng reason, có nút Duyệt nhưng không có "Luôn cho phép"; thẻ không reason vẫn có nút đó, theo
    "always-allows a tool from the approval bar, shows it in the header and revokes it");
    `app-activity.test.tsx` ("deletes a chat-created job from the jobs tab and keeps the profile
    one": trên toàn app, nút xoá chỉ có ở job chat, bấm xác nhận thì gửi đúng một DELETE, dòng biến
    mất, job profile còn nguyên)
  - Playwright: `e2e/manage-smoke.spec.ts`
    "a schedule is added from the jobs list through the agent's editor" (không đổi assertion,
    chỉ sửa `e2e/mock-api.ts` để một spec giữ tham chiếu tới cùng mảng `jobs` nó truyền vào
    `mockApi` thấy được cả việc thêm bằng `push` lẫn việc xoá qua route DELETE mới)
- **Đọc lại đầu ra tool đã bị rút ngắn (`tool_output_read`), spill và dọn dẹp**
  - pytest: `tests/test_output_spill.py` (ghi và đọc tệp, trần 5 MB cắt đúng ranh giới ký tự
    nên tệp vẫn đọc được UTF-8, tên tệp băm từ id, id hội thoại lạ bị từ chối, quét không theo
    và không xoá symlink, sao chép bỏ qua symlink, `shape_with_spill`);
    `tests/test_registry_spill.py` (registry ghi tệp và nối dòng trỏ vừa trần, không ghi khi
    đầu ra ngắn, ghi lỗi thì vẫn trả kết quả, `tool_output_read` không tự spill dù trần rộng
    hay hẹp, trần quá hẹp cho dòng trỏ thì chỉ rút gọn, ghi chú của hook sau không đổi); `tests/test_tool_output_read.py` (đọc từng đoạn, nhãn nguồn, tệp thắng
    bản DB, hết thì báo, offset âm hoặc quá cuối bị kẹp vào văn bản, id của cuộc khác, id trùng
    bị từ chối, vừa trần registry);
    `tests/test_message_tool_results.py` (`MessageStore.tool_results`);
    `tests/test_output_read_wiring.py` (agent có hoặc không có tool trong `tools:` thì có hoặc
    không có spill, stub trong prompt nêu id đúng khi có tool, vòng lặp thật đọc lại đoạn giữa
    của đầu ra 22 000 ký tự); `tests/test_agent_context_trim.py`
    ("test_a_stub_names_the_id_to_reread_only_for_an_agent_that_can_reread",
    "test_rereading_changes_only_the_wording_of_the_stubs",
    "test_a_stub_for_a_call_with_no_id_falls_back_to_the_plain_wording");
    `tests/test_agent_templates.py` ("test_every_tool_a_template_lists_is_a_real_tool",
    "test_the_counsel_and_the_researcher_can_read_a_long_output_back");
    `tests/test_housekeeping.py` (quét ngay khi khởi động, quét lại mỗi chu kỳ, lần quét lỗi
    không giết vòng, huỷ được, lifespan chỉ quét khi `schedule=True`); `tests/test_api_fork.py`
    ("test_deleting_a_conversation_removes_its_spill_folder",
    "test_deleting_an_unknown_conversation_is_404_and_touches_no_spill_folder",
    "test_forking_copies_the_spill_files_to_the_fork",
    "test_a_failed_spill_copy_does_not_break_the_fork",
    "test_a_fork_still_reads_the_original_after_its_source_is_deleted_and_swept")
  - Behavior eval: `evals/` của home, một ca chạy lệnh in khoảng 24 000 ký tự rồi hỏi một giá
    trị ở giữa (kỳ vọng `tool_output_read`, tối đa một `shell_run`)
- **Id lời gọi tool không còn trùng hay bị dùng lại sai**
  - pytest: `tests/test_tool_call_ids.py` (id provider bỏ trống là uuid duy nhất);
    `tests/test_approval_id_reuse.py` (id dùng lại mà approval đã lưu ghi lời gọi khác thì bị
    từ chối, kể cả khi chỉ khác tên tool); `tests/test_delegate_child_scope.py` (agent con chỉ
    tìm được qua lời gọi của chính cha nó); `tests/test_tools_delegate.py`
    ("test_another_parents_child_with_the_same_call_id_is_not_reused")
- **Lỗi tạm thời của upstream được hỏi lại một lần trên cùng tuyến, chỉ khi chưa hiện chữ**
  - pytest: `tests/test_route_retry.py` (chunk lỗi `provider_unavailable` giữa stream được hỏi
    lại và trả lời, 503/429 và chunk lỗi mã 500/429 được thử lại, 402/400, chunk lỗi không mã
    hay mã 400 và stream hỏng không thử lại, lỗi kết nối được thử lại, đã hiện chữ thì không thử
    lại, hỏng lần hai thì rơi tuyến kế hoặc báo mọi tuyến hỏng, lần hỏi đã được phục vụ ghi sổ
    giá không rõ còn lần bị từ chối trước chunk đầu thì không, lượt chỉ giữ câu trả lời của lần
    hỏi lại và không phát `route_fallback`); `tests/test_provider_chain.py` (lỗi không tạm thời
    vẫn rơi tuyến ngay như trước)
- **Đối số của lời gọi tool đi ra từng mảnh ngay khi model gửi, trước câu trả lời trọn vẹn**
  - pytest: `tests/test_tool_call_ids.py`
    ("test_each_piece_of_arguments_comes_back_named_with_the_call_it_belongs_to": mỗi mảnh mang
    vị trí và tên đã ghép của lời gọi, lời gọi ghép ở cuối không đổi,
    "test_a_delta_that_brings_no_arguments_is_not_a_piece",
    "test_arguments_sent_ahead_of_the_name_come_back_with_no_name_yet",
    "test_pieces_of_two_calls_keep_their_own_index_and_name_in_the_order_they_came",
    "test_a_delta_that_states_no_index_is_a_piece_of_the_first_call");
    `tests/test_tool_call_position.py` (mỗi mảnh mang vị trí của lời gọi trong câu trả lời chứ
    không mang số provider gửi: stream đánh số từ 1, bỏ cách số hay cả hai vẫn cho vị trí 0 rồi
    1, trùng chỗ của lời gọi trong `calls()`; lời gọi giữ vị trí khi lời gọi sau mở ra; lời gọi
    mở trước một lời gọi mang số nhỏ hơn thì từ lúc lời gọi kia mở, mảnh của nó mang đúng chỗ
    theo thứ hạng của số, là chỗ nó đứng trong `calls()`, chứ không theo thứ tự tới; mảnh
    tới trước tên cũng được xếp như vậy; lời gọi mới chỉ có id và tên vẫn giữ chỗ của nó;
    stream ghi `"index": null` cho lời gọi duy nhất vẫn được vị trí 0;
    "test_the_piece_a_turn_shows_names_the_place_of_its_call_in_the_answer": qua cả một lượt
    với stream đánh số 1 và 2, event `tool_call_delta` mang `index` đúng bằng chỗ của lời gọi
    trong `tool_calls` của `assistant_message`);
    `tests/test_openrouter.py::test_each_fragment_of_a_tool_call_is_passed_on_as_it_arrives`
    (mảnh xen với chữ theo đúng thứ tự gửi, `Completion` cuối y như cũ) và
    "test_a_delta_that_brings_words_and_a_fragment_passes_both_on_the_words_first" (một delta
    mang cả chữ lẫn mảnh thì mảnh không bị bỏ và đi sau chữ);
    `tests/test_ollama.py::test_a_local_model_passes_on_the_pieces_of_a_tool_call_too`;
    `tests/test_route_retry.py`
    ("test_a_route_is_still_asked_again_after_part_of_a_tool_call_arrived",
    "test_a_tool_call_piece_does_not_use_up_the_retry_that_text_would": mảnh lời gọi không phải
    chữ đã hiện, nên tuyến vẫn được hỏi lại); `tests/test_provider_chain.py`
    ("test_scripted_provider_streams_each_tool_call_in_pieces_before_the_completion",
    "test_scripted_provider_streams_no_piece_for_an_answer_that_calls_nothing");
    `tests/test_echo_provider.py` (model giả phát mảnh 12 ký tự mang tên lời gọi, chữ có dấu
    không bị đổi thành mã escape, lượt chỉ gọi tool không còn mảnh chữ rỗng, `fake:slow` chờ
    giữa hai mảnh chữ hay hai mảnh lời gọi và không chờ quanh câu trả lời một mảnh, `fake:echo`
    không bao giờ chờ, mặc định chờ bằng `asyncio.sleep`)
- **Lời viết canvas hiện dần trên luồng của tab đang chờ khi model còn đang viết nó; đối số của
  tool khác không đi ra dưới dạng mảnh khi model còn đang viết chúng**
  - pytest: `tests/test_draft_preview.py` (chỉ `artifact_create` và `artifact_rewrite` được xem
    trước; mảnh đầu phát ngay dù đồng hồ đọc số nào; mảnh tới trong 3 giây được gom, mảnh tới
    đúng 3 giây sau event trước mang ra mọi thứ đã gom, và khoảng chờ tính lại từ event ấy; mảnh
    tới trước tên thì chờ tên rồi đi cùng; lời gọi mang tên tool khác, kể cả `artifact_import`,
    bị bỏ hẳn dù tên đổi về sau; hai lời gọi trong một câu trả lời được tính giờ và gom riêng;
    phần còn giữ khi lần thử kết thúc bị bỏ chứ không gửi; `reset` quên cả lời gọi đã bỏ; đồng hồ
    mặc định là `time.monotonic`); `tests/test_model_stream.py`
    ("test_a_canvas_write_is_shown_ahead_of_the_answer_that_carries_it"; phần còn giữ không được
    xả sau câu trả lời; bước gọi model đi theo đồng hồ được tiêm; `workspace_write` với đối số
    dài không cho event nào;
    "test_an_attempt_cut_off_mid_document_is_called_off_before_the_next_one_shows": tuyến bị cắt
    giữa chừng đối số cho một event tên rỗng mang `attempt=1`, rồi lần thử mới bắt đầu lại từ
    mảnh đầu và mọi event của nó mang `attempt=1`; lần thử chưa hiện gì thì không có event tên
    rỗng nhưng vẫn được đếm; tuyến hỏng hẳn vẫn cho `route_fallback` và cũng được đếm;
    "test_on_the_slow_model_a_document_of_a_few_kilobytes_is_seen_filling_in": trên `fake:slow`
    một tài liệu vài KB được phát nhiều lần chứ không phải một, và tổng thời gian model chờ
    cho cả tài liệu ấy dưới một phút);
    `tests/test_tool_call_delta_event.py` (event `tool_call_delta` chỉ có `type`, `index`, `name`,
    `chunk`, `attempt`; "test_the_activity_hub_neither_writes_nor_broadcasts_it";
    "test_it_leaves_a_run_exactly_as_it_was": `apply_event` không mở step và không đổi số nào;
    "test_a_reply_reads_the_same_with_the_pieces_in_the_chain_or_without_them": Telegram và job
    đọc cùng một câu trả lời; qua API nó là một khối SSE riêng đứng trước `assistant_message`,
    còn lượt gọi tool khác không có khối ấy)
- **Web giữ các mảnh ấy thành bản đang viết của lượt và đọc được đối số khi JSON chưa đóng; bản
  đang viết không sống quá lượt của nó, và không ở lại cho lời gọi hoá ra là tool khác**
  - vitest: `web/src/state/writing-previews.test.ts` (mảnh đầu mở một bản với khoá riêng, mảnh sau
    nối vào và đếm thêm một lần; hai lời gọi trong một câu trả lời tách nhau theo vị trí; event tên
    rỗng hay mảnh mang số lần thử khác, lớn hơn hay nhỏ hơn, bỏ mọi bản chưa có lời gọi, lần thử
    mới nhận khoá mới;
    event tên rỗng của chính lần thử ấy không đổi gì; `bindCalls` gắn bản với lời gọi đứng đúng vị
    trí khi cùng tên tool, bỏ bản mà lời gọi là tool khác, kể cả `artifact_rewrite` thay cho
    `artifact_create`, bỏ bản không có lời gọi ở vị trí ấy và bỏ bản của bước trước; bước sau mở
    bản mới bên cạnh bản đã gắn dù cùng vị trí và cùng số lần thử, vẫn nối tiếp vào bản của chính
    nó khi bản đã gắn được viết ở lần thử khác, và lần thử lại của bước sau không đụng tới bản đã
    gắn; "what the person put away, where the stream of a turn stops or starts": việc người đã
    cất một bản chỉ còn tính khi lượt đang chờ họ trả lời, không tự có ở nơi chưa ai cất gì, và
    qua một lần tải lại chỉ còn tính khi đúng yêu cầu đã chờ ấy vẫn chờ; lượt đã xong thì không
    còn bản nào và không còn gì đã cất);
    `web/src/state/thread-reducer-previews.test.ts` (luồng theo từng mảnh mà không đổi `thinking`
    hay chữ đang tới; `route_fallback` rồi event tên rỗng bỏ bản và giữ dòng báo đổi tuyến;
    `assistant_message` gắn lời gọi và bản ở lại qua `tool_call` lẫn `tool_result`;
    "drops a preview whose call turned out to be another tool, with all it had read of it": vị trí
    từng mang tên `artifact_create` mà lời gọi là `workspace_write` thì không còn bản nào; tám cách
    một lượt kết thúc, mỗi cách không để lại bản nào dù bản đã gắn hay chưa; lượt sau, cuộc khác
    và lần tải lại không dùng lại khoá cũ);
    `web/src/state/thread-reducer-put-away.test.ts` (luồng nhớ việc người đã cất một bản đang viết
    và không đổi gì khác, thẻ vẫn còn; dấu ấy ở lại qua mọi thứ lượt nói tiếp, kể cả khi model bắt
    đầu lại; "a canvas put away in a turn that then waits for the person": dấu còn khi yêu cầu
    duyệt đang chờ và stream đã đóng sau nó, còn khi người trả lời rồi lượt viết canvas khác, còn
    khi câu trả lời không gửi được, còn sau lần tải lại thấy đúng yêu cầu ấy; mất khi lần tải lại
    thấy yêu cầu đã đóng hay thấy một yêu cầu khác, khi người bấm dừng, và khi server báo lượt
    xong, bị chặn hay lỗi dù trang còn hiện yêu cầu; tám cách một lượt kết thúc đều xoá dấu, mở
    cuộc khác trong lúc đang chờ cũng vậy, và lượt bắt đầu sau đó không nợ gì dấu được đặt khi
    không có lượt nào chạy);
    `web/src/lib/partial-json-content.test.ts` (đọc `title`, `kind`, `id`, `content` ở tầng ngoài
    cùng của object chưa đóng: `content` có ngay khi chuỗi mở, ba khoá kia chỉ có khi chuỗi đóng;
    mọi escape của JSON cho đúng chữ `JSON.parse` cho; ký tự viết bằng hai escape đọc thành một ký
    tự, đúng ở cả hai đầu dải của mỗi nửa; escape bị cắt ở cuối thì bỏ lại chờ mảnh sau, kể cả nửa
    đầu của ký tự viết bằng hai escape; nửa ký tự không bao giờ đủ thành U+FFFD và đọc tiếp, kể cả
    khi chữ theo sau chỉ trông giống đuôi một escape mà không có dấu gạch chéo ngược mở đầu; escape
    sai không làm mất phần sau; giá trị không phải chữ bị bỏ qua dù bên trong có ngoặc, nháy hay
    khoá trùng tên; khoá lặp lấy lần cuối như server; khoá lạ, kể cả `__proto__` và `constructor`,
    không được đọc; thứ không mở bằng `{` thì không đọc gì dù theo sau là khoá và chữ; object hỏng
    chỉ đọc tới chỗ hỏng, và dấu khác đứng ở chỗ của `:` hay `,` cũng là chỗ hỏng; chuỗi một
    megabyte đọc trong một lượt);
    `web/src/lib/canvas-writing.test.ts` (tiêu đề đi qua đúng phép làm sạch của server, tiêu đề
    trống hay quá 200 ký tự thì không có; `kind` chỉ nhận tên một loại canvas, `constructor` và
    `toString` không phải; lời viết lại chỉ nêu canvas khi id đủ 12 ký tự hex, lấy tiêu đề và loại
    của canvas ấy, và không hỏi tab về id sai dạng; lời tạo mới không nêu canvas nào dù đối số
    mang id; kích thước tính theo byte UTF-8);
    `web/src/state/activity-reducer.test.ts` ("takes nothing from the pieces of a canvas being
    written: they are no step of the run")
- **Canvas agent còn đang viết hiện dần trên web: mỗi canvas một thẻ trong luồng, và một khung chỉ
  đọc ở chỗ của dock; khung tự hiện một lần ở nơi không cản ai, không lấy bàn phím, không ghi gì
  lên server hay vào bộ nhớ trình duyệt, và nhường chỗ cho canvas thật khi lời gọi xong**
  - vitest: `web/src/hooks/use-canvas-writing.test.tsx` (thẻ chỉ có cho bản chưa gắn lời gọi; mỗi
    mảnh được đọc một lần dù màn hình vẽ lại bao nhiêu lần và danh sách canvas của dock là object
    mới ở mỗi lần vẽ; tắt xem trước thì hết thẻ ngay, bật lại thì có lại, không chờ mảnh kế; canvas
    mới tự hiện từ mảnh thứ hai có
    chữ, không trên màn hẹp kể cả khi màn rộng ra sau, không khi người đang gõ trong một canvas kể
    cả khi họ ngừng, không cho lời gọi đã gắn, không thay bản đang hiện, và hai bản sẵn sàng cùng
    lúc thì hiện bản đầu; lời viết lại chỉ tự hiện trên chính canvas nó viết lại đang mở, và lời
    chưa nêu canvas nào thì không tự hiện dù dock đang giữ canvas, đang ở danh sách hay đang đóng;
    bấm xem thì hiện ngay từ mảnh đầu, trên màn hẹp và cả khi đang gõ, thay bản tự hiện, đếm số lần
    hỏi và không tự hiện lại về sau; "shows the one asked for in the very drawing that dropped the
    one on show": lời bấm xem tới đúng lần vẽ làm mất bản đang hiện thì bản được hỏi vẫn hiện; rời
    khung thì hook báo cho luồng đúng một lần và phần còn lại của lượt im, luồng quên thì bản kế
    lại tự hiện; "holds for a screen drawn anew in that turn, which has seen none of it: the thread
    remembers": màn chat dựng lại giữa lượt mà luồng còn nhớ thì bản mới chỉ là thẻ; mỗi lần cất
    một bản được bấm xem đều báo lại, còn khung tự đi thì không báo gì; khung
    tự đi khi model bắt đầu lại, khi dock chuyển chỗ và không quay lại khi dock trở về, khi tắt xem
    trước; nó ở lại suốt lời gọi, rồi mở lặng lẽ đúng một lần canvas mà kết quả nêu dù đối số nói
    gì; lời gọi hỏng, bị từ chối hay bị dừng, và kết quả không nêu canvas, chỉ cất khung; không mở
    đè lên chữ người vừa gõ trong canvas phía sau, nhưng vẫn mở khi bàn phím chỉ đang ở trong dock
    mà người không gõ gì ở đó, vì bàn phím ấy đang ở chính khung sắp nhường chỗ; canvas viết lại
    vốn đang mở thì không mở lại; lời gọi hỏng không làm im canvas sau);
    `web/src/components/canvas/canvas-writing-card.test.tsx` (thẻ nói đang viết hay viết lại dưới
    tiêu đề tới lúc này hoặc một chữ thay, ký tự ẩn trong tiêu đề hiện thành dấu, loại chỉ có khi
    đã biết, kích thước đã viết nằm ở dòng không bị đọc lên mỗi lần đổi và nêu đúng con số, ba
    chấm ẩn với trình đọc màn hình, nhãn của nút xem có tên canvas và nút hỏi đúng bản ấy, thẻ
    không hiện chữ đang viết);
    `web/src/components/canvas/canvas-writing-view.test.tsx` (đầu khung nêu tên và loại, nói chưa
    lưu khi agent còn viết và đang lưu khi lời gọi đã có, ở cùng một dòng `status` để trình đọc màn
    hình đọc lên lúc nó đổi; đầu khung chỉ có nút đóng, và bản không có link, ảnh hay khối mã thì
    cả khung chỉ có nút ấy, không ô gõ, không link;
    markdown đi qua cùng view của canvas đã lưu, HTML viết trong markdown hiện thành chữ; `html`,
    `svg`, `mermaid` hiện mã nguồn kèm dòng nói vì sao và không dựng phần tử nào; loại chưa biết,
    `code` và `image` là chữ thường; ký tự ẩn hiện thành dấu; bàn phím ở yên khi khung tự hiện,
    tới nút đóng khi người bấm xem, không bị kéo lại khi chữ tới thêm, quay lại khi bấm lần nữa,
    và không bị lấy khỏi link trong khung; khung theo dòng cuối cho tới khi người cuộn lên);
    `web/src/components/canvas/canvas-writing-view-offers.test.tsx` (bản markdown đang viết có
    đúng những thứ canvas đã lưu có trong phần chữ: link mở ở tab khác với `noopener noreferrer`,
    nút giữ ảnh của trang ngoài và nút "Sao chép mã", ngoài nút đóng; "draws that text exactly as a
    saved canvas draws it": phần chữ là đúng HTML mà view của canvas đã lưu vẽ ra; không có gì để
    gõ vào dù bản chứa gì; bản thuộc loại hiện mã nguồn, và bản markdown đã quá dài, chỉ có nút
    đóng vì link, ảnh và mã trong chúng là chữ; "is asked about again when a later piece lengthens
    the address the person agreed to": người đã đồng ý với `http://a.test/x`, mảnh sau nối địa chỉ
    thành `http://a.test/xy` thì ảnh không được tải và nút hỏi lại với địa chỉ mới; mảnh sau không
    đụng tới địa chỉ thì ảnh ở yên);
    `web/src/components/canvas/canvas-writing-view-long.test.tsx` (bản markdown dài 99 999 ký tự
    vẫn đọc như markdown; từ 100 000 ký tự trở lên, ở đúng ngưỡng, hơn một ký tự hay gấp mấy lần,
    khung hiện mã nguồn kèm một dòng nói vì sao và không kèm dòng của trang hay hình vẽ; ký tự ẩn
    trong bản dài vẫn hiện thành dấu; `code`, `image` và loại chưa biết dài cỡ ấy không có thêm
    dòng nào, vì chúng vốn là chữ thường; `html`, `svg`, `mermaid` giữ đúng một dòng như bản
    ngắn; "keeps its frame, its place to scroll and the keyboard on its close button": bản vượt
    ngưỡng trong lúc đang hiện thì khung, vùng cuộn và nút đóng vẫn là các phần tử cũ, bàn phím ở
    yên trên nút đóng; mảnh sau không đưa bản trở lại markdown và dòng báo không lặp);
    `web/src/components/canvas/canvas-dock-writing.test.tsx` (dock hiện khung trên tab canvas dù
    chưa mở gì và trả cột hoạt động lại sau đó; canvas dock đang giữ chờ phía sau cùng chữ người
    đã gõ; danh sách bị che; trên màn hẹp khung phủ lên chat với đường quay lại đứng đầu; đường
    quay lại, nút Canvas và nút đóng đều rời khung trước khi làm việc cũ; bàn phím ở yên trong ô
    chat khi khung tới và khi nó đi, về nút Canvas khi dock đóng lại, ở lại trong cột hoạt động,
    và tới control đầu của dock khi canvas thật thế chỗ khung; canvas thứ hai theo dòng cuối của
    chính nó); `web/src/lib/canvas-dock-state.test.ts` (dock đóng vẫn là đang hiện khi có khung);
    `web/src/components/message-thread-writing.test.tsx` (mỗi canvas một thẻ theo thứ tự bắt đầu,
    đứng sau chữ đang tới; thẻ thay dòng "đang nghĩ"; không thẻ ở màn không theo việc viết);
    `web/src/hooks/use-canvas-auto-open-writing.test.ts` (lời gọi mà dock đã hiện khi còn viết
    không được mở lần nữa ở hook tự mở, các canvas khác của lượt vẫn mở);
    `web/src/hooks/use-canvas-list-verify.test.ts` (`kindOf` lấy loại từ danh sách rồi từ lần đọc
    gần nhất)
  - vitest cấp App: `web/src/app-canvas-writing.test.tsx` (mảnh đầu chỉ là thẻ; từ mảnh thứ hai
    khung hiện cạnh luồng, ô chat giữ bàn phím; "gives way to the canvas the agent made, in the
    same column, having written nothing to the server": không request ghi nào tới `/artifacts`,
    không ghi canvas đang mở; tin gửi khi khung đang hiện không mang gì của nó; model bắt đầu lại
    thì khung đi ngay và bản sau dựng từ đầu; dừng lượt thì không còn gì; nút Canvas cất khung
    trước và phần còn lại của lượt im; Escape trên màn rộng không cất khung, vì ở đó khung không
    che chat; thẻ gọi khung lại; canvas thật vẫn tự mở sau khi cất;
    người đang gõ trong canvas khác thì khung không tự hiện, và bấm thẻ lưu chữ của họ như mọi lần
    rời ô soạn: đúng một `PUT` mang chữ của họ; lưu được thì canvas của agent mở khi xong, lưu
    hỏng thì canvas của họ trở lại cùng chữ đã gõ);
    `web/src/app-canvas-writing-put-away.test.tsx` (người cất khung, lượt dừng lại hỏi duyệt một
    lời ghi tệp, người duyệt, rồi canvas kế của lượt ấy chỉ là thẻ và thẻ vẫn gọi được khung;
    không cất gì thì canvas kế tự hiện như trước; người cất khung, sang Quản lý rồi quay lại chat
    giữa lượt: bản ấy vẫn là thẻ ở lúc quay lại và ở mọi mảnh sau, còn không cất thì nó hiện lại;
    lượt xong hay bị người dừng thì canvas của lượt sau lại tự hiện);
    `web/src/app-canvas-writing-safety.test.tsx` (lời viết lại hiện trên canvas nó viết lại, canvas
    ấy chờ phía sau rồi hiện lại; bấm thẻ của chính canvas ấy trong luồng thì khung được cất và
    canvas dock đang giữ hiện lại; canvas khác đang mở hay không mở gì thì chỉ là thẻ; id trong bản
    đang viết không vào request nào; bộ nhớ trình duyệt giữ chữ người gõ cho canvas ấy và không có
    chữ nào của agent; bản hoá ra là tool khác bị gỡ, đối số của nó không ở lại trong dock; trang
    `html` hiện mã nguồn và không gì trong nó chạy; markdown vẽ như canvas đã lưu; loại lạ là chữ;
    tiêu đề theo đúng giới hạn của canvas đã lưu);
    `web/src/app-canvas-writing-narrow.test.tsx` (màn hẹp chỉ có thẻ; bấm xem thì khung phủ chat
    và bàn phím ở nút đóng; Escape hoặc đường quay lại trả chat, bàn phím về nút Canvas; Escape
    rời khung trước rồi mới cất canvas dock đang giữ; canvas thật phủ chat khi người đang xem, và
    không phủ khi họ không xem);
    `web/src/app-canvas-writing-keyboard.test.tsx` (luật tự hiện hỏi `typing()` của dock chứ không
    hỏi `editing()`: bàn phím ở một nút của canvas đang mở, ở một tab của cột, trong danh sách
    canvas hay trong cột hoạt động khi chưa mở gì, không gõ chữ nào, thì bản đang viết vẫn chỉ là
    thẻ, bàn phím ở yên và không có `PUT` nào; bàn phím về ô chat rồi thì bản ấy vẫn không tự
    hiện, thẻ vẫn gọi được khung; bàn phím ở ô chat và canvas đang mở không có chữ gõ dở thì
    khung hiện đè lên như trước; màn 1000 px nới ra 1440 px khi bàn phím còn ở canvas vừa phủ
    chat thì mảnh kế không làm khung hiện, còn bàn phím ở ô chat thì khung hiện ở mảnh kế);
    `web/src/app-canvas-writing-handover.test.tsx` (lúc lời gọi xong, khung nhường chỗ theo
    `editing()` chứ không theo `typing()`, và mỗi lần dock được bảo mở đều được đếm qua một lớp
    bọc quanh `useCanvasDock` thật: màn rộng, canvas của agent được mở đúng một lần, lặng lẽ, bởi
    hook đã hiện nó, và hook tự mở không mở lại ở lúc ấy hay ở phần còn lại của lượt; bàn phím ở
    nút đóng của khung hay ở một tab của cột thì canvas vẫn mở; chữ người gõ mà lần lưu bị từ
    chối thì không gì mở canvas của agent, kể cả sau khi lần lưu lại thành công và bàn phím đã về
    ô chat; màn hẹp, người đang xem thì canvas mở đúng một lần phủ chat và bàn phím tới đường
    quay lại, người chỉ có thẻ thì không gì được mở, và chữ chưa lưu được thì canvas của họ vẫn
    phủ chat cùng chữ ấy)
  - e2e: `web/e2e/canvas-writing.spec.ts` (màn rộng: khung hiện dần cạnh luồng, ô chat giữ bàn
    phím, rồi canvas thật thế chỗ; trang `html` là mã nguồn và `window.pwned` không được đặt; điện
    thoại 390×844: chỉ có thẻ cho tới khi chạm, khung phủ cả màn, nút cao ít nhất 40 px, Escape
    rời khung). Luồng còn mở của các test này dựng bằng `web/src/test/canvas-writing-turn.ts`
    (vitest) và `web/e2e/live-stream.ts` (e2e, vì route của Playwright trả cả thân một lần); yêu
    cầu duyệt đẩy vào một luồng còn mở được `web/src/test/fake-backend.ts` ghi lại trên cuộc trò
    chuyện như server làm, để lời duyệt theo sau tìm thấy nó
- **Xem trước canvas đang viết tắt được bằng một công tắc ở Cài đặt, riêng cho thiết bị đang dùng:
  trình duyệt chỉ lưu một chữ `off`, và trình duyệt không cho lưu thì lựa chọn vẫn có hiệu lực
  trong tab kèm dòng nói rõ**
  - vitest: `web/src/hooks/use-live-preview.test.tsx` (mặc định bật và không lưu gì; tắt thì lưu
    đúng một chữ `off` dưới `canvas.livePreview`, bật lại thì xoá; chữ khác `off` vẫn là bật; mọi
    nơi đọc trong tab thấy cùng một lựa chọn; lựa chọn ở tab khác tới qua event `storage`, và hook
    thôi nghe khi không còn ai đọc; "asks a reader that is gone nothing more": nơi đọc đã rời đi
    không còn được báo, lựa chọn sau đó vẫn được lưu mà không lần đọc bộ nhớ nào xảy ra thay cho
    nó, và bao nhiêu nơi đọc đến rồi đi thì số lần đọc cho nơi còn lại vẫn như khi chỉ có một
    mình nó; trình duyệt từ chối lưu thì lựa chọn vẫn được nhận, `tabOnly`
    bật, nơi đọc kế tiếp trong tab vẫn thấy nó, nó đứng trên thứ trình duyệt đang lưu, và được bỏ
    khi trình duyệt lại lưu được);
    `web/src/components/canvas/live-preview-setting.test.tsx` (ô chọn gọi theo tên, mặc định bật,
    có dòng "chỉ trên thiết bị này", nằm trong thẻ Canvas; bấm thì ghi rồi xoá chữ `off`; thiết bị
    đã tắt thì hiện là tắt; trình duyệt từ chối lưu thì ô vẫn đổi và có dòng báo chỉ giữ trong tab);
    `web/src/screens/manage-screen.test.tsx` ("offers the switch for watching a canvas be written
    ahead of the machine's settings", "keeps that switch off the … section" cho chín mục còn lại)
  - vitest cấp App: `web/src/app-canvas-writing-off.test.tsx` (thiết bị đã tắt: không thẻ, không
    khung, dòng "đang nghĩ" và dòng trạng thái như trước mảnh đầu, ô chat giữ bàn phím; canvas agent
    viết xong vẫn tự mở cạnh chat trên màn rộng và không request ghi nào; màn hẹp cũng không có
    thẻ; tắt bằng công tắc trong Cài đặt thì chỉ chữ `off` được lưu và canvas viết sau đó không
    hiện; bật lại thì canvas kế tiếp hiện dần)
- **Tham số lời gọi tool không phải JSON object thành lỗi tool, lượt vẫn chạy tiếp**
  - pytest: `tests/test_tool_args_invalid.py` (tham số bị cắt giữa chừng báo vị trí chỗ dừng
    chứ không phải chỗ chuỗi bắt đầu, lỗi giữa chừng báo vị trí và vài chục ký tự quanh đó với
    ký tự điều khiển viết thành `<U+000A>`, escape `\u` sai gần cuối không bị coi là bị cắt,
    JSON không phải object được gọi theo kiểu, tham số đúng hay rỗng không bị đánh dấu, chi
    tiết không bao giờ lên wire, lời gọi hỏng lưu và đọc lại được còn lời gọi thường giữ đúng
    dạng hàng cũ, lời gọi hỏng không chạy mà trả lỗi rồi lượt chạy tiếp, `ask_user` và tool cần
    duyệt có tham số hỏng không hỏi ai); `tests/test_openrouter.py`
    ("test_malformed_tool_arguments_complete_as_an_invalid_call")
- **Tên hay đối số của lời gọi tool không phải chữ là luồng hỏng: lượt nhận lỗi provider, không
  đứt lặng vì một lỗi không lớp nào bắt**
  - pytest: `tests/test_openrouter.py`
    ("test_a_tool_call_field_that_is_not_text_is_a_malformed_stream", hai ca: đối số là object,
    tên là mảng)
- **Lời gọi tool bị cắt vì chạm giới hạn đầu ra được bảo chia nhỏ, các lần hỏng khác chỗ không
  bị coi là lặp**
  - pytest: `tests/test_tool_args_cut_off.py` (stream dừng với `finish_reason` `length` chỉ
    đánh dấu lời gọi cuối, lời gọi hỏng trước đó hay câu trả lời dừng bình thường không bị đánh
    dấu, lời gọi bị cắt nhận lời dặn chia nhỏ chứ không phải "gửi lại", sự kiện câu trả lời mang
    chi tiết chỗ hỏng của từng lời gọi, sáu lần hỏng khác chỗ không bị nhắc lặp hay dừng lượt,
    cùng một lời gọi hỏng ba lần liền vẫn bị nhắc, lỗi tool dài hơn trần bị cắt như mọi kết quả)
- **`/api/inbound` không nhận tên kênh nội bộ làm `source`**
  - pytest: `tests/test_api_inbound.py`
    ("test_a_relay_cannot_borrow_the_name_of_one_of_the_servers_own_channels": `chat`, `telegram`,
    `job`, `job:<id>`, `delegate:<…>`, `web`, `memory:<…>` bị 422 và không có run hay cuộc trò
    chuyện nào được tạo; "test_any_other_source_is_recorded_on_the_run": `api`, `selftest`,
    `slack:team`, `api:zalo` vẫn chạy và run ghi đúng nhãn)
- **Tệp trong workspace của agent phục vụ như nội dung không tin cậy: chỉ ảnh raster, PDF và chữ
  thuần mở tại chỗ, còn lại tải về**
  - pytest: `tests/test_untrusted_content.py` (mỗi nhóm đuôi của bảng ghim sẵn có đúng
    `Content-Type`, `inline` hay `attachment`, CSP sandbox trừ PDF; `.PNG` viết hoa như `.png`;
    HTML, `.xht`, `.rss`, `.atom`, `.ts`, tệp không đuôi đều là `application/octet-stream` tải về;
    SVG tải về khi mở; mọi response có `nosniff` và CORP `same-origin`; tên tệp chữ Việt, Nhật, có
    ngoặc kép, xuống dòng, `/` hay chỉ có emoji ra header mã hoá được bằng latin-1, có tên ASCII
    dự phòng và `filename*` giải mã lại đúng tên; bảng của canvas (`canvas_shown`): canvas chữ là
    `text/plain` mở tại chỗ và tải về khi yêu cầu, svg khi xem là `image/svg+xml` tải về còn khi
    lưu là chữ, ảnh theo kiểu mà byte của nó cho, byte không nhận ra là `application/octet-stream`
    không bao giờ mở tại chỗ);
    `tests/test_server_agents_activity_jobs.py::test_agent_files_are_served_only_from_the_workspace`
    (chỉ tệp trong workspace, kể cả qua symlink)
- **Canvas: tài liệu có phiên bản đi cạnh cuộc trò chuyện (tầng lưu trữ)**
  - pytest: `tests/test_artifact_kinds.py` (mỗi loại là chữ hoặc nhị phân, mỗi loại một trần,
    loại lạ bị từ chối theo tên, lỗi kích thước là `ValueError` để một chỗ trả lời được mọi đầu
    vào sai, loại tạo bằng tay là các loại chữ theo thứ tự của bảng chứ không theo tập,
    `sniff_image` nhận PNG, JPEG, GIF và WebP theo vài byte đầu rồi trả đuôi, còn `RIFF` không có
    `WEBP`, chữ cắt ngắn, trang hay PDF thì không, `prepare` kiểm byte của ảnh sau khi kiểm cỡ nên
    ảnh quá trần vẫn bị từ chối vì cỡ,
    "test_a_title_is_one_line_of_visible_text": xuống dòng thành dấu cách, bỏ ký tự
    điều khiển, bidi và tag nhưng giữ joiner của emoji, tiêu đề rỗng bị từ chối, giới hạn 200 ký
    tự đo sau khi làm sạch, ngôn ngữ là một tên ngắn viết thường tối đa 40 ký tự, ngôn ngữ có
    dấu cách, xuống dòng hay ký tự ẩn bị từ chối); `tests/test_artifact_guards.py` (mọi đường đặt
    tiêu đề đều lưu bản đã làm sạch, tiêu đề sai làm hỏng cả lần ghi, ngôn ngữ sai không tạo
    canvas, tác giả không phải `user` hay `agent:<id>` với mã agent hợp lệ bị từ chối, người tạo
    phải khớp tác giả: `""` cho người, `<id>` cho `agent:<id>`, lần ghi vượt trần của tác giả bị
    từ chối và không lưu gì, người được cả 1 GiB còn agent dừng trước một phần mười
    ("test_agents_stop_short_of_the_ceiling_so_the_person_can_still_save"), chạm đúng trần vẫn
    được, lần lưu gộp vào loạt chỉ tính phần thêm vào); `tests/test_store.py`
    ("test_a_delete_that_fails_halfway_leaves_the_conversation_whole");
    `tests/test_artifact_schema.py` (DB mới có đủ bảng và index, payload là các cột cuối, tổng
    kích thước cộng từ index `artifact_versions_by_size` mà không đọc trang chứa nội dung, DB cũ
    có thêm bảng canvas mà giữ nguyên tin nhắn, mở lần hai không đổi gì);
    `tests/test_artifact_links.py` (liên kết lại giữ `seen_version`, `seen_version` không lùi,
    không lưu liên kết hay focus nào cho cuộc trò chuyện hoặc canvas không tồn tại, kể cả lần
    ghi muộn sau khi xoá, một phiên bản được ghim khi có cuộc trò chuyện đã thấy hoặc đang đọc
    nó, đánh dấu chưa commit được huỷ cùng giao dịch của bên gọi, focus giữ canvas đang mở và
    đoạn được chọn, xoá cuộc trò chuyện bỏ liên kết và focus mà giữ canvas);
    `tests/test_artifact_read_cursor.py` (trang từ đầu một bản mới hơn bắt đầu con trỏ lại,
    trang bắt đầu trong phần đã đọc thì nối dài, trang nhảy cóc hay bản cũ không đổi gì, chỉ đọc
    liền tới cuối mới tính là đã thấy,
    "test_pages_taken_from_two_versions_never_count_as_one_whole_read", bản rỗng tính là đã thấy
    sau một lần đọc, đọc trọn bản cũ không kéo `seen_version` lùi);
    `tests/test_artifact_versions.py`
    ("test_thirty_saves_in_a_minute_that_nobody_has_seen_keep_one_version",
    "test_a_burst_that_never_pauses_still_closes_its_row_after_the_window",
    "test_a_clock_set_back_does_not_hold_a_burst_open",
    "test_a_version_an_agent_has_seen_is_never_folded_into_the_next_save",
    "test_a_version_an_agent_is_reading_page_by_page_is_never_folded_away",
    "test_a_save_that_fails_halfway_through_folding_loses_nothing"; số phiên bản không bao giờ
    dùng lại, base cũ bị từ chối kèm bản mới nhất, `apply` đọc, sửa và ghi trong một bước, CR và
    CRLF lưu thành LF trên mọi đường ghi, các ký tự ngắt dòng khác giữ nguyên trong dòng để dòng
    chỉ tách theo LF, khôi phục giữ các bản sau);
    `tests/test_artifact_store.py` (kích thước tính bằng byte UTF-8, payload sai loại hay vượt
    trần không lưu gì, byte không phải ảnh không vào được qua tạo hay ghi, trần đo trên chữ đã
    đổi xuống dòng, thứ không tồn tại là `KeyError`,
    "test_a_version_gone_from_a_canvas_that_is_there_names_the_newest": bản đã bị gộp hay chưa
    từng có là `VersionGone` kèm số bản mới nhất, xoá canvas bỏ phiên bản, liên kết và focus của
    nó, "test_list_matches_the_title_regardless_of_case_and_accents", hai canvas cùng giây xếp
    theo thứ tự tạo, "test_on_change_hears_every_write_after_commit_outside_the_lock",
    "test_a_failing_on_change_is_logged_and_the_write_stands")
- **Canvas: nguồn của canvas và bản nhập từ tệp (tầng lưu trữ)**
  - pytest: `tests/test_artifact_source_store.py`
    ("test_a_write_records_where_its_version_came_from_in_the_one_change": `write(source=…)` đổi
    nguồn cùng lúc với phiên bản mới, một event mang cả hai,
    "test_a_write_that_names_no_source_keeps_the_one_recorded": ghi, `apply`, khôi phục không nêu
    nguồn thì nguồn giữ nguyên, "test_a_refused_write_leaves_the_source_as_it_was",
    "test_setting_the_source_adds_no_version_and_keeps_the_time_of_the_last_change": `set_source`
    không thêm bản, không đổi `updated_at`, có event sau commit và ngoài khoá,
    "test_setting_the_source_of_a_canvas_that_is_gone_raises_key_error",
    "test_typing_right_after_a_reimport_keeps_the_imported_version" và
    "test_a_reimport_right_after_a_burst_of_typing_keeps_what_was_typed": dòng `import` không bị
    tự lưu của người gộp mất và cũng không gộp mất loạt tự lưu,
    "test_a_picture_canvas_takes_new_bytes_and_keeps_the_old_ones",
    "test_a_write_whose_payload_does_not_fit_the_kind_adds_no_version": chữ cho canvas ảnh hay
    byte cho canvas chữ là `PayloadMismatch`,
    "test_restoring_a_picture_brings_back_its_exact_bytes");
    `tests/test_artifact_authors.py`
    ("test_a_version_imported_from_a_file_is_named_as_one_whoever_imported_it": bản nhập của
    người lẫn của agent đứng riêng khỏi các bản tự viết của cùng tác giả, các bản nhập liền nhau
    là một nhóm);
    `tests/test_canvas_note_one_line.py`
    ("test_a_picture_that_changed_is_told_in_one_line_and_stays_unseen": canvas ảnh đổi thì ghi
    chú là một dòng tác giả, không diff, seen đứng yên,
    "test_a_reimport_from_the_web_is_told_in_one_line_and_stays_unseen": bản người nhập lại từ
    tệp cũng một dòng, `artifact_rewrite` sau đó vẫn bị từ chối);
    `tests/test_api_artifact_pictures.py`
    ("test_saving_text_onto_a_picture_canvas_is_422_and_the_picture_stays")
- **Canvas: những canvas agent đã ghi trong một cuộc trò chuyện (tầng lưu trữ)**
  - pytest: `tests/test_artifact_store_written_in.py`
    ("test_a_canvas_the_agent_began_and_one_it_only_changed_are_both_listed": `written_in` nêu cả
    canvas agent tạo lẫn canvas có sẵn mà agent chỉ sửa, kèm tiêu đề hiện tại, và cuộc trò chuyện
    gốc không có dòng nào,
    "test_each_conversation_lists_what_was_written_in_it_alone": canvas được ghi ở hai cuộc trò
    chuyện thì mỗi bên nêu phiên bản lớn nhất ghi ở bên đó, không phải bản mới nhất của canvas,
    "test_what_a_person_saved_in_the_conversation_is_not_the_agents_writing": bản người lưu trong
    cùng cuộc trò chuyện bị bỏ, canvas chỉ có bản của người không có dòng, phiên bản nêu là bản
    lớn nhất agent ghi dù người đã sửa sau,
    "test_a_deleted_canvas_is_no_longer_listed",
    "test_canvases_come_in_the_order_each_was_first_written_within_one_second": cùng một giây vẫn
    xếp theo lần ghi đầu, không theo mã, tiêu đề hay lần ghi mới nhất,
    "test_a_file_the_agent_imports_is_its_writing_as_a_new_canvas_or_a_new_version": bản agent
    nhập bằng `artifact_import` được tính, canvas mới lẫn phiên bản mới,
    "test_carrying_a_canvas_to_or_from_a_file_unchanged_writes_nothing": xuất, nhập không đổi và
    ghi nguồn không thêm phiên bản nên không sinh dòng nào,
    "test_a_file_the_person_reads_again_on_the_web_is_not_the_agents_writing": "Nhập lại" trên
    web là bản của người, không thuộc cuộc trò chuyện nào);
    `tests/test_artifact_store_usage.py`
    ("test_the_canvases_are_counted_with_the_stores_lock_held": `sizes` và `written_in` chạy câu
    truy vấn khi đang giữ khoá của store, nên không đếm phiên bản của một lần ghi còn dang dở,
    "test_a_canvas_named_as_written_cannot_be_changed_by_its_reader")
- **Canvas: số phiên bản mà SQLite không chứa nổi là một phiên bản không có, không phải lỗi 500**
  - pytest: `tests/test_artifact_version_range.py`
    ("test_a_version_number_at_or_beyond_the_64_bit_edge_is_gone_and_names_the_newest": mọi số từ
    `2**63` trở lên hay từ `-(2**63) - 1` trở xuống, cùng hai số sát mép còn nằm trong 64 bit, đều
    là `VersionGone` kèm số bản mới nhất chứ không phải `OverflowError` của driver,
    "test_a_canvas_that_is_not_there_stays_a_missing_canvas_whatever_version_is_asked": canvas
    không có vẫn là `KeyError` gọi đúng mã canvas chứ không thành "bản không còn",
    "test_a_read_of_a_version_too_large_to_exist_is_404_with_the_newest_number": xem một bản,
    `raw` và trang chạy với số đó đều 404 kèm `head_version`,
    "test_a_restore_of_a_version_too_large_to_exist_is_404_and_writes_nothing": khôi phục bị 404
    và không thêm bản nào,
    "test_a_save_on_a_version_too_large_to_exist_is_a_conflict_and_writes_nothing": lưu với
    `base_version` đó là 409 kèm bản mới nhất, canvas không đổi (số này không bao giờ xuống SQL
    nên test chỉ ghim điều đó),
    "test_the_tool_reads_a_version_too_large_to_exist_as_one_that_is_gone": `artifact_read` trả
    đúng câu "bản đó không còn, bản mới nhất là …" cho cả số lẫn chuỗi số, không phải "tool
    lỗi"). Việc chặn nằm ở một chỗ là `ArtifactHistory.version`, nơi mọi đường gọi tên một phiên
    bản đều đi qua, nên không route hay tool nào cần giới hạn riêng
- **Canvas: chữ có nửa ký tự Unicode bị từ chối kèm lý do, không phải lỗi 500**
  - pytest: `tests/test_artifact_unstorable_text.py`
    ("test_the_store_refuses_half_a_character_saying_which_part_and_writes_nothing": nửa ký tự
    (surrogate lẻ, ví dụ nửa đầu của một emoji) trong nội dung hay tiêu đề, qua tạo, lưu, `apply`
    và đổi tên, đều là `UnstorableText` kèm câu nói rõ phần nào sai và kho không đổi gì,
    "test_a_request_with_half_a_character_is_422_saying_which_part_and_writes_nothing": tạo, lưu
    và đổi tên qua REST đều 422 kèm đúng câu đó, không ghi gì,
    "test_a_whole_emoji_sent_as_an_escaped_pair_is_kept_by_every_write": emoji đủ cặp, mà JSON viết
    thành hai `\u` escape, vẫn được lưu ở cả ba đường,
    "test_the_tool_refuses_half_a_character_saying_which_part_and_writes_nothing": `artifact_create`,
    `artifact_edit` (khớp đúng, khớp nới, tiêu đề, và lần sửa không đổi gì mà vẫn gửi tiêu đề) và
    `artifact_rewrite` trả đúng câu đó chứ không phải "tool lỗi", canvas không đổi và khoá của kho
    được nhả, `language` có nửa ký tự vẫn nhận lời từ chối `language` có sẵn,
    "test_a_whole_emoji_is_written_by_every_tool",
    "test_an_old_passage_with_half_a_character_is_one_the_canvas_does_not_hold": `old` có nửa ký
    tự chỉ là đoạn không tìm thấy, vì canvas không bao giờ chứa nó). Việc chặn nằm ở `utf8_size`,
    một chỗ tính cỡ UTF-8 cho nội dung, tiêu đề và `new` của lần sửa, nên không đường ghi nào cần
    kiểm riêng; hai hàng của `tests/test_artifact_errors.py` và `tests/test_artifact_scope.py` ghim
    chỗ bảng 422 và `canvas_errors` nhận ra `UnstorableText`
- **Canvas: bảy tool của agent, trong đó năm tool để tạo, liệt kê, đọc, sửa và viết lại canvas**
  - pytest: `tests/test_artifact_tools.py` (`build_artifact_tools` trả năm tool, không tool nào
    hỏi duyệt; hai tool mang tệp vào và ra nằm ở mục nhập, xuất bên dưới; mô tả đưa tài
    liệu người sẽ sửa dần vào canvas dù chỉ vài dòng và nói cách thêm chữ bằng một lần sửa, tạo lưu canvas
    dưới tên agent và không trả lại nội dung, con được giao việc chia sẻ canvas nó tạo với gốc,
    loại agent không ghi được (ảnh) bị từ chối, enum của tool là năm loại chữ, tạo html, svg hay
    mermaid như mọi canvas và html được lớn hơn tài liệu nhưng có trần riêng, mô tả của tool tạo
    (và chỉ nó) nói cho trang html biết khung cách ly không cho gì: không `localStorage`, không
    mạng ngoài ba CDN, không `alert`, không mở cửa sổ,
    "test_a_turn_from_the_web_chat_telegram_or_a_job_writes_and_reads_canvases": lượt web chat,
    Telegram và job tạo, đọc, sửa, viết lại và liệt kê được,
    "test_a_turn_from_the_inbound_api_writes_no_canvas_yet_reads_one": lượt API chỉ đọc và liệt
    kê, "test_a_delegated_child_writes_when_the_turn_its_chain_began_from_could": con ghi được
    khi chuỗi bắt đầu từ web chat, Telegram hay job, không ghi được khi bắt đầu từ API hay không
    có gốc, canvas master đã đọc không vào tầm của con, lần đọc của một con
    không mở rộng tầm của con kế tiếp, canvas do người tạo chỉ vào tầm qua liên kết, canvas không
    tồn tại trả lời như canvas ngoài tầm,
    "test_a_turn_writes_at_most_thirty_versions_of_one_canvas": lần ghi không đổi gì không tính
    và canvas khác có bộ đếm riêng, một lượt tạo tối đa 30 canvas, danh sách mới nhất trước theo
    giờ của chủ và đánh dấu canvas có bản cuộc trò chuyện chưa thấy, lọc theo tiêu đề và master
    liệt kê mọi canvas, mọi lời từ chối của kho nói phải làm gì thay vào đó, đối số không phải
    chuỗi bị từ chối trước khi chạm vào gì, mọi tool cần cuộc trò chuyện của lượt,
    "test_each_write_opens_with_its_tag_and_a_read_or_a_list_never_does");
    `tests/test_artifact_read.py`
    ("test_the_pages_of_a_canvas_fit_the_cap_and_join_back_into_its_text", ghi chú của hook bị cắt
    trước bất kỳ dòng nào của trang, dòng dài hơn một trang bị cắt và trang sau bắt đầu ở dòng kế,
    phần bị cắt chưa ai đọc nên bản đó không tính là đã thấy,
    "test_only_a_read_from_the_first_line_to_the_last_makes_a_version_seen", người lưu giữa hai
    trang thì lần đọc vẫn ở bản nó bắt đầu, bản đã bị gộp mất thì báo bản mới nhất, mỗi trang nêu
    ai viết các bản chưa thấy kể cả bản người khôi phục, trang theo số dòng đặt trước và bản mới
    nhất khi không nói bản nào,
    dòng quá cuối và loại không đọc được thành chữ bị từ chối, canvas code hiện ngôn ngữ cạnh loại);
    `tests/test_artifact_edit_tools.py` (sửa trích lại các dòng đã đổi và tính bản mới là đã thấy,
    "test_an_edit_says_how_long_the_canvas_now_is_as_a_read_counts_it": kết quả sửa nêu cỡ mới
    của canvas, số dòng đúng như trang đọc đếm,
    sửa đè lên lần lưu của người nêu người và để bản đó chưa thấy,
    "test_the_nearest_passage_to_a_missed_edit_is_looked_for_outside_the_lock", diff của sửa vừa
    mọi trần và để ghi chú của hook bị cắt trước, sửa không đổi gì không thêm bản mà vẫn đổi tiêu
    đề, "test_a_rewrite_needs_the_canvas_read_whole_first": liệt kê, đọc trang đầu hay nhảy tới
    trang cuối đều không đủ, viết lại đè lên lần lưu của người bị từ chối kèm phần họ đổi,
    "test_a_conflict_over_many_writers_names_the_newest_six_and_any_restore", xung đột vừa mọi
    trần, viết lại từ bản mới nhất đã đọc trọn thì ghi,
    "test_what_the_agent_created_or_rewrote_it_rewrites_without_reading_back": bản agent vừa tạo
    hay viết lại thì viết lại được ngay mà không đọc lại, đúng như mô tả tool nói, và mô tả tạo
    dặn sửa chính canvas đã có, viết lại chỉ đổi kiểu xuống
    dòng là không đổi gì, con sửa hay viết lại thì chia sẻ canvas với gốc,
    "test_a_kind_agents_do_not_write_is_refused_only_once_the_canvas_is_in_reach": canvas ảnh của
    người, trong tầm thì bị từ chối là loại đóng, ngoài tầm thì như không tồn tại, sửa và viết lại
    html, svg, mermaid như mọi canvas, trang html 1 MB viết liền một dòng thì sửa theo đoạn được
    còn viết lại bị từ chối kèm lời dặn dùng `artifact_edit`, diff trích
    dãy backtick có rào dài hơn, sửa khớp hai chỗ bị từ chối trừ khi thay mọi chỗ);
    `tests/test_artifact_unchanged_rename.py`
    ("test_a_canvas_deleted_before_an_unchanged_write_renames_it_reads_as_not_found": canvas bị
    xoá giữa lần ghi không đổi gì và lần đổi tiêu đề đi kèm thì `artifact_edit` lẫn
    `artifact_rewrite` trả đúng câu không tìm thấy canvas chứ không phải "tool lỗi");
    `tests/test_canvas_tool_wiring.py`
    ("test_an_agent_with_no_allow_list_gets_the_seven_canvas_tools": agent không có allow-list,
    master hay không, nhận đủ bảy tool theo thứ tự, năm tool cũ rồi `artifact_import`,
    `artifact_export`, và chỉ `artifact_export` hỏi duyệt,
    "test_an_allow_list_keeps_out_the_canvas_tools_it_does_not_name", master
    liệt kê mọi canvas theo giờ của chủ còn agent khác thì không,
    "test_an_export_lands_only_in_the_agents_own_workspace_and_write_paths": `artifact_export`
    lắp từ profile chỉ ghi trong workspace và `write_paths` của chính agent đó, trang đọc vừa
    trần đầu ra của chính agent)
- **Canvas: tệp trong workspace vào canvas bằng `artifact_import`, canvas ra tệp bằng
  `artifact_export`, chữ không đi qua model**
  - pytest: `tests/test_artifact_source.py` (đọc tệp nguồn: chữ về đúng dạng kho sẽ giữ, bỏ BOM,
    xuống dòng LF, mã băm của đúng chữ đó, ảnh về nguyên từng byte, đường dẫn thoát workspace
    bằng `..`, bằng đường dẫn tuyệt đối hay `~người-không-có` bị từ chối, đường dẫn tuyệt đối
    trong workspace và symlink người đặt trong workspace thì đọc được như `workspace_read`, tệp
    không có là không tìm thấy, thư mục bị từ chối,
    "test_a_pipe_is_refused_without_waiting_for_a_writer": FIFO bị từ chối ngay vì tệp được mở
    không chặn, test giữ thời hạn và tự mở đầu ghi ở `finally` nên không treo được,
    "test_a_device_behind_a_link_is_refused",
    "test_a_file_over_the_cap_is_refused_before_a_byte_is_read",
    "test_a_file_that_grew_after_it_was_measured_is_refused_one_byte_past_the_cap": đọc nhiều
    nhất trần cộng một byte, tệp đúng bằng trần thì đọc trọn,
    "test_bytes_that_are_not_utf8_text_are_refused_rather_than_patched": byte hỏng hay byte NUL
    không bị thay bằng ký tự thế chỗ, byte không mở đầu như ảnh nào thì canvas ảnh từ chối);
    `tests/test_artifact_source_kinds.py` (đuôi cuối cùng định loại, không kể hoa thường, đuôi lạ
    bị từ chối kèm lời dặn truyền `kind`, code lấy ngôn ngữ theo đuôi và để trống khi không biết);
    `tests/test_artifact_source_ref.py` (đường dẫn có ký tự điều khiển, ký tự đổi chiều chữ,
    U+2028, nửa cặp surrogate đứng lẻ, quá 1.024 ký tự hay rỗng bị từ chối, đường dẫn thường đi
    qua nguyên vẹn,
    "test_a_source_names_the_agent_and_the_path_under_its_workspace": `source_for` và
    `parse_source` đi vòng đúng, tách ở dấu `/` đầu tiên, nguồn tính từ gốc workspace chứ không từ
    gốc máy, "test_a_source_is_never_built_from_a_name_that_hides_something": tên thật trên đĩa
    cũng được kiểm, URL, chuỗi rỗng và nguồn thiếu tiền tố `workspace:` parse ra không có gì,
    `web_url` chỉ nhận http và https có
    host, không khoảng trắng, không nửa surrogate lẻ, không quá 2.000 ký tự,
    "test_a_link_that_carries_a_login_is_refused_in_words_that_say_why": link có tên đăng nhập hay
    mật khẩu trước dấu `@` của tên máy chủ bị từ chối bằng câu riêng, không chép lại link, còn
    `@` trong đường dẫn, câu truy vấn hay phần sau `#` thì vẫn qua,
    "test_each_file_a_page_points_at_is_counted_once_and_a_link_that_loads_none_is_not");
    `tests/test_artifact_import.py`
    ("test_a_file_becomes_a_canvas_that_remembers_where_it_came_from": canvas có `source`, tác giả
    `agent:<id>`, cuộc trò chuyện đã thấy bản 1, kết quả là thẻ, tên tệp, cỡ, 12 ký tự mã băm và
    dòng nguồn, không có đường dẫn của máy, con chia sẻ canvas nó nhập với gốc của chuỗi, tiêu đề
    mặc định lấy tên tệp, trang `index` lấy tên thư mục chứa nó, tên dài được ghép dấu trước rồi
    mới cắt ở 200 ký tự, `title` trắng tính như không gửi,
    "test_the_result_tells_of_a_page_without_a_word_the_file_holds": chuỗi đánh dấu trong chữ,
    trong `src=` và trong `href=` của tệp đều không xuất hiện ở kết quả, các tệp trang trỏ tới chỉ
    được đếm, cảnh báo đó chỉ có với html và svg, `kind` gửi kèm thắng đuôi tệp và code lấy ngôn
    ngữ theo đuôi, đối số tuỳ chọn gửi trắng tính như bỏ trống, ảnh vào nguyên từng byte và dòng
    nguồn không mời đọc, `source_url` được giữ làm nguồn,
    "test_an_absolute_path_inside_the_workspace_is_stored_relative_to_it");
    `tests/test_artifact_import_guards.py`
    ("test_a_turn_on_a_channel_with_no_canvas_is_refused_before_the_file_is_read": lượt API bị
    từ chối, tệp không được đọc, không canvas nào được tạo,
    "test_a_telegram_turn_and_a_job_bring_a_file_in_as_a_canvas": lượt Telegram và job mang tệp
    vào thành canvas gắn với cuộc trò chuyện của lượt,
    "test_a_turn_that_made_its_share_of_canvases_imports_no_more" và
    "test_a_turn_that_wrote_its_share_of_one_canvas_imports_into_it_no_more": lần thứ 31 bị từ
    chối mà không đọc tệp, `kind` lạ, URL xấu, đường dẫn giấu ký tự hay chỉ có khoảng trắng, đường
    dẫn hay link mang nửa surrogate lẻ bị từ chối trước khi đọc, `source_url` mang tên đăng nhập
    hay mật khẩu cũng vậy và không thành nguồn của canvas có sẵn
    ("test_a_link_with_a_login_never_becomes_the_source_of_a_canvas_that_is_there"), tệp không đọc được thì không tạo canvas và không trừ ngân sách, tệp không
    đổi được loại của canvas đã có, canvas ngoài tầm trả lời như canvas không tồn tại kể cả khi
    `kind` gửi kèm lệch); `tests/test_artifact_import_outside.py`
    ("test_a_path_out_of_the_workspace_is_told_so_whatever_its_suffix_or_kind": đường dẫn ra ngoài
    workspace (`..`, tuyệt đối, `~tên`) nhận câu ra ngoài workspace chứ không phải câu về đuôi
    tệp, có hay không có `kind`, kể cả khi `kind` gửi kèm không phải loại canvas nào (không
    nhận câu về loại lạ), và không tệp nào bị mở,
    "test_a_path_out_of_the_workspace_is_told_so_before_the_canvas_it_was_to_go_into": cả khi
    nhập vào canvas có sẵn, `kind` lệch hay canvas ngoài tầm, không trừ ngân sách,
    "test_a_link_inside_the_workspace_is_still_followed_to_where_it_leads": liên kết người đặt
    trong workspace vẫn được đi theo như `workspace_read`, đường dẫn tuyệt đối rơi vào trong
    workspace vẫn đọc được); `tests/test_artifact_import_replace.py`
    ("test_a_file_replaces_the_newest_version_the_conversation_has_seen": bản mới của agent mang
    ghi chú `import`, seen lên bản mới, `language` gửi kèm không đổi gì,
    "test_a_file_that_changes_nothing_adds_no_version_and_opens_no_gate": thẻ có `unchanged`,
    không trừ ngân sách, seen đứng yên, canvas vẫn gắn với cuộc trò chuyện mà không được chia
    sẻ, `title` mới vẫn đổi tên, nguồn đổi thì được ghi lại bằng một dòng, canvas ảnh chỉ thêm
    bản khi byte khác,
    "test_a_file_does_not_go_over_versions_the_conversation_has_not_seen": lời từ chối nêu ai
    viết các bản đó và không ghi, không đếm, không đánh dấu đã thấy gì,
    "test_replace_goes_over_unseen_versions_and_leaves_them_unseen": `replace: true` ghi đè, nêu
    bản của ai bị thay và rằng chúng còn trong lịch sử, seen đứng yên nên ghi chú lượt sau vẫn kể
    các bản đó, "test_a_change_made_while_the_file_was_read_is_not_written_over": bản mới nhất
    được tra sau khi đã có tệp trong tay); `tests/test_artifact_import_args.py`
    ("test_only_a_code_canvas_takes_a_language_from_the_suffix": tệp `.py` nhập với
    `kind: markdown` không mang ngôn ngữ nào,
    "test_a_title_and_a_link_sent_with_a_file_are_recorded_in_the_write_that_replaces": `title`
    và `source_url` gửi kèm lần nhập đè được ghi trong chính lần ghi đó, một bản duy nhất, bản
    ấy thuộc cuộc trò chuyện đã nhập, dòng nguồn nêu đúng link,
    "test_a_link_sent_with_a_file_that_changes_nothing_becomes_the_source": tệp không đổi gì thì
    link vẫn thành nguồn và chỉ được báo một lần,
    "test_a_save_that_lands_as_the_file_is_written_is_refused_not_written_over": lần ghi nêu
    đúng bản đã đem so, nên bản người lưu chen vào sát lúc ghi bị báo xung đột chứ không bị ghi
    đè, không trừ ngân sách, không đổi nguồn); `tests/test_artifact_export.py`
    ("test_the_two_file_tools_come_together_and_only_the_export_asks_first",
    "test_text_goes_out_as_utf8_and_the_canvas_stays_as_it_was": kết quả không mở đầu bằng thẻ,
    chỉ nói đã thay tệp khi tệp có sẵn, canvas không thêm bản và lượt không bị trừ ngân sách, ảnh
    ra nguyên từng byte, canvas html ra `x.html` vẫn là `x.html` và đường dẫn tuyệt đối được gọi
    lại từ gốc workspace, tham số `version` và bản không còn, canvas ngoài tầm thì không tạo tệp
    và hỏi một bản nó không có cũng chỉ nhận câu không tìm thấy canvas,
    "test_an_export_makes_nothing_seen_so_an_unread_canvas_still_cannot_be_rewritten": xuất
    không phải đọc cũng không phải ghi, canvas vẫn gắn với cuộc trò chuyện mà không được chia sẻ);
    `tests/test_artifact_export_paths.py` (thoát workspace bằng `..`, bằng đường dẫn tuyệt đối
    hay `~người-không-có`, đích là thư mục, đường dẫn giấu ký tự, mang nửa surrogate lẻ hoặc
    rỗng đều bị từ chối và cây thư mục không đổi, "test_an_agent_held_to_its_write_paths_exports_only_under_them",
    "test_a_folder_linked_out_of_the_workspace_takes_no_export",
    "test_a_folder_linked_out_of_the_write_paths_takes_no_export",
    "test_a_link_is_never_written_through": đích là symlink, kể cả symlink trỏ tới chỗ chưa có,
    bị từ chối và tệp nó trỏ tới không đổi; symlink dẫn tới một thư mục được báo là symlink, không
    phải là thư mục,
    "test_a_write_that_fails_leaves_the_old_file_whole_and_no_other_behind": `os.replace` ném
    `OSError` thì tệp cũ nguyên vẹn, không sót tệp tạm, lời báo không có đường dẫn của máy,
    "test_a_file_marked_read_only_is_not_replaced": tệp chỉ đọc không bị thay, và dòng `warning`
    trong log mang số lỗi của "permission denied" như một lần ghi thường, không phải `None`,
    "test_a_new_file_gets_the_mode_of_any_written_file_and_an_old_one_keeps_its_own");
    `tests/test_artifact_export_disk.py`
    ("test_a_name_longer_than_the_disk_takes_is_an_export_that_failed": tên tệp hay tên thư mục
    dài hơn hệ tệp nhận, ở thư mục có sẵn hay thư mục lần ghi sẽ tạo, đều cho agent câu không ghi
    được chứ không phải tên lớp lỗi, cây thư mục không đổi và log có đúng một dòng `warning` nêu
    chỗ thật tệp định tới, lớp lỗi và `errno`, không có dòng `error` của một tool sập,
    "test_a_folder_the_process_may_not_enter_is_an_export_that_failed": thư mục mode 000, tệp
    trong đó có sẵn hay chưa, cũng vậy; bỏ qua khi chạy bằng root,
    "test_a_folder_that_is_a_link_back_to_itself_is_an_export_that_failed": thư mục là symlink
    trỏ về chính nó, có hay không có `write_paths`, cho cùng một kết quả trên Python 3.12 (nơi
    `Path.resolve` ném `RuntimeError`) và 3.13,
    "test_a_write_path_that_is_a_link_back_to_itself_holds_no_folder": `write_paths` có một
    symlink như thế thì tệp rơi ngoài các đường dẫn còn lại vẫn bị từ chối bằng câu cũ,
    "test_a_write_path_that_is_a_link_to_a_folder_holds_what_that_folder_holds": `write_paths`
    là symlink tới một thư mục khác trong workspace thì tệp gửi dưới nó vẫn được ghi, vào đúng
    thư mục symlink dẫn tới,
    "test_where_a_path_leads_is_judged_before_the_disk_is_asked_about_its_name": tên quá dài nằm
    ngoài workspace, sau một thư mục liên kết ra ngoài hay ngoài `write_paths` vẫn nhận lời từ
    chối về vị trí như trước, không ghi gì và không để lại dòng log nào);
    `tests/test_artifact_export_write.py`
    ("test_a_failure_no_disk_reports_is_worded_like_any_other_and_leaves_nothing_behind":
    `os.replace` ném `ValueError` thì agent vẫn nhận câu không ghi được, tệp cũ nguyên vẹn, không
    sót tệp tạm hay thư mục, nguyên nhân nằm trong log cùng chỗ thật trên máy mà tệp định tới,
    viết ở dạng `repr`,
    "test_a_write_cut_short_takes_its_half_written_file_away": lần ghi đứt giữa chừng vì
    `OSError`, `MemoryError` hay một `BaseException` đều dọn tệp ghi dở,
    "test_the_folders_made_for_a_file_that_was_not_written_are_taken_away_again": chỉ những thư
    mục chính lần ghi đó tạo, từ sâu ra nông, thư mục có sẵn thì ở lại,
    "test_a_folder_that_holds_something_by_then_is_left_with_what_it_holds": lỗi tới tay nơi
    gọi vẫn là lỗi đã chặn lần ghi, không phải việc thư mục không xoá được,
    "test_a_name_someone_put_a_link_at_first_is_never_written_through": tên tệp tạm đã có sẵn
    một symlink thì lần ghi dừng, tệp symlink trỏ tới không đổi và symlink không bị dọn,
    "test_a_folder_another_write_made_first_is_used_and_is_not_this_ones_to_take_away");
    `tests/test_artifact_export_log.py`
    ("test_a_disk_that_refuses_is_worded_for_the_agent_and_leaves_one_warning_in_the_log": đĩa
    đầy, mất quyền ghi hay `OSError` không có số đều cho agent câu không ghi được với đường dẫn
    tương đối, và để lại đúng một dòng `warning` trong log nêu chỗ thật tệp định tới ở dạng
    `repr`, tên lớp lỗi và `errno`, không kèm lời của hệ điều hành,
    "test_the_letters_of_a_name_are_logged_as_letters_whatever_the_alphabet": tên tệp tiếng
    Việt vào log vẫn là chữ đọc được chứ không thành mã `\u…`, ở nhánh lỗi do đĩa lẫn nhánh
    lỗi không do đĩa,
    "test_a_folder_whose_name_holds_a_line_break_starts_no_line_of_its_own_in_the_log": thư mục
    thật mode 555 có tên chứa `\n`, `\r` hay U+2028 rồi tới một dòng trông như bản ghi log, đi
    tới qua một symlink tên thường, vẫn chỉ để lại một bản ghi nằm trên một dòng khi ghi ra theo
    đúng định dạng log của server; bỏ qua khi chạy bằng root,
    "test_a_failure_no_disk_reports_names_such_a_folder_on_the_line_it_began_too": nhánh lỗi
    không do đĩa, ghi kèm traceback, cũng không để dòng nào của log mở đầu bằng chữ trong tên
    thư mục);
    `tests/test_artifact_export_modes.py`
    ("test_the_file_being_written_is_open_to_no_reader_the_finished_one_is_closed_to": dưới umask
    022 và 077, từ lúc được tạo tới lúc chữ đi vào, tệp tạm không mở cho ai mà tệp cuối đóng, tệp
    thay tệp cũ nhận mode của tệp cũ trước khi byte nào được ghi, tệp mới có mode như mọi tệp ghi
    thường);
    `tests/test_artifact_number_args.py`
    ("test_a_version_that_is_no_finite_number_exports_nothing": `version` là vô cực hay NaN, kể
    cả khi JSON gửi `1e999`, bị từ chối bằng lời và không tệp nào được ghi,
    "test_a_read_sent_one_shows_no_page_and_moves_no_cursor": `version`, `from_line` và `lines`
    của `artifact_read` cũng vậy, con trỏ đọc đứng yên,
    "test_a_number_as_text_is_read_and_what_is_no_number_reads_as_left_out": số viết thành chuỗi
    vẫn được đọc, thứ không phải số vẫn tính như bỏ trống);
    `tests/test_artifact_source_unreadable.py` (tệp, hay thư mục chứa nó, mà tiến trình không có
    quyền đọc: lời từ chối nói đúng là thiếu quyền chứ không gọi đó là thứ không phải tệp thường,
    tool nhập không tạo canvas và không trừ ngân sách, lần nhập lại từ web trả 422 cùng câu đó
    và canvas đứng yên);
    `tests/test_artifact_file_reach.py` (đem canvas ra tệp hay đem tệp vào mà không đổi gì thì
    không nới tầm với của ai:
    "test_what_a_child_carried_to_or_from_a_file_stays_out_of_the_next_childs_reach": con xuất
    hay nhập lại không đổi canvas của chính nó thì canvas chỉ gắn với cuộc trò chuyện của con,
    không chia sẻ, gốc của chuỗi giữ nguyên dù đã gắn sẵn hay chưa, con kế tiếp đọc, xuất hay
    nhập đều nhận câu không tìm thấy canvas và không tệp nào được ghi,
    "test_what_the_master_carried_does_not_reach_its_delegated_child": master xuất hay nhập lại
    canvas của người thì con được giao việc sau đó vẫn không với tới,
    "test_an_import_that_writes_a_version_shares_the_canvas_as_any_write_does": lần nhập thêm
    bản vẫn chia sẻ với cả chuỗi, và xuất hay nhập không đổi sau đó không rút lại phần chia sẻ);
    `tests/test_kit_hooks_canvas_files.py` (hook của kit và hai tool canvas chạm tệp:
    "test_a_hook_that_guards_files_is_asked_about_the_canvas_tools_that_carry_them": hook có
    matcher `Read|Write|Edit|Bash` hay `workspace_read|workspace_write` chặn cả `workspace_read`,
    `workspace_write`, `artifact_import` và `artifact_export`,
    "test_a_hook_is_asked_only_about_the_canvas_tool_that_does_what_it_guards": hook chỉ nêu
    `Write` không được hỏi về lần nhập, hook chỉ nêu `Read` không được hỏi về lần xuất, cả trước
    lẫn sau lời gọi, hook nêu tên tool canvas chỉ được hỏi về đúng tool đó,
    "test_front_matter_still_reads_a_harness_name_as_the_plain_file_tool": `Read` trong front
    matter vẫn là `workspace_read`, payload giữ `tool_name` thật và mang `tool_alias` là `Write` /
    `Read`, "test_a_hook_that_refuses_writes_stops_an_export_before_any_file_is_made" và
    "test_a_hook_that_refuses_reads_stops_an_import_before_any_canvas_is_made": qua sổ đăng ký
    tool thật, hook chặn thì không tệp nào được ghi và không canvas nào được tạo,
    "test_the_hooks_of_an_agents_kit_stand_before_its_canvas_file_tools": hook trong profile của
    agent đứng trước hai tool đó trong sổ đăng ký lắp từ profile)
- **Canvas: kênh nào ghi được, người đọc của lượt có ngồi ở web không, agent với tới canvas nào,
  một lượt ghi bao nhiêu, ai viết các bản chưa thấy**
  - pytest: `tests/test_artifact_scope.py`
    ("test_a_turn_from_the_web_chat_telegram_or_a_job_writes_a_canvas": lượt API thì không,
    "test_a_delegated_child_writes_when_the_turn_its_chain_began_from_could": con theo nguồn của
    lượt mở đầu chuỗi, con mở trước khi chuỗi ghi gốc thì không bao giờ ghi, người gõ thẳng vào
    cuộc trò chuyện của con thì ghi được từ đó,
    "test_an_api_turn_in_a_childs_own_conversation_writes_none": chiều ngược lại, lượt API trong
    cuộc trò chuyện của con thì không ghi và không tính là vắng, dù chuỗi bắt đầu từ web chat,
    Telegram hay job,
    "test_the_reader_of_a_telegram_turn_or_a_job_is_away_from_the_web",
    "test_a_delegated_childs_reader_is_where_its_chain_began" và
    "test_a_person_typing_in_a_childs_own_conversation_reads_from_there": người đọc của lượt
    Telegram, của job và của con trong chuỗi bắt đầu từ đó không ngồi ở web; lượt web chat, lượt
    API và chuỗi không có gốc thì không tính là vắng, agent ghi được năm loại chữ (markdown, code, html, svg, mermaid) chứ không ghi ảnh, lời từ
    chối kể đủ năm loại, lần ghi thứ 31 cho một canvas trong lượt bị từ chối, một
    lượt tạo tối đa 30 canvas,
    "test_a_batched_call_counts_toward_its_turn_and_a_child_turn_counts_apart", master với tới mọi
    canvas còn agent khác chỉ canvas của mình, canvas một lượt trong chuỗi chỉ đọc không vào tầm
    của con kế tiếp, mỗi lời từ chối của kho thành lời dặn (kể cả chữ có nửa ký tự Unicode),
    "test_a_canvas_out_of_reach_reads_exactly_like_one_that_does_not_exist", lỗi khác đi qua
    nguyên vẹn); `tests/test_artifact_authors.py` (dòng tác giả gom từng đoạn liền của một tác
    giả, nhóm phủ cả những số bản một loạt gộp đã bỏ,
    "test_the_authors_line_names_the_six_newest_groups_at_most": giữ sáu nhóm mới nhất và dấu …
    đứng đầu, "test_a_restore_is_a_group_of_its_own_naming_the_version_it_brought_back");
    `tests/test_artifact_reach.py`
    ("test_a_quiet_canvas_linked_here_is_found_past_newer_ones_out_of_reach",
    "test_reachable_and_is_reachable_agree_on_every_kind_of_canvas",
    "test_a_persons_canvas_is_reached_only_through_a_link_whatever_the_agent_is_called", khớp tiêu
    đề bỏ qua hoa thường và dấu trước khi giới hạn, mới sửa trước); `tests/test_store.py`
    ("test_a_child_keeps_the_root_of_its_delegation_and_nothing_can_change_it");
    `tests/test_tools_delegate.py`
    ("test_the_child_records_its_root_and_where_the_root_turn_came_from",
    "test_a_child_further_down_keeps_the_root_its_parent_was_given")
- **Canvas: sửa theo đoạn khớp, chỉ ra chỗ gần nhất khi trượt, diff có rào và có trần**
  - pytest: `tests/test_text_edit.py` (khớp chính xác thay tại chỗ, nháy cong và dấu cách đặc biệt
    khớp dạng thường theo cả hai chiều, khớp chính xác thắng khớp nới lỏng, khớp nới lỏng nhiều chỗ
    bị từ chối kèm số chỗ, khớp chính xác nhiều chỗ bị từ chối trừ khi thay tất cả, `old` rỗng bị
    từ chối, "test_no_match_raises_a_bare_not_found_without_searching": phần chạy trong khoá của
    kho không tìm gì, trần tính số byte của đúng chữ đã khớp, vừa đúng trần thì giữ còn hơn một
    byte thì không, `replace_all` quá trần bị từ chối trước khi dựng chuỗi, chuẩn hoá giữ nguyên vị
    trí từng ký tự); `tests/test_text_nearest.py`
    ("test_a_miss_names_the_closest_lines_and_quotes_them_verbatim", lời báo rào vùng sau câu không
    tìm thấy, không gì giống hay một đoạn giống quá ít thì không có vùng,
    "test_two_equally_close_places_give_no_region",
    "test_a_long_old_on_a_long_text_compares_at_most_three_windows", dòng rào lặp khắp nơi không
    kéo vùng đi chỗ khác, vùng quanh một dòng khổng lồ vẫn trong cỡ của nó, đoạn khớp dài bị cắt ở
    giới hạn dòng, `old` quá dài thì không tìm, văn bản dài hơn `MISS_MAX_TEXT` cũng không tìm
    (trần theo số đo bộ nhớ, 1 MiB ký tự): đúng trần vẫn trích đoạn gần nhất, hơn một ký tự thì chỉ
    có lời không tìm thấy thường); `tests/test_artifact_diff.py` (hai dạng thẻ đọc lại
    qua cùng một mẫu, thẻ chỉ tính khi đứng ngay đầu kết quả, rào dài hơn mọi dãy backtick bên
    trong, dòng vừa chỗ giữ nguyên, dòng dài hiện quanh phần cần xem,
    "test_removed_lines_take_at_most_half_and_what_was_written_always_shows", dòng dài bị đổi cắt
    quanh chỗ đổi ở cả hai bên, "test_the_diff_never_outgrows_its_budget", số đếm cuối luôn vừa
    ngân sách, dòng thêm dài bị cắt cho vừa chỗ chứ không bị bỏ, tiêu đề đoạn đánh số dòng chỉ theo
    LF và theo chỗ trong chữ mới, không khác gì thì diff rỗng, chỉ phần giữa đã đổi được so,
    "test_a_diff_quoting_a_backtick_run_is_drawn_again_to_fit_a_longer_fence", chỗ quá nhỏ vẫn kết
    thúc bằng số đếm)
- **Canvas: chỗ đổi trải quá rộng thì kết quả nói bằng lời, diff vẽ ra thì vẽ ngoài vòng lặp chung**
  - pytest: `tests/test_artifact_quote.py`
    ("test_an_edit_spread_over_too_many_lines_is_written_and_quotes_no_diff": sửa vẫn được ghi,
    kết quả kết thúc bằng lời bảo đọc lại bằng `artifact_read` chứ không có khung diff, và việc so
    từng dòng không chạy lần nào (`SequenceMatcher` bị thay bằng hàm báo lỗi),
    "test_a_rewrite_refused_over_a_wide_change_sends_the_agent_to_read_instead": lời từ chối vẫn
    nêu bản mới nhất và ai viết, rồi bảo đọc bản mới nhất thay vì xem phần khác biệt, cũng không so
    dòng nào, "test_a_change_just_inside_the_limit_is_still_compared_and_quoted": chỗ đổi trải
    đúng `MIDDLE_LINES` dòng vẫn được so và trích, cả khi sửa lẫn khi bị từ chối viết lại,
    "test_a_diff_is_drawn_off_the_thread_that_serves_every_conversation": diff được vẽ đúng một
    lần, trên một luồng khác luồng của vòng lặp sự kiện, ở cả `artifact_edit` lẫn
    `artifact_rewrite`). Số dòng của các ca lấy từ chính `MIDDLE_LINES` chứ không chép con số 600,
    và luồng được đo bằng định danh luồng chứ không bằng thời gian, nên các test neo vào việc "quá
    rộng thì không so" và "so thì không chiếm vòng lặp", không neo vào một ngưỡng hay một tốc độ.
    Ghi chú canvas dùng chung ngưỡng này (`tests/test_canvas_note.py`)
- **Canvas: lượt sau không mang lại chữ mà lượt trước đã ghi vào canvas**
  - pytest: `tests/test_canvas_payload_trim.py`
    ("test_a_steer_mid_turn_leaves_the_document_the_turn_wrote_whole",
    "test_a_child_told_to_conclude_still_sees_the_document_it_wrote",
    "test_an_earlier_turns_frame_and_edits_leave_notes_of_where_their_text_went": id, tiêu đề, loại
    và `old` ngắn giữ nguyên còn kho giữ mọi chữ, lần ghi thất bại để lại ghi chú chưa lưu gì,
    "test_a_write_cut_off_mid_call_leaves_a_note_to_look_before_writing_again",
    "test_a_turn_resumed_after_an_approval_keeps_the_document_it_wrote_before", lời gọi chưa có kết
    quả và mọi tin khác đi qua nguyên vẹn, đúng là object cũ, kết quả lạc hay `content` không phải
    chuỗi không làm hỏng lượt nào, ranh giới lượt nằm ở tin cuối cùng trước lượt, id dùng lại được ghép với kết quả theo sau nó, lời gọi của lượt này dưới id cũ không
    nhận kết quả của lời gọi trước, lượt bắt đầu ở chỗ run đang chạy bắt đầu hoặc sau tin cuối,
    "test_a_file_carried_in_or_out_by_an_earlier_turn_passes_on_as_the_call_was_made": lời gọi
    `artifact_import` và `artifact_export` của lượt trước đi qua nguyên vẹn, đúng là object cũ, dù
    đường dẫn hay tiêu đề dài, vì chúng không mang chữ của tài liệu,
    "test_every_canvas_tool_argument_that_carries_document_text_is_trimmed": xét cả bảy tool,
    "test_a_note_is_always_shorter_than_the_text_it_stands_for")
- **Canvas: lượt không ghi được canvas được báo trước trong system prompt**
  - pytest: `tests/test_canvas_prompt_tail.py`
    ("test_a_turn_that_cannot_write_a_canvas_is_told_so_with_the_same_tools": lượt API, con có
    chuỗi bắt đầu từ API và con của chuỗi không có gốc nghe mục này, sau ghi chú ngày và ngay
    trước dòng ngày, cùng bộ tool; web chat và con của nó thì không,
    "test_an_api_turn_in_a_childs_own_conversation_is_told_the_channel_is_closed": lượt API trong
    cuộc trò chuyện của con nghe mục này đúng một lần và không nghe lời dặn của lượt vắng mặt, dù
    chuỗi bắt đầu từ web chat, Telegram hay job,
    "test_the_note_names_only_the_canvas_writes_the_agent_holds": agent chỉ có `artifact_import`
    và `artifact_export` được nhắc đúng một tên `artifact_import`, agent chỉ xuất và đọc thì không
    có mục này, "test_the_standing_prompt_has_no_canvas_note": prompt thường trực không có mục
    này, "test_the_note_lists_exactly_the_tools_a_closed_channel_refuses": ở lượt API
    `artifact_import` bị từ chối và có tên trong mục, `artifact_export` vẫn ghi được tệp và không
    có tên, "test_the_refusal_names_no_channel_as_the_only_one_that_opens_a_canvas": lời từ chối
    không còn nói chỉ web chat mở được canvas)
- **Canvas: lượt Telegram và job ghi được canvas; system prompt của lượt có người đọc không
  ngồi ở web chat dặn khi nào nên tạo canvas và dòng nào gửi canvas kèm tin nhắn, mà không nói
  người đọc đang ở Telegram**
  - pytest: `tests/test_canvas_prompt_tail.py`
    ("test_a_turn_whose_reader_is_away_from_the_web_chat_is_told_how_a_canvas_reaches_them": lượt
    Telegram, job và con trong chuỗi bắt đầu từ đó nghe mục **Canvas** với lời dặn này, ở cùng
    chỗ với mục của kênh đóng, sau ghi chú trong ngày và ngay trước dòng ngày; prompt của lượt
    web chat là prompt đó bỏ đi mục này, đúng từng ký tự, cùng bộ tool; lượt job nghe đúng từng
    chữ lượt Telegram nghe; con của chuỗi API hay chuỗi không có gốc không nghe lời dặn này,
    "test_an_agent_that_writes_no_canvas_is_told_nothing_about_making_one": agent không giữ tool
    ghi canvas nào thì không có mục,
    "test_the_line_a_telegram_turn_is_taught_is_one_the_chat_sends_a_canvas_for": dòng
    `FILE: artifact:<id>` trong lời dặn, thay mã canvas vào, được đọc thành một canvas để gửi,
    "test_the_note_says_who_reads_then_when_a_canvas_is_worth_making_then_how_one_is_sent": lời
    dặn nói, theo đúng thứ tự, người nhận không ngồi ở web chat nên không thấy canvas, chỉ tạo
    canvas khi được dặn hay khi tài liệu dài và sẽ còn sửa tiếp, còn lại trả lời thẳng trong tin
    nhắn, rồi dòng `FILE: artifact:<id>` gửi canvas kèm tin nhắn,
    "test_the_note_never_says_its_reader_is_on_telegram": Telegram chỉ được nhắc hai lần, là một
    trong hai cách lượt được đọc và là điều kiện để dòng đó gửi canvas; job trên máy không có
    bot cũng nghe lời này nên nó không khẳng định người đọc ở Telegram)
  - pytest: `tests/test_telegram_canvas_turn.py`, qua vòng lặp và tool thật
    ("test_a_telegram_turn_writes_a_canvas_and_sends_it_as_the_file_its_reply_names": chat nhận
    lời của lượt, rồi tệp canvas, rồi danh sách canvas; canvas nằm trong kho dưới tên agent và
    gắn với cuộc trò chuyện của lượt,
    "test_a_job_writes_a_canvas_and_its_brief_names_it": brief mang danh sách canvas job đã ghi)
  - pytest: `tests/test_scheduler_reporting.py`
    ("test_a_job_that_wrote_a_canvas_and_answered_ok_is_not_pushed_and_keeps_the_canvas": job trả
    lời đúng `OK` sau khi ghi canvas thì Telegram không nhận gì và canvas vẫn ở trong kho)
- **Canvas: ghi chú canvas báo agent những gì đã đổi từ lần nó nghe gần nhất, cùng canvas đang
  mở và đoạn người chọn trên web**
  - pytest: `tests/test_canvas_note.py` (hội thoại không có canvas không lưu ghi chú, canvas agent
    chưa từng thấy được nêu một lần mà vẫn không viết lại được,
    "test_a_persons_edit_is_shown_as_a_diff_that_makes_the_new_version_seen", ghi chú không hiện
    trọn mọi thay đổi (bản của agent khác, dòng bị cắt, bản khôi phục) thì `artifact_rewrite` vẫn
    bị từ chối, người sửa tiếp sau một thay đổi đã báo thì diff từ bản đã báo còn `seen` đứng yên,
    bản đã báo không bị lần tự lưu kế tiếp gộp mất, sửa rồi hoàn tác thì không báo gì mà tính
    canvas là đã thấy, phần giữa đổi quá 600 dòng báo một dòng, tối đa ba diff và mới nhất trước,
    canvas không vừa được đếm và báo ở ghi chú sau,
    "test_a_note_never_outgrows_its_ceiling_and_counts_what_it_left_out", canvas dựng lỗi được báo
    một dòng còn canvas khác vẫn hiện, dựng ghi chú không ghi gì);
    `tests/test_canvas_note_focus.py` (canvas đang mở được nêu một lần cho mỗi lần mở, đoạn được
    chọn trích một lần rồi xoá, đặt theo dòng chỉ khi các dòng đó chứa đúng đoạn, đoạn chọn trên
    bản cũ nói bản nào mới nhất, trên bản đã gộp thì tìm trong bản mới nhất, vùng chọn sai dạng,
    rỗng, chỉ có khoảng trắng hay không có trong bản thì bị bỏ, canvas không phải chữ chỉ được nêu
    tên, canvas đang mở mà agent chưa thấy được nêu và báo là mới, tin từ Telegram, API, job hay
    agent con không nghe gì về canvas đang mở, canvas đang mở đứng đầu còn lại mới nhất trước);
    `tests/test_canvas_note_frame.py` (dấu mở, dấu đóng và ký tự xuống dòng trong canvas không đổi
    được khung ghi chú hay giả làm stub, chữ trích thoát mọi ký tự xuống dòng trừ LF, tiêu đề dài
    bị cắt và không đóng được ngoặc quanh nó); `tests/test_message_context.py` (tin, ghi chú và
    các dấu đã báo vào cùng một giao dịch, lỗi ở lúc chèn tin, cập nhật liên kết, cập nhật cuộc
    trò chuyện hay commit không để lại gì kể cả sau một commit khác, tin cho cuộc trò chuyện không
    tồn tại không đánh dấu gì, ghi chú dựng lỗi thì tin vẫn lưu không ghi chú và tin sau báo lại,
    giao từ hàng đợi lỗi thì hàng chờ còn nguyên, tin xếp hàng hay steer từ Telegram nghe thay đổi
    mà không nghe canvas đang mở còn từ web chat thì nghe cả hai, chỉ tin của người từ một nguồn
    mới có ghi chú); `tests/test_artifact_links.py` (ghi chú chỉ đánh dấu liên kết đã có, bản đã
    báo chỉ tiến và được giữ khỏi bị gộp, `seen` chỉ tiến từ đúng bản ghi chú diff từ đó, báo
    canvas đang mở thì đánh dấu đã báo và có thể xoá vùng chọn, canvas đang mở vẫn là đã báo tới
    khi canvas khác mở hay có đoạn mới được chọn); `tests/test_artifact_diff.py` (diff hiện đủ mọi
    dòng đổi mới là trọn; dòng bị cắt quanh chỗ đổi, dòng bỏ chỉ được đếm, hết chỗ cho thay đổi
    sau hay dòng thêm bị cắt cho vừa thì không trọn; phần giữa đã đổi đếm các dòng giữa hai đầu
    chung); `tests/test_canvas_note_prompt.py` (mọi lời gọi model của lượt đọc tin sau ghi chú
    trọn vẹn còn kho giữ nguyên chữ người viết, ghi chú của lượt trước thành cùng một stub, tin
    hàng đợi giao đọc ghi chú trọn trong lượt của nó, system prompt giống hệt dù ghi chú khác
    nhau, hội thoại không có canvas tới model đúng như đã lưu và cùng object, khung prompt gọi
    những gì canvas chứa, kể cả chữ ghi chú trích, là dữ liệu ở cả hai ngôn ngữ);
    `tests/test_canvas_fork.py` (mỗi tin chép giữ ghi chú của nó, nhánh liên kết những canvas gốc
    đã liên kết tới điểm rẽ mà chưa thấy, chưa đọc, chưa báo gì, canvas liên kết sau điểm rẽ bị bỏ
    còn cùng giây thì giữ, canvas đang mở ở gốc không mở ở nhánh, ghi chú đầu ở nhánh báo mỗi
    canvas là mới, nhánh chỉ đọc trang cuối vẫn không viết lại được);
    `tests/test_canvas_note_imports.py` (mỗi phần dựng ghi chú import được đầu tiên trong một
    trình thông dịch mới, phần ở tầng lưu trữ không kéo gói agent, tên nguồn web chat của ghi chú
    trùng tên nguồn của agent); `tests/test_canvas_note_app.py` (qua app với `fake:echo`: tin từ
    web lưu cùng canvas đang mở và diff, model đọc ghi chú trước tin, `/tool artifact_read` vẫn gọi
    được trong hội thoại có ghi chú)
- **Canvas qua REST: tạo, đọc, lưu, đổi tên, xoá; mọi lần ghi qua REST là của người**
  - pytest: `tests/test_api_artifacts.py`
    ("test_a_canvas_made_on_the_web_is_the_persons_and_reads_back_the_same", canvas tạo trong một
    hội thoại được chia sẻ và mở ở đó, hội thoại không có thì 404 và không tạo gì, web tạo được
    năm loại chữ chứ không tạo ảnh (`image`, `pdf`, rỗng hay viết hoa đều 422 và kho còn trống),
    schema của `kind` khớp `CREATABLE_KINDS`, tiêu đề kho từ chối là 422, quá trần là 413 nêu đúng
    trần của loại đó (trang html lớn hơn tài liệu) và không ghi gì, kho đầy là 507 nêu các canvas
    lớn nhất,
    "test_the_detail_is_one_version_whole_though_a_write_lands_between_its_reads", canvas không có
    là 404 ở mọi route, "test_a_save_without_a_real_base_version_is_422_and_writes_nothing": thiếu,
    `true` hay `0` đều bị từ chối, lưu trên bản cũ là 409 kèm bản mới nhất và không ghi gì, hai lần
    lưu trong một đợt gộp mà số bản vẫn tăng, đổi tên không thêm bản, danh sách mới nhất trước và
    lọc theo hội thoại hay tiêu đề, `limit` từ 1 tới 200); `tests/test_artifact_errors.py` (mỗi lời
    từ chối của kho ra đúng mã:
    "test_a_version_folded_away_is_404_with_the_newest_number_though_it_is_a_key_error", `KeyError`
    của id khác và `ValueError` bảng không nêu đi tiếp như lỗi thật, 409 đọc lại bản mới nhất chứ
    không dùng bản lúc xung đột, canvas bị xoá giữa chừng là 404, 413 nêu cỡ và trần,
    "test_full_storage_is_507_naming_the_three_largest_canvases_biggest_first", 422 mang lời của
    kho, kể cả khi byte gửi lên không phải ảnh hay chữ có nửa ký tự Unicode)
- **Canvas qua REST: chỗ các canvas đang chiếm (`GET /api/artifacts/usage`)**
  - pytest: `tests/test_api_artifacts_usage.py`
    ("test_usage_adds_up_every_version_of_every_canvas": `bytes` và `by_artifact` cộng mọi phiên
    bản chứ không chỉ bản mới nhất, chữ tính theo byte chứ không theo ký tự, ảnh tính cùng chữ,
    `cap` là trần chung của kho,
    "test_a_deleted_canvas_gives_its_room_back",
    "test_usage_with_no_canvas_is_nothing_under_the_same_ceiling": kho rỗng trả `count` 0, `bytes`
    0, `by_artifact` rỗng và vẫn nêu trần,
    "test_usage_is_not_read_as_the_id_of_a_canvas": route khai báo trước `/artifacts/{id}` nên
    "usage" không bị đọc thành mã canvas; từ khác ở chỗ đó vẫn là 404 và canvas thật vẫn đọc được,
    "test_usage_counts_the_canvases_a_list_is_too_short_to_return": 201 canvas thì danh sách dừng
    ở 200 còn `count` là 201)
- **Canvas qua REST: lịch sử phiên bản, khôi phục và chữ thô không chạy gì**
  - pytest: `tests/test_api_artifact_history.py` (phiên bản mới nhất trước và không kèm chữ, một bản
    đọc trọn, bản đã gộp là 404 kèm số bản mới nhất, canvas không có là 404 ở mọi route lịch sử,
    "test_a_restore_writes_the_old_version_as_the_persons_newest": ghi chú `restore:<n>`, số bản
    khôi phục phải là số nguyên thật, "test_the_raw_text_is_plain_text_that_runs_nothing": `raw` của
    canvas chữ là `text/plain` sandbox kèm `nosniff`, CORP và một chính sách `frame-ancestors`
    riêng dù canvas chứa HTML, chữ thô của một bản cũ,
    "test_a_page_is_shown_and_saved_as_text_and_never_as_a_page" (khi xem lẫn khi tải về),
    "test_a_drawing_is_shown_as_an_image_that_downloads_and_is_saved_as_text": svg khi xem là
    `image/svg+xml` tải về (tên `.svg.txt`) còn khi lưu là chữ, mermaid là chữ `.mmd`,
    "test_a_picture_goes_out_as_its_own_bytes_under_the_type_they_give": ảnh ra đúng từng byte
    dưới kiểu PNG, JPEG, GIF hay WebP mà byte cho, chi tiết của ảnh có `content: null`, bản cũ của
    ảnh kèm byte và kiểu của chính nó,
    "test_a_download_is_named_after_the_title_in_any_script"); `tests/test_artifact_filenames.py`
    ("test_a_file_name_keeps_the_title_in_any_script_without_what_a_file_system_refuses",
    "test_a_file_name_ends_in_the_extension_of_its_kind": markdown là `.md`, code theo ngôn ngữ, ngôn
    ngữ lạ là `.txt`, code `html`, canvas html và svg là `.html.txt`, `.svg.txt` để mở tệp tải về
    chỉ thấy chữ, không chạy script, mermaid là `.mmd`; ảnh lấy đuôi từ byte của nó và `.bin` khi
    byte không cho đuôi nào, còn byte không bao giờ đổi tên của loại chữ,
    "test_an_extension_names_the_first_language_that_saves_under_it": bảng ngược
    `LANGUAGE_BY_EXTENSION` phủ đúng các đuôi của `CODE_EXTENSIONS` và mỗi đuôi trả về ngôn ngữ
    lưu ra chính đuôi đó)
- **Canvas qua REST: đọc lại tệp nguồn trong workspace (`POST /api/artifacts/{id}/reimport`)**
  - pytest: `tests/test_api_artifact_import.py`
    ("test_a_changed_file_becomes_the_persons_newest_version_marked_as_an_import": tác giả `user`,
    ghi chú `import`, `conversation_id` rỗng, nguồn giữ nguyên, trả `{changed, artifact}` không kèm
    chữ, "test_a_file_that_changes_nothing_adds_no_version": tệp chỉ khác BOM và kiểu xuống dòng
    vẫn là không đổi, "test_a_reimport_must_say_which_version_the_panel_loaded": thiếu
    `base_version`, 0 hay chuỗi là 422,
    "test_a_file_never_goes_over_a_version_saved_since_the_panel_loaded": `base_version` cũ mà tệp
    khác bản mới nhất là 409 kèm `head_version`, chữ và tác giả của bản đó; cũ mà tệp bằng bản mới
    nhất là 200 `changed: false`,
    "test_a_save_made_while_the_file_was_read_is_what_the_file_is_compared_with": bản mới nhất được
    đọc sau khi tệp đã trong tay,
    "test_a_picture_is_compared_and_replaced_byte_for_byte");
    `tests/test_api_artifact_import_scope.py`
    ("test_a_reimport_links_no_conversation_and_makes_nothing_seen": bản mới không thuộc cuộc
    trò chuyện nào dù canvas đã liên kết,
    "test_the_request_picks_neither_the_file_nor_whose_version_it_becomes": `path`, `source`,
    `conversation_id`, `kind`, `author`, `note`, `content` trong body đều không có tác dụng,
    "test_no_request_of_the_web_gives_a_canvas_a_source": tạo, lưu, đổi tên kèm `source` vẫn để
    nguồn rỗng nên nhập lại là 422,
    "test_a_reimport_is_announced_only_when_it_changed_the_canvas": không đổi thì không có event,
    đổi thì một event `artifact` tới các hội thoại đã liên kết);
    `tests/test_api_artifact_import_refusals.py` (lời từ chối nào cũng không ghi gì và không lộ
    đường dẫn của máy: "test_a_canvas_that_names_no_workspace_file_is_422": không nguồn, nguồn là
    URL, `workspace:` thiếu agent hay thiếu đường dẫn, "test_a_canvas_that_is_not_there_is_404",
    "test_a_canvas_deleted_while_its_file_was_read_is_404",
    "test_a_source_whose_agent_left_the_crew_is_410", "test_a_source_file_that_is_gone_is_410",
    "test_a_source_outside_the_workspace_is_403_in_words_for_a_person": `..`, đường dẫn tuyệt đối
    và `~` ra ngoài workspace nhận `FILE_OUTSIDE_WORKSPACE`,
    "test_a_file_that_cannot_be_a_version_of_the_canvas_is_refused_by_the_canvas_kind": quá trần
    là 413, không phải UTF-8 hay có byte NUL là 422, canvas ảnh mà tệp không phải ảnh là 422, thư
    mục là 422, "test_a_source_that_became_a_pipe_is_422_without_waiting_for_a_writer": request
    không treo, "test_a_page_of_another_site_cannot_ask_for_a_reimport": `Sec-Fetch-Site`
    `cross-site` hay `same-site` là 403, "test_full_storage_is_507_and_the_canvas_stays")
- **Canvas qua REST: trang chạy trong sandbox, không có đường nào ra ngoài**
  - pytest: `tests/test_artifact_render.py` (chính sách viết ra nguyên văn trong test nên đổi nó là
    đổi cả tệp này; `sandbox` chỉ có `allow-scripts`, không bao giờ `allow-same-origin`; chỉ
    `frame-ancestors` nhắc `'self'`; `default-src`, `connect-src`, `form-action` và `base-uri` là
    `'none'`, `img-src` và `media-src` chỉ có `data:` và `blob:`, không nguồn nào là `*`, `http:` hay
    `https:` trần, `webrtc` bị chặn; thư viện của trang mermaid nằm trong `script-src`;
    "test_a_page_goes_out_with_the_headers_of_a_page_that_runs_and_no_others": hai header
    `Content-Security-Policy` (chính sách rồi `frame-ancestors`), `text/html`, `nosniff`,
    `no-referrer`, `no-store` và không header nào khác ngoài `content-length` và `vary` của lớp nén;
    canvas html ra đúng trang của nó kèm reporter, mermaid ra trang vẽ nguồn của nó, bản mới nhất
    khi không hỏi bản nào, `version` bằng 0, âm hay không phải số là 422; markdown, code, svg và ảnh
    là 404 `NOT_A_PAGE` kể cả khi kèm `version`, canvas không có là 404, bản đã gộp hay chưa có là
    404 kèm số bản mới nhất; địa chỉ chỉ nhận `GET`, các method khác là 405 và không ghi gì);
    `tests/test_render_pages.py` (reporter đứng ngay sau doctype mở đầu trang, sau cả BOM, khoảng
    trắng và chú thích, và đứng trên cùng khi trang không có doctype, bỏ nó đi thì ra đúng canvas;
    trình duyệt gặp doctype trước và reporter trước mọi script của trang; reporter không tự đóng
    được thẻ `script` của nó và là JavaScript cổ trong một hàm không để lại biến toàn cục, vì một
    trang không parse được thì không báo gì; một lời từ chối không phải `Error` (Mermaid từ chối sơ
    đồ không parse được bằng object thường `{str, message, hash}`) được báo bằng `message` của nó
    chứ không phải `[object Object]`;
    "test_the_reporter_hands_the_app_a_port_before_it_listens_for_anything": reporter mở một
    `MessageChannel`, giữ `postMessage` của đầu kênh nó giữ trong một biến cục bộ đã `bind`, gửi
    `canvas-hello` kèm đầu kia trong danh sách chuyển giao đúng một lần và trước mọi
    `addEventListener`, sau lời chào không còn chỗ nào nhắc tới `port1`;
    "test_a_browser_without_message_channels_still_reports_what_goes_wrong": mọi thứ về kênh nằm
    trong một `try` bốn dòng, phần báo lỗi nằm ngoài nó;
    "test_the_reporter_tells_of_a_press_only_when_the_browser_says_a_person_made_it": reporter nói
    `press` ở đúng một chỗ và chỉ khi `event.isTrusted === true` (đúng một lần đọc `isTrusted`), và
    không đọc `type` hay `detail` của sự kiện nào: hai thứ ấy là accessor trên prototype, trang viết
    lại được, nên cú bấm được nhận ra bằng listener nó tới chứ không bằng điều sự kiện tự nói;
    listener của nó trên `window` đúng là `pointerdown`, `mousedown`, `pointerup`, `mouseup` (cùng
    hàm ấy, pha capture) rồi `error`, `unhandledrejection`, `securitypolicyviolation`, không có
    `focus`, `pointermove`, `wheel` hay `keydown` là những sự kiện trang tự khiến trình duyệt bắn ra
    được, và không có `click`, cái mà Enter hay phím cách người gõ cho app tạo ra trên một nút của
    trang đã giành bàn phím;
    "test_the_hello_is_no_report_and_counts_against_none": lời chào không tính vào hai mươi lời báo;
    "test_the_work_on_a_page_does_not_grow_with_the_square_of_what_it_holds": hai đầu vào mà bản cũ
    tốn hàng giây hoặc vô tận (28 chú thích liền nhau trước một doctype không có, 64.000 khoảng
    trắng trong sơ đồ có rào) phải xong dưới 0,5 s, vì cả hai chạy trên event loop; sơ đồ đóng
    `</pre>` rồi mở `<script>` và tiêu đề đóng `</title>` đều ra thành chữ; một rào ba dấu huyền bọc
    cả sơ đồ thì bỏ, mọi trường hợp khác giữ nguyên; thư viện là một phiên bản ghim kèm băm và
    `crossorigin`, `securityLevel: "strict"` và `startOnLoad: false`; sơ đồ không parse được không
    bị trang nuốt: `run()` đứng một mình, không `try`, `catch`, `finally`, `await` hay `.then`, nên
    lời từ chối của nó tới reporter, và bỏ lời gọi đó thì không sơ đồ nào được vẽ; không có thư viện
    thì có dòng báo ở trên nguồn; trang là tài liệu đủ bộ và reporter đứng trước mọi thứ nó tải);
    `tests/test_render_fixtures.py` (`web/e2e/render-policy.txt` và `web/e2e/frame-reporter.js`, hai
    tệp mà test trình duyệt đọc, bằng `render_csp()` và `REPORTER_JS` từng byte; sửa một bên mà quên
    tệp thì test đỏ); `tests/test_local_guard.py`
    ("test_only_the_render_page_of_a_canvas_is_open_to_a_request_from_elsewhere": với
    `Sec-Fetch-Site` là `cross-site` hay `same-site`, địa chỉ render trả 200 còn canvas, `raw`,
    `versions`, danh sách, `/render/`, `/render/x`, `/render%0A` và `a%2Fb/render` đều 403; Origin
    lạ và host lạ vẫn bị từ chối)
- **Canvas đang mở trên web: đặt, đọc, đóng; mở là chia sẻ với hội thoại**
  - pytest: `tests/test_api_canvas_focus.py` (đặt rồi đọc lại cùng vùng chọn, `null` là đóng, vùng
    chọn không kèm canvas là 422, mở canvas agent chỉ đọc thì chia sẻ nó, canvas chưa liên kết được
    liên kết chia sẻ và chưa thấy,
    "test_a_canvas_opened_on_the_web_reaches_the_agents_the_conversation_delegates_to",
    "test_a_selection_the_note_would_drop_is_422_and_nothing_changes": `true`, chỉ khoảng trắng, bản
    sau bản mới nhất, dòng cuối trước dòng đầu, chữ quá 20.000 ký tự,
    "test_a_selection_may_reach_twenty_thousand_characters", hội thoại hay canvas không có là 404)
- **Mỗi tin chat mang canvas đang mở ở tab gửi nó**
  - pytest: `tests/test_api_chat_canvas.py`
    ("test_a_message_names_the_canvas_open_in_the_tab_that_sent_it": thiết bị khác vừa mở canvas
    khác cũng không đổi điều tin nêu, tin trích đoạn được chọn, tin không mang `canvas` giữ canvas
    đang mở, tin từ tab không mở canvas thì đóng nó,
    "test_a_message_with_a_selection_the_note_would_drop_is_422_and_goes_nowhere", cổng từ chối (chờ
    duyệt, hội thoại không có) thì canvas đang mở không đổi, tab hiện canvas đã xoá vẫn gửi được và
    đóng nó, "test_a_queued_message_names_its_canvas_when_it_is_delivered",
    "test_the_open_canvas_is_named_once_while_messages_keep_carrying_it",
    "test_a_queued_ask_keeps_its_passage_until_it_is_delivered": tin hỏi về một đoạn mà bị xếp hàng
    giữ vùng chọn tới lúc giao, ghi chú giao đi trích đúng đoạn ấy,
    "test_a_queued_ask_loses_its_passage_to_a_later_message_from_the_same_tab": giới hạn đã biết, ghi
    chú của tin xếp hàng dựng lúc giao theo canvas đang mở khi ấy, nên tin sau từ cùng tab, đã xoá
    vùng chọn, làm tin trước mất đoạn)
  - vitest, tab nêu canvas nào trong tin: `web/src/api/client.test.ts` ("carries the tab's canvas only
    when it is given, and a null one as it is": thân POST là `{text}` khi không có canvas, `{text,
    canvas}` khi có, kể cả `{artifact_id: null}`); `web/src/hooks/use-canvas-dock-focus.test.ts` nhóm
    "the canvas a message names" (chưa mở canvas nào ở tab này thì không nêu gì, mở rồi thì nêu canvas
    ấy không kèm đoạn chọn, canvas mới nhất vừa mở và canvas tạo tại đây ngay từ lúc tạo; đóng trên
    màn rộng là `null` dù đóng bằng `close`, `forceClose` hay `toggle`, còn lớp phủ của màn hẹp dẹp đi
    thì vẫn nêu canvas; theo bề rộng lúc đóng chứ không lúc mở; về danh sách vẫn nêu canvas, việc đóng
    đang chờ một lần lưu chưa xong cũng vậy; sang hội thoại khác thì trống và không quay lại theo
    người; đọc qua tham chiếu lấy từ trước vẫn thấy giá trị lúc hỏi);
    `web/src/hooks/use-thread.test.ts` nhóm "the canvas a send carries" (canvas đi theo POST của tin
    gửi thường và của tin xếp hàng sau lượt đang chạy ở tab này; bảng "%s on a plain send is told in
    Vietnamese, in the result and in the notice", gửi tin mang một đoạn chọn, cho 422 là đoạn chọn
    không còn khớp, 409, 429, 500 và mất kết nối: `error` của kết quả luôn là câu của ta, thông báo
    giữ câu của server ở 429 và nói máy chủ lỗi ở 5xx, bong bóng tạm biến mất; ba lỗi 422, 429 và mất
    kết nối của tin xếp hàng cũng vậy; hai bảng "a 422 for a plain send with %s is not told as a
    passage that no longer fits" và "a 422 for a send queued behind this tab's turn with %s is not
    told as a passage either" cho tin nêu canvas mà không mang đoạn chọn nào — `selection: null`,
    không có trường `selection`, và canvas đang đóng: kết quả là câu chung "chưa gửi được" còn thông
    báo giữ lời của server, vì không đoạn nào của người bị từ chối;
    "keeps the old wording of a 422 for a message that carried no canvas");
    `web/src/lib/error-text.test.ts` nhóm "turnErrorText" (409 là hội thoại chờ quyết định dù server
    viết gì, 422 của tin mang đoạn chọn là đoạn chọn không còn khớp, lỗi khác để `errorText` lo dù
    tin có đoạn chọn hay không); `web/src/lib/send-result.test.ts` ("words a 422 as the selection only
    when the message carried a selection of the canvas"; `sendErrorText` đổi nghĩa chỉ của 422 và chỉ
    khi tin mang đoạn chọn, lời server bằng tiếng Anh không bao giờ tới người dùng)
- **Tin gửi đi cùng ghi chú canvas thì tab gửi nhận lại đúng ghi chú ấy ngay đầu luồng và hiện nó
  thành một chip dưới tin; mở lại cuộc trò chuyện vẫn thấy chip**
  - pytest: `tests/test_user_context_event.py`
    ("test_the_first_event_of_a_turn_is_the_note_its_message_was_stored_with", event chỉ có `type`
    và `context`, không mang id tin; tin lưu không có ghi chú, lượt không nhận tin mới và tin server
    xếp hàng (chỉ nhận `queued`) đều không có event này;
    "test_the_activity_hub_neither_writes_nor_broadcasts_it": tab khác đang xem không thấy ghi chú
    của người gửi; "test_a_reply_reads_the_same_with_the_note_in_the_chain_or_without_it";
    "test_it_cannot_be_changed_once_it_is_made": một event đi qua luồng, bộ lọc của hub và câu trả
    lời kênh chat gom lại, nên không chỗ nào được sửa ghi chú của chỗ sau; qua API thì là khối SSE
    đầu tiên và mang đúng đoạn người đã chọn)
  - vitest: `web/src/state/thread-reducer.test.ts` (tin lưu cùng ghi chú mang ghi chú, tin lưu không
    có hay có ghi chú rỗng thì không có khoá `context`; event `user_context` gắn ghi chú vào tin người
    mới nhất dù nó đứng đâu trong thread, và để yên thread khi chưa có tin người nào);
    `web/src/state/activity-reducer.test.ts` (luồng hoạt động của tab khác không nhận gì từ ghi chú
    của tin); `web/src/hooks/use-thread.test.ts` ("reaches the bubble the send drew, off the stream
    of that send"; tin server không lưu ghi chú thì bong bóng giữ nguyên chữ người gõ);
    `web/src/components/canvas/canvas-note-chip.test.tsx` (chip gập lại và chưa có chữ nào của ghi
    chú trên màn hình, `aria-controls` chỉ có khi thân đang mở, mở rồi đóng lại, chữ trong ghi chú
    là chữ chứ không là markup, ký tự ẩn hiện thành dấu thấy được còn nút chép chép đúng bản gốc);
    `web/src/components/message-thread.test.tsx` ("the canvas note under a user message": chip nằm
    ngay dưới bong bóng của tin mang ghi chú và ngoài bong bóng, không có dưới tin không mang ghi
    chú hay dưới câu trả lời của agent, và chỉ dưới đúng tin của nó)
  - Playwright: `canvas-note.spec.ts` ("a message sent with a canvas note shows it as a chip, and
    still does once the page is loaded again": chip ngay sau bong bóng, mở ra thấy đúng ghi chú,
    tải lại trang vẫn còn; tin gửi không ghi chú thì không có chip; ở 390×844 và 1000×800 cảm ứng
    chip và nút chép đều ≥40px kể cả lúc đang mở, không cuộn ngang; ghi chú dài — 60 dòng, một dòng
    nhiều từ và một dòng 400 ký tự liền — mở ra vẫn xuống dòng trong bề rộng, cao dưới nửa màn hình
    và cuộn được bên trong)
- **Mọi thay đổi canvas tới web qua luồng hoạt động, kể cả lần ghi từ luồng khác; không lần đọc
  nào đổi trạng thái**
  - pytest: `tests/test_artifact_events.py` ("test_every_change_made_over_rest_is_announced": tạo,
    lưu, đổi tên, khôi phục và xoá, mỗi lần một event `artifact` kèm hội thoại liên kết,
    "test_a_canvas_an_agent_writes_with_its_tool_is_announced",
    "test_a_write_from_another_thread_reaches_the_watchers_loop": loop chạy ở chế độ debug, lần ghi
    từ luồng khác tới watcher trong 0,5 s mà không có lỗi nào; thiếu bước chuyển về loop thì test
    đỏ chứ không treo); `tests/test_api_artifact_invariants.py`
    ("test_every_canvas_route_and_the_chat_message_run_on_the_event_loop",
    "test_the_routers_checked_here_are_every_canvas_router_the_app_serves": router canvas nào
    của `app.ROUTERS` cũng nằm trong bộ được kiểm, kể cả router nhập lại,
    "test_no_read_changes_what_a_conversation_knows_or_has_open": mọi `GET` canvas, kể cả
    `usage` và trang `render` của canvas html và mermaid ở bản mới nhất lẫn một bản cũ, giữ
    nguyên liên kết, con trỏ đọc, canvas đang mở, phiên bản và tin)
- **Canvas trên web: trộn ba chiều theo dòng, giữ con trỏ trên đúng ký tự, diff lịch sử giữ mọi dòng**
  - vitest: `web/src/lib/diff-lines.test.ts` (dòng trống, khoảng trắng cuối dòng và xuống dòng cuối là
    dòng thật, đầu đuôi chung được cắt trước khi áp trần, quá trần là null);
    `web/src/lib/merge3.test.ts` ("merges two edits far apart in a long text under the default cap",
    viết lại các dòng sát một lần chèn là xung đột, hai bên cùng thêm cuối tệp là xung đột, sửa hai dòng
    liền nhau là xung đột, xuống dòng cuối của mỗi bên được giữ, sửa giống nhau không nhân đôi, xoá với
    sửa cùng dòng là xung đột, một bên quá trần là xung đột, "gives the server's changes in the person's
    line numbers"); `web/src/lib/line-edits.test.ts` (sửa ở hai phía con trỏ giữ đúng ký tự, thêm dòng
    cuối tệp không dời con trỏ ở dòng cuối, vị trí trong vùng thay về cuối đoạn thay, trong vùng xoá về
    chỗ vùng đó, không so được thì chỉ kẹp); `web/src/lib/canvas-diff.test.ts` (dòng bớt trước dòng
    thêm, đoạn không đổi dài thu còn ba dòng mỗi bên, kể cả sau một lần chèn ở dòng đầu, quá trần là
    null)
- **Canvas trên web: client REST, lời từ chối có cấu trúc, event canvas từ luồng hoạt động**
  - vitest: `web/src/api/artifact-client.test.ts` (danh sách mọi canvas, của một hội thoại hay theo
    tiêu đề, tạo trong hội thoại trả bản đầy đủ, mọi route dưới id đã mã hoá, signal và `keepalive`
    của lần lưu tới `fetch`, link chữ thô của bản mới nhất, của một bản và để tải về,
    "links the page of a canvas under an encoded id, with no version: the newest is the one shown",
    "sends the kind a canvas is made as, with the text it starts from", chi tiết của ảnh có
    `content: null`,
    "reads the server's version from a 409 that carries one, and from nothing else", 507 nêu dung
    lượng và các canvas lớn nhất, "tells a version that was folded away from a canvas that is
    gone"); `web/src/api/client.test.ts` ("keeps a structured error detail beside the message older
    callers read", detail dạng chữ vẫn là lời báo, luồng hoạt động chuyển cả event `artifact`);
    `web/src/hooks/use-activity.test.ts` ("hands an artifact payload to the canvas listeners and
    leaves the run state as it was"); `web/src/lib/artifact-events.test.ts` (một hàm đăng ký hai lần
    bỏ một lần vẫn nghe, "skips a listener removed during an event, and starts one added during it
    from the next")
  - vitest, server giả cho các test sau: `web/src/test/fake-canvas.test.ts` (số bản nối sau bản mới
    nhất, lưu trên bản cũ trả bản mới nhất, khe và bản đã gộp, khôi phục ghi `restore:<n>`,
    "checks a save the way the store does: the canvas, the body, the base, the size, then the
    room", kho đầy nêu ba canvas lớn nhất, route và method không có trả như router, danh sách gập
    tiêu đề như server và cùng giây thì canvas tạo sau đứng trước, từ chối, mất reply và giữ request
    hay reply đúng một lần, event mang hội thoại liên kết lúc đó và không bao giờ mang chữ,
    "refuses a keepalive body that would take the bytes in flight past 64 KiB, without sending it",
    request bị huỷ vẫn ghi phần việc đã bắt đầu, canvas chỉ liên kết với hội thoại có thật và event
    tới mọi luồng đang mở, "makes a canvas of every kind a person can make, with the text it is
    given", "keeps a picture as bytes with no text: its detail and versions say so, and a write of
    text is refused"). Mẫu canvas html, svg, mermaid và ảnh cho các test về loại nằm ở
    `web/src/test/fake-canvas-kinds.ts` (`SAMPLES`; ảnh không có chữ, server giả chỉ giữ cân nặng
    của nó và trả `content: null` như server thật)
- **Canvas trên web: tự lưu không mất phím gõ, mỗi lúc một lần lưu, thử lại khi mất reply, dừng khi
  server từ chối**
  - vitest, máy trạng thái thuần, không timer và không mạng: `web/src/lib/canvas-machine-save.test.ts`
    ("never has two saves in flight, whatever falls due and whatever comes back", gửi chữ kèm phiên bản
    nó được sửa từ đó rồi lấy reply làm base, chữ gõ trong lúc lưu được gửi khi lần lưu kia về, trần
    kích thước đo bằng byte UTF-8, thử lại sau 2, 5, 15, 30 giây rồi mỗi phút, 5xx như mất reply, "still
    sends the text when it went back to its base after a lost save, which may have landed", mỗi mã từ
    chối một test: 404 là đã xoá, 413 dừng tới khi chữ đổi, 507 giữ các canvas lớn nhất và dừng tới lần
    lưu tay, 422 và 4xx khác dừng tới lần lưu tay, 409 không kèm bản mới nhất không phải xung đột);
    `web/src/lib/canvas-machine-flush.test.ts` (`flush` trả phiên bản giữ chữ lúc gọi, không chờ phím gõ
    sau đó, chờ qua lần lưu đang bay mang chữ cũ, null khi xung đột, đã xoá, bị từ chối, lần lưu đầu
    mất, quá trần hay đang dừng); `web/src/lib/canvas-machine-size.test.ts` (trần theo loại canvas:
    markdown, code và mermaid 512 KB, html 4 MB, svg 2 MB; đúng trần thì gửi, hơn một byte thì dừng và
    nêu trần; html nhận 1 MB mà markdown thì không; loại lạ theo trần nhỏ nhất; đếm byte UTF-8 chứ
    không đếm ký tự; dừng vì cỡ được gỡ và quên trần khi chữ vừa lại, vẫn dừng khi chưa vừa, lưu tay hay
    khôi phục một bản cũng gỡ nó và quên trần; 413 nêu
    trần server nói và trần ấy thắng bảng, 413 không kèm trần thì dùng trần của loại, lần lưu xong
    thì không còn trần nào); `web/src/lib/canvas-machine-slow.test.ts` (lần lưu hết hạn mà không reply
    là mạng chậm chứ không phải mất: thử lại sau hai giây, chữ ấy còn tính là có thể đã tới server,
    trạng thái "slow" khi máy có mạng và "offline" khi không, lần thử lại gửi đúng chữ và trạng thái
    vẫn là "slow" tới khi một lần lưu về, bỏ qua lần lưu theo giờ hay lúc mất focus trong lúc chờ,
    chờ lâu dần như lần lưu mất, phân biệt với lần lưu mất ở lần kế, một lần lưu về thì thôi nói mạng
    chậm, flush đang chờ được trả null, 409 mang chữ của lần hết hạn là của chính mình, lần thử lại
    thấy đúng chữ ấy trên server thì coi là đã lưu, canvas bị xoá lúc lần lưu đang bay thì hết hạn cũng
    không đặt lần thử lại nào, không có lần lưu nào bay thì bỏ qua);
    `web/src/lib/canvas-caps.test.ts` (trần từng loại, tên lạ hay tên của prototype theo trần nhỏ
    nhất, độ dài tin chat là 20000, đếm byte UTF-8 của chữ một, hai, ba và bốn byte, `fits` đúng trần
    và hơn một byte của từng loại, chữ hai byte có số ký tự nhân ba vượt trần mà đo byte vẫn vừa, mỗi
    loại một trần riêng)
  - pytest: `tests/test_web_caps.py` (bảng trần của web khớp bảng của server theo từng loại, và giới
    hạn độ dài tin của web khớp route chat; một bên đổi một mình thì hỏng ở đây)
- **Canvas trên web: theo kịp server và nháp trên máy; event của chính mình không đọc lại, bản mới được
  trộn, xung đột giữ cả hai phía**
  - vitest: `web/src/lib/canvas-machine-sync.test.ts` ("reads nothing when its own save's event comes
    before or after the reply", "does not call text saved when the agent wrote a newer version during
    the save", đổi tên và xoá khi đang lưu, "puts off a read asked for during a save, and never sends
    older text after it", hai bản nối nhau mỗi bản một lần đọc, lần lưu mất reply mà đã tới server được
    nhận làm base; mở với nháp: nháp bằng bản mới nhất thì bỏ, nháp trên bản mới nhất thành chữ chưa
    lưu, nháp trên bản cũ được trộn, sửa cùng dòng là xung đột, "takes the person's own save that was
    out when the page closed, and keeps what they typed after it", "does not take a version the agent
    wrote with the same words for the person's own save"); `web/src/lib/canvas-machine-conflict.test.ts`
    (409 của chính lần lưu mất reply là base chứ không phải xung đột, phím gõ trong lúc lưu được trộn,
    "merges again when the merged save meets yet another version, and loses nothing", `keepMine` và
    `loadTheirs` rồi lấy lại chữ của mình được cho tới khi gõ, 409 giữa lúc soạn IME chờ
    `compositionend`, khôi phục đặt chữ và base không chờ luồng; "ends on the newest version when it
    loads theirs while a newer one is being read": bấm "Nạp bản mới" lúc lần đọc bản mới hơn nữa
    đang bay thì lần đọc đó không được áp vào chữ vừa thay, máy hỏi đúng một lần đọc nữa, không có
    lần thứ ba, và canvas dừng ở bản mới nhất với trạng thái đã lưu; "reads at once when it loads
    theirs knowing of a newer version that no read is out for": lần đọc trước đó hỏng thì "Nạp bản
    mới" hỏi đọc ngay; nạp đúng bản mới nhất đã nghe tới thì không đọc gì; "ends on a version
    written over the restore, whose read was out when the restore's reply came" và "reads at once
    after a restore under a version it has heard of, when no read is out": khôi phục cũng vậy, còn
    khôi phục thành bản mới nhất thì không đọc gì); `web/src/lib/canvas-draft.test.ts`
    (nháp chỉ của đúng canvas, xoá khoá cũ trước khi ghi nên kho đầy không để lại nháp, trình duyệt từ
    chối thì báo và tab giữ nháp, "clears a draft only while it still holds the text that was saved",
    giữ mười nháp mới nhất, bỏ nháp quá ba mươi ngày và nháp hỏng; hết quota thì bỏ nháp cũ nhất từng
    cái một cho tới khi vừa, mục không phải nháp đi trước, và dọn hết vẫn không vừa thì mọi nháp khác
    được trả lại nguyên byte, không đụng gì khác khi lần ghi vừa; nhóm "a draft the browser refused,
    held in this tab": nháp của tab được đọc trước nháp tab khác đã lưu, đi khi trình duyệt giữ được
    hay khi không còn gì để giữ (trình duyệt chặn lưu trữ không biến việc đó thành lỗi), `clearDraft`
    xoá từng bản theo chữ của chính bản đó, trang hỏi trước khi đóng tới khi nháp cuối cùng đi; nhóm "a
    draft the browser refuses again and again": mười lần dừng gõ chỉ hỏi trình duyệt một lần và nháp
    của canvas khác chỉ bị lấy ra rồi đặt lại một lần, thử lại khi nháp nhẹ hơn (chữ ngắn hơn, hay
    bản gốc ngắn hơn mà chữ vẫn dài như cũ: "is tried again once the version it was edited from is
    shorter, its own text no shorter") hay khi một nháp đã lưu bị xoá, một nháp nhẹ hơn đã được giữ thì
    cỡ từng bị từ chối cũng được thử lại ("is tried again at the size refused once a smaller one was
    kept"), xoá nháp chỉ có ở tab thì không thử lại, không cản nháp của canvas khác, trình duyệt
    chặn hẳn lưu trữ thì không bị nhớ, và `console.error` khi nháp lấy ra không đặt lại được);
    `web/src/lib/local-store.test.ts` (liệt kê khoá theo tiền tố, lần ghi báo có được giữ không khi
    trình duyệt từ chối hay hết quota)
- **Canvas trên web: nháp mà trình duyệt từ chối vẫn còn trong tab cho tới khi một bản giữ chữ**
  - vitest, cả App trên `FakeCanvas` với trình duyệt chặn lưu trữ: `web/src/app-canvas-tab-draft.test.tsx`
    (chữ gõ còn nguyên khi mở lại canvas sau lần đóng mà cả hai lần lưu đều 500, sau lần đóng mà lần
    lưu để lại gặp 409 của người khác, và sau khi đổi cuộc trò chuyện; lần lưu kế gửi đúng chữ đó;
    trang hỏi trước khi đóng suốt lúc ấy, thôi hỏi khi một bản đã giữ chữ hay canvas bị xoá, vẫn hỏi
    và vẫn giữ chữ khi người khác chỉ lưu thêm một bản của canvas ("is still asked about when someone
    else only saves its canvas anew, and is there on the way back"), và không hỏi gì khi lần lưu để
    lại hạ cánh)
- **Canvas trên web: nháp chỉ còn trong tab được tự lưu khi mở lại canvas, và lời báo chưa lưu đi khi
  lần lưu hạ cánh**
  - vitest, cả App trên `FakeCanvas`: `web/src/app-canvas-held-draft.test.tsx` (trình duyệt chặn lưu
    trữ: mở lại canvas sau lần lưu để lại hỏng thì chữ được gửi 1,5 giây sau, không sớm hơn một mili
    giây và không cần phím nào, rồi dòng trong luồng chat, dòng "Không giữ được bản nháp trên máy này"
    trong panel và câu hỏi trước khi đóng trang đều đi; rời canvas ngay sau khi mở lại cũng lưu và
    dòng trong luồng chat đi; nháp đã trộn với bản mới hơn lúc mở lại, lưu tay xong thì trang thôi
    hỏi; canvas vẫn mở thì dòng trong panel chỉ còn tới khi lần lưu hạ cánh và hiện lại khi chữ kế
    cũng bị từ chối; trình duyệt giữ được nháp thì mở lại chỉ hiện nháp, 60 giây không gửi gì, dòng
    trong luồng chat ở lại và đi khi người tự lưu)
  - vitest, runner trên `FakeCanvas` với đồng hồ giả: `web/src/lib/canvas-runner-held-draft.test.ts`
    ("saves the draft by itself, as long after it opened as after a keystroke"; cờ nháp hỏng bật khi
    nháp được ghi lại sau 0,3 giây và tắt khi lần lưu hạ cánh; nháp trộn được thì lưu đúng chữ đã trộn
    trên bản vừa trộn; lưu tay trước khi nháp được ghi lại thì tab không còn giữ gì; nháp xung đột với
    bản mới nhất thì không gửi gì, vẫn giữ và trang vẫn hỏi; lần đọc đầu hỏng thì lần đọc sau mang
    nháp về và tự lưu; runner bị thả ngay lúc lần đọc đầu về thì không đặt lần lưu nào; nháp trình
    duyệt đã giữ thì chỉ hiện, 60 giây không gửi gì cho tới khi người lưu hay gõ);
    `web/src/lib/canvas-runner-tab-draft.test.ts` (nháp tab giữ của canvas đang mở: đi khi lần lưu đã
    trộn với bản của người khác hạ cánh dù nháp còn mang chữ trước khi trộn, ở lại khi chữ gõ sau lúc
    lần lưu đi còn chưa lưu, đi khi một lần đọc cho thấy lần lưu mất reply đã hạ cánh);
    `web/src/lib/canvas-machine-sync.test.ts` ("drops the draft of a lost save a read shows landed, by
    the text that landed"); `web/src/lib/canvas-draft-held.test.ts` (`heldInTab` chỉ đúng với canvas
    mà trình duyệt từ chối nháp và thôi đúng khi nháp sau được giữ; `dropFromTab` bỏ nháp của tab dù
    chữ gì, trang thôi hỏi khi đó là nháp cuối và vẫn hỏi khi tab còn giữ nháp của canvas khác, không
    đụng nháp tab khác đã lưu, không làm gì với canvas tab không giữ nháp)
  - vitest, lời "canvas không còn gì chưa lưu": `web/src/lib/canvas-handoff-saved.test.ts` (tới khi
    lần lưu để lại hạ cánh, không tới khi nó hỏng, không tới khi một nháp của chữ gõ sau đó còn sống
    lâu hơn lần lưu ấy ("does not come when the save that lands is outlived by a draft of words typed
    since") và tới khi lần lưu giữ đúng chữ của nháp; runner đã thả chỉ báo một lần, từ lần lưu để
    lại; canvas đang mở báo khi lần lưu hạ cánh mà không gõ gì thêm, không báo khi còn chữ gõ sau lúc
    lần lưu đi hay khi đang xung đột; mỗi lượt đăng ký nghe riêng và thôi nghe riêng);
    `web/src/hooks/use-canvas-chat-notices.test.ts` (dòng về lần lưu hỏng đi khi canvas ấy được lưu,
    dù nháp còn trên máy hay chỉ trong tab, còn dòng của canvas khác ở lại; đi khi lần lưu để lại sau
    đó hạ cánh; danh sách vẫn là chính nó khi canvas được lưu chưa từng bị nhắc tới; hiện lại khi lần
    lưu sau lại hỏng; nút ẩn vẫn cất như cũ)
- **Canvas trên web: canvas đang mở lưu 1,5 giây sau phím cuối, rời đi vẫn lưu nốt, keepalive chỉ khi
  vừa trần**
  - vitest, hook trên `FakeCanvas` với đồng hồ giả: `web/src/hooks/use-canvas.test.ts` ("saves once,
    1.5 s after the last of thirty keystrokes and not a moment sooner", Cmd/Ctrl+S lưu ngay và không lưu
    lại khi hết lúc dừng gõ, sửa mà chữ không đổi không lùi lần lưu, "says so when this device cannot
    keep the draft, until it can again", canvas 100 KB ẩn tab hay tháo panel đi bằng request thường và
    nháp giữ phím gõ ngay trước, canvas 10 KB tháo panel thì một `PUT` keepalive đúng base, "forgets the
    draft of a canvas deleted while open once its panel goes", trang hỏi trước khi đóng chỉ khi chữ
    chưa lưu mà máy cũng không giữ được nháp, thôi hỏi khi chữ đã lưu hay đã về bản gốc, và vẫn hỏi
    sau khi panel đi cho tới khi lần lưu để lại hạ cánh);
    `web/src/hooks/use-canvas-switch.test.ts` ("shows the next canvas at once and finishes the last
    one's save behind it", thử lại đang chờ được thử thêm một lần khi rời rồi dừng, ẩn tab lúc canvas
    sau đang tải không lưu gì cho nó, "lets a canvas left behind finish its save without reading it
    again or showing it", cờ nháp hỏng không theo sang canvas sau);
    `web/src/hooks/use-canvas-sync.test.ts` (đọc lại khi luồng nối lại sau lần rớt mà không đọc lúc mới
    nối, khi tab hiện, khi event báo bản mới; "ends on the newest version when the newer one is
    loaded while a read of one newer still is out": với server giả, xung đột đang đứng ở v2, v3 được
    báo và lần đọc nó bị giữ lại, bấm "Nạp bản mới" rồi thả lần đọc thì hook đọc thêm đúng một lần
    (ba `GET` cả thảy) và dừng ở chữ của v3, trạng thái đã lưu; lần lưu không reply tới hạn (30 giây, thêm một giây cho mỗi
    50 KiB thân) là chậm chứ không phải mất và được gửi lại;
    nháp qua lần mount thử của StrictMode; "opens text typed after a save that landed unheard as the
    person's draft, not as a clash"; năm test `flush`); `web/src/lib/canvas-handoff.test.ts` (lần lưu
    cuối của canvas đã rời: 409 của chính mình là đã lưu, lỗi giữ nháp và báo người nghe còn đăng ký,
    gửi chữ gõ sau lần lưu đang bay, ngân sách keepalive tính bằng byte, mỗi lúc một lần lưu keepalive,
    lỗi trả lại ngân sách; canvas rời đi mà máy không giữ được nháp thì trang hỏi trước khi đóng tới khi
    lần lưu xong, hỏng hay ném lỗi cũng thôi hỏi và thông báo không hứa nháp, có nháp thì không hỏi gì,
    hai canvas thì hỏi tới khi cả hai xong; runner thật mà trình duyệt từ chối nháp thì tab giữ chữ và
    trang vẫn hỏi sau khi lần lưu hỏng; nháp đi khi bản lưu giữ chữ ở dạng đã trộn với bản của người
    khác, và ở lại khi người đã gõ thêm từ lúc rời; "says nothing and keeps no draft when the canvas
    was deleted before its last save got there": canvas bị xoá trong lúc lần lưu cuối còn bay thì
    `PUT` gặp 404, không người nghe nào được gọi và nháp của nó bị xoá, vì không có lần lưu nào hỏng
    cả; "lets go of words only this tab held for a canvas deleted before its last save got there":
    nháp mà chỉ tab giữ cũng đi theo, nên trang thôi hỏi trước khi đóng)
  - Hai request của runner (lưu và đọc) nằm ở `web/src/lib/canvas-requests.ts`. Hạn của lần lưu có test
    riêng ở `web/src/lib/canvas-requests.test.ts`: 30 giây cộng một giây cho mỗi 50 KiB thân, làm tròn
    lên; đo trên byte UTF-8 của thân nên 100000 chữ "ệ" chờ lâu hơn 100000 chữ "x"; không reply tới hạn
    thì báo `saveTimedOut` chứ không báo mất, trước hạn một mili giây thì chưa, 3 MB html không bị cắt
    ở giây 31, reply mất không mang status, 413 mang trần của loại canvas. Nhóm "how long a save may go
    unanswered after saves in a row had no reply in time" giữ việc nới hạn cho đường truyền chậm: sau
    mỗi lần lưu hết hạn liên tiếp thì phần thời gian cho thân gấp đôi còn 30 giây chờ reply giữ nguyên
    (4 MB: 111920, 193840, 357680, 685360 ms), dừng ở 8 lần dù hết hạn bao nhiêu lần, thân 34 byte vẫn
    là nửa phút chứ không thành một phút, và request thật sống tới đúng hạn đã nới. `requestSave` trả
    về cả hai hạn, `{ ms, firstMs }`: hạn của chính lần lưu và hạn đầu của cùng thân ấy; "keeps the
    first deadline what it was however many there were: only the save's own grows" giữ `firstMs` đứng
    yên ở 91441 ms khi `ms` lên 275763 rồi 521525. Lần đọc có nhóm "a read
    coming back" ở cùng tệp: gửi đi cái server giữ và không để timer nào lại, "says the canvas could
    not be read when what came back cannot be taken in, instead of leaving it loading" (thân trả về
    mà máy trạng thái không nhận được thì báo đọc hỏng chứ không treo ở "đang tải"), "says in the
    console what it could not take in" (lỗi ấy được ghi ra console đúng một lần kèm chính exception,
    vì canvas chỉ nói là không đọc được), lần đọc bị từ chối báo hỏng kèm status đúng một lần và không
    ghi gì ra console.
    `web/src/lib/canvas-runner-wait.test.ts` giữ `waitMs` của runner (0 khi chưa có lần lưu nào, cả
    hạn lúc lần lưu đi rồi ít dần, dài hơn với lần lưu lớn, về 0 khi lần lưu xong hay hết hạn, và vẫn là
    0 chứ không âm khi đồng hồ nhảy qua hạn trước lúc timer chạy) và nhóm "a save the link was too slow
    for": đường truyền mất 150 giây cho 4 MB (`web/src/test/slow-link.ts`, PUT bị bỏ trước lúc tới thì
    server không nhận) vẫn lưu xong mà không ai chạm vào canvas, lần gửi lại có `waitMs` 193842 ms và
    còn trong hạn khi hạn đầu đã qua, hết hạn hai lần liên tiếp thì gấp bốn, lưu xong thì về hạn đầu,
    lần bị server từ chối ở giữa không xoá mức nới, lần mất hay bị từ chối không làm hạn dài ra, canvas
    nhỏ vẫn nửa phút. `waitMs(true)` là phần còn lại của hạn đầu, tính từ lúc chính lần lưu ấy đi:
    "has, for a message, only what is left of the deadline it was first given, however long its own
    has grown" (sau một lần hết hạn `waitMs()` là 193842 còn `waitMs(true)` là 111921, về 0 khi hạn
    đầu qua dù lần lưu còn bay trong hạn đã nới, và 0 khi không lần lưu nào đang bay). Rời canvas hỏi
    `waitMs()` nên theo hạn đã nới; tin gửi đi hỏi `waitMs(true)` nên không theo.
    `web/src/lib/unload-guard.test.ts` giữ câu hỏi trước khi đóng trang (không hỏi khi chưa ai giữ,
    hỏi khi có người giữ và đặt cả `returnValue` cho engine cũ, thôi hỏi khi nhả và nhả hai lần không
    hại, còn hỏi khi còn người giữ khác), `web/src/hooks/use-saving-note.test.ts` giữ lời báo đang lưu
    (không nói gì khi việc xong trong chưa tới 300 ms, nói từ 300 ms và thôi khi việc xong hay hỏng,
    trả lại kết quả và chuyển lỗi đi, không để timer nào lại). Các test khác chạy hai request ấy thật
    trên `FakeCanvas`, nên chuyển chúng khỏi `canvas-runner.ts` không đổi test nào
- **Canvas trên web: tên người viết một bản, kích thước đọc được, ký tự ẩn hiện ra**
  - vitest: `web/src/lib/canvas-author.test.ts` (người là "bạn", agent theo tên, agent có id `user` vẫn
    là agent, agent không còn thì theo id); `web/src/lib/format-bytes.test.ts` (bước 1024, một chữ số lẻ
    dưới mười viết bằng dấu phẩy, làm tròn tới 1024 thì lên đơn vị); `web/src/lib/hidden-chars.test.ts`
    ("shows a right-to-left override as a visible mark", mọi ký tự điều khiển bidi và zero-width)
- **Canvas trên web: panel một canvas đọc, sửa, đổi tên, chép và tải về; canvas đã xoá vẫn đọc được**
  - vitest: `web/src/components/canvas/canvas-panel.test.tsx` (canvas người viết mở ở Sửa, sang Xem rồi
    về không mất chữ gõ, "opens a canvas an agent wrote to read, and keeps reading when a newer version
    arrives", canvas người viết vẫn ở Sửa khi agent ghi vào, nháp trên máy mở ở Sửa kể cả trên canvas
    agent viết, markup trong canvas markdown và code hiện thành chữ; đổi tên bằng `PATCH`, "shows the
    name the server answered with, when the stream says nothing of the rename": tên mới lấy từ chính
    reply chứ không chờ luồng báo, canvas vừa
    tạo mở với tên chờ gõ đè, đổi tên mà server không thấy canvas là canvas đã xoá; "keeps its text to
    read and copy, and offers nothing that needs the canvas"; về danh sách, đóng, tải bản mới nhất,
    "copies the text as it is, unmarked", dock lưu được chữ đang mở, hỏi được canvas còn không và buông
    khi panel tháo); `web/src/components/editable-title.test.tsx` ("renaming a canvas beside the
    conversation": ô tên có nhãn và placeholder riêng dưới tiêu đề của cuộc trò chuyện, "opens ready to
    type over the name of something just made"); `web/src/components/canvas/canvas-editor.test.tsx`
    (Ctrl/Cmd+S lưu ngay thay cho hộp lưu của trình duyệt, kể cả khi giữ Shift, còn chữ s để cho ô gõ;
    báo canvas lúc ô mất focus và lúc soạn IME; code, html, svg, mermaid và một loại web không biết
    đều dùng phông code và không kiểm chính tả, còn văn xuôi được kiểm chính tả trong phông của trang;
    "stays on
    the characters it was on when a line arrives above", tính từ chỗ phím gõ để con trỏ, giữ chỗ cuộn);
    `web/src/components/canvas/canvas-panel-modes.test.tsx` (canvas vừa tạo ở đây mở ở Sửa kể cả khi
    agent ghi vào trước lần đọc đầu, chữ gõ gộp vào bản mới hơn của agent mở ở Sửa và nói đã gộp tới
    khi lưu, canvas code của người dùng phông code; tên canvas vừa tạo mở để gõ, tối đa 200 ký tự;
    không hiện dòng phiên bản khi canvas đang được đọc dù bản mới đã báo tới; chọn Xem hay Sửa thì
    đóng lịch sử); `web/src/components/canvas/canvas-panel-lent.test.tsx` (cái panel đang mở cho dock
    mượn: thời gian lần lưu đang bay còn được chờ là 0 khi chưa có lần lưu nào, đủ hạn cộng một mili
    giây lúc lần lưu đi, ít dần theo giờ và về 0 khi lần lưu về; và máy này có giữ được nháp của chữ đang
    gõ hay không, rồi giữ được trở lại khi một lần ghi nháp vừa)
- **Canvas trên web: dòng trạng thái lưu, lời báo khi không lưu được, diff hai bản**
  - vitest: `web/src/components/canvas/canvas-status.test.tsx` (chữ cho từng trạng thái và lý do không
    bản nào giữ chữ đang gõ, "follows a save from the keystroke until it lands", server không trả lời
    khi máy có mạng, lần lưu chờ mạng khi máy mất mạng, lần lưu hết hạn mà chưa reply là "Mạng chậm,
    đang gửi lại" chứ không phải máy chủ không phản hồi, chữ nêu đúng trần (4 MB, 2 MB) mà canvas quá
    lớn bị giữ, "shows the largest canvases when the server is full, saves on its own no more, and
    saves on Cmd+S", nội dung bản lưu trong lúc sửa chỉ hiện ở thanh xung đột, canvas xin đóng mà chưa
    bản nào giữ chữ nói lý do rồi đóng hẳn khi được bảo, và nút nói bản nháp chỉ còn trong tab này khi
    máy không giữ được nháp); `web/src/components/canvas/canvas-status-cap.test.tsx` (trần mà server
    giữ một lần lưu được nói ở mọi chỗ panel nói vì sao chưa lưu: cạnh dòng phiên bản, trong thông
    báo của canvas xin đóng, và ở Lịch sử khi một lần khôi phục chờ chữ không lưu được);
    `web/src/lib/canvas-reasons.test.ts` ("reads %i as its reason, never the server's own words",
    request không tới server là mất kết nối); `web/src/components/diff-view.test.tsx` ("keeps three
    unchanged lines around a change and counts the rest", chỗ sửa chỉ gồm một ký tự ẩn vẫn hiện ra, hai
    bản giống nhau và hai bản quá lớn để so theo dòng đều được nói);
    `web/src/components/canvas/canvas-conflict.test.tsx` (thanh xung đột nêu ai lưu bản nào, giữ chữ
    của tôi thì không nạp bản kia, nạp bản kia khi được bảo, "shows what keeping mine would change in
    theirs, and hides it again"; chữ mà "Nạp bản mới" thay lấy lại được cho tới khi gõ);
    `web/src/components/canvas/canvas-notices.test.tsx` ("says the canvas could not be opened, and
    opens it on retry", máy này không giữ được nháp thì nói, canvas không có gì chưa lưu thì không
    cảnh báo nháp dù trình duyệt chặn lưu trữ, cảnh báo đi ngay khi chữ về đúng bản đã lưu)
- **Canvas trên web: lịch sử phiên bản, so sánh và khôi phục**
  - vitest: `web/src/components/canvas/canvas-history.test.tsx` ("lists each version, the newest first,
    and compares one with the version listed before it", so với bản cũ nhất còn giữ khi được hỏi và nói
    bản cũ nhất không có bản trước, đóng mà không khôi phục gì; "saves the typing first, then makes the
    version picked the newest without waiting for the event", ghi chú khôi phục hiện trên bản nó tạo,
    không khôi phục khi chữ gõ chưa lưu được và nói vì sao, server hết chỗ thì hiện các canvas lớn nhất;
    bản được chọn hay bản cần khôi phục đã bị gộp mất thì đọc lại danh sách và vẫn mở, "takes a restore
    of a canvas deleted meanwhile for the deletion");
    `web/src/components/canvas/canvas-history-reads.test.tsx` (bản mới báo tới lúc lịch sử đang mở thì
    đọc lại danh sách, chọn lại bản đọc hỏng thì đọc lại và thôi báo lỗi, danh sách hay một bản bị từ
    chối vì canvas đã xoá là canvas đã xoá; khôi phục đang đi thì không bấm lại được, server từ chối thì
    bấm lại được, lần thử lại lưu được chữ gõ thì thôi nói chữ gõ chặn lần khôi phục)
- **Canvas trên web: danh sách canvas của cuộc trò chuyện và nút tạo canvas mới**
  - vitest: `web/src/hooks/use-canvas-list.test.ts` (không hỏi gì khi chưa mở cuộc nào, chỉ canvas của
    cuộc này và mới nhất trước, "drops the last conversation's list at once, and its reply when it comes
    late", "reads the list once for a burst of changes, half a second after the first", thấy canvas tạo
    ở chỗ khác dù lời báo chưa nêu cuộc nào, không đọc được thì nói và đọc lại khi thử lại, đọc lại hỏng
    vẫn giữ danh sách đang có, đọc lại khi luồng nối lại và khi tab hiện, đóng cuộc rồi thì không nghe
    thay đổi nữa, không hiện gì của danh sách cuộc trước trong lúc đọc danh sách cuộc sau, thay đổi
    nghe được ngay trước khi đóng cuộc không làm đọc lại danh sách cuộc ấy, lần đọc trước hỏng sau khi
    lần đọc sau đã về thì giữ cái lần sau thấy); `web/src/components/canvas/canvas-picker.test.tsx`
    (đang tải, chưa có canvas, lỗi có nút thử lại, "shows each canvas with its kind, version and last
    change, and opens the one picked",
    "makes a canvas, one at a time, and says when one could not be made", "names the kind of a
    drawing, a diagram and a picture, and an unknown kind as it is", "offers the five kinds a person
    can make, never an image, and makes the one chosen", "keeps the kind chosen for the next canvas,
    and changes it on the next choice", "holds the kind still while a canvas is being made");
    `web/src/lib/artifact-events.test.ts` ("announces a canvas found gone as a deletion that names no
    conversation")
- **Canvas trên web: dock cạnh cuộc trò chuyện, tab và cột kéo rộng được từ 1101 px, lớp phủ cột chat
  dưới đó, rời canvas vẫn lưu nốt**
  - vitest: `web/src/hooks/use-canvas-dock.test.ts` ("never shows the last conversation's canvas in a
    render of the next one", lần lưu cuối hỏng sau khi đổi cuộc không để gì lại ở cuộc sau; tạo canvas
    markdown chưa có tên trong cuộc này rồi mở với tên chờ gõ, bảng "makes a %s canvas holding what
    one of its kind starts from" cho code, html, svg và mermaid, "sends nothing, and shows no request
    as out, while no conversation is open to put the canvas in", không tạo được thì nói và ở lại danh
    sách; "gives up on the open canvas's save after 5 seconds", đóng hay về danh sách mà không lần lưu
    nào xong thì ở lại tới khi đóng hẳn, lần lưu quá hạn cũng ở lại, còn lần lưu chưa hết hạn riêng của
    nó thì panel đóng và để lần lưu ở phía sau chờ nốt, canvas bị xoá lúc lần lưu cuối đang bay hay đã
    bị xoá thì đóng ngay; lần lưu hỏng sau khi panel đi được báo tới khi ẩn, canvas đã đóng hẳn thì
    không báo, trừ khi máy không giữ được nháp của nó: khi ấy thông báo là chỗ duy nhất người biết;
    "brings the canvas forward on each opening, and the button toggles the dock");
    `web/src/hooks/use-canvas-dock-moves.test.ts` (mở canvas hay danh sách khi đang xem hoạt động thì
    đưa tab canvas lên, không tạo canvas khi chưa mở cuộc nào, không báo lỗi tạo của canvas xin trước
    khi người mở canvas khác, canvas mở lại mà lần lưu cuối hỏng thì được báo lại, panel cũ buông muộn
    thì dock vẫn hỏi panel mới); `web/src/components/canvas/canvas-dock-view.test.tsx` (focus đi từ nút
    Canvas vào cột mở ra, sang nút về chat khi dock phủ cuộc trò chuyện, và đứng yên khi dock chuyển từ
    danh sách sang canvas; cột hoạt động nằm trong phần tử của dock nên bàn phím đang ở đó thì ở
    yên khi cột mở ra từ một cú bấm không lấy bàn phím, dù hoạt động lùi về sau tab của nó, và về
    nút Canvas khi dock đóng; hoạt động hiện khi chưa mở gì, tab hoạt động theo cú bấm, lớp phủ hiện cả
    dock; cột rộng đúng như cạnh nói; nút Canvas đếm canvas, không hiện số khi chưa biết canvas
    nào, và nói dock mở hay đóng; lần lưu không về
    của canvas chưa có tên gọi là canvas không tên, và thông báo nói bản nháp vẫn trên máy khi giữ được,
    nói nháp chỉ còn trong tab và mở lại canvas để lưu khi máy không giữ được; nhóm "making a canvas of
    a kind from the list": "asks for the kind chosen with what it starts from, and opens it to edit as
    text");
    `web/src/hooks/use-canvas-width.test.ts` ("takes half the room beside the sidebar until the person
    chooses", cả canvas lẫn cuộc trò chuyện rộng ít nhất 360 px, chỉ nhớ bề rộng khi được bảo giữ, bề
    rộng đã giữ co theo cửa sổ hẹp và trở lại khi cửa sổ rộng ra, theo cửa sổ khi người chưa chọn, không
    hẹp dưới 360 px kể cả cạnh cuộc trò chuyện hẹp, bỏ bề rộng đã giữ không phải số hay lớn quá để là
    số, đo chỗ cạnh sidebar theo bề rộng mà stylesheet đặt);
    `web/src/components/canvas/canvas-handle.test.tsx` ("widens the canvas as the pointer moves left
    and keeps where the button came up", kéo không bôi đen chữ, sau khi nhả thì thôi theo con trỏ; chỉ
    nút chính mới kéo; panel đóng giữa lúc kéo thì buông con trỏ);
    `web/src/components/conversation-header.test.tsx` ("starts with the pill given first, ahead of spend
    and options, and ends with the extras": nút Canvas đứng đầu hàng pill nên ở 390 px vẫn trong màn
    hình)
  - Việc xin tạo canvas nằm ở `web/src/hooks/use-canvas-create.ts` và không có tệp test riêng: dock
    đưa cho nó số lần chuyển và hai cách hiện kết quả, nên các test ở trên (tạo từng loại kèm chữ mở
    đầu của loại ấy, không gửi gì khi chưa mở cuộc nào, lỗi tạo, chuyển trước khi reply về) chạy nó
    qua dock và chuyển nó ra khỏi dock không đổi test nào. Chữ mở đầu của từng loại có test riêng ở
    `web/src/lib/canvas-templates.test.ts` (năm loại theo thứ tự danh sách hiện, markdown và code bắt
    đầu trống, html là trang nhỏ nhất còn chừa thân để viết, svg có `viewBox` để vẽ, mermaid có hai ô
    đã vẽ được với tên tiếng Việt, mẫu nào cũng kết thúc bằng xuống dòng và lần nào cũng cho cùng
    chữ, và nằm xa dưới trần nhỏ nhất của mọi loại)
  - vitest, cả App trên `FakeCanvas`: `web/src/app-canvas.test.tsx` ("opens as a tab over the activity,
    in a column its edge widens, and keeps both mounted", "keeps the open canvas and its typing as the
    window crosses 1101 px both ways", "makes a canvas from the list and opens its name to type over",
    "covers the chat column, and Escape saves the typing, closes it and gives focus back", "goes back to
    the chat from the covering list", "closes the drawer opened over the canvas before the canvas",
    "closes as another conversation opens, and the typing left behind is saved", "tells in the chat of a
    save that failed after the switch, until dismissed", "drops the ones older than 30 days as the app
    starts")
  - Playwright: `canvas.spec.ts` ở 1440 px ("opens in a tab beside the chat, and a pause in typing saves
    once from the version it began on", "keeps every character typed while a save is held for two
    seconds", "an agent's save on the line being edited raises the conflict bar, and keeping mine saves
    over it"), ở 1000 px và 390×844 cảm ứng ("saves, keeps the approval out of reach, fits a finger and
    goes back to the chat": nút Canvas trọn trong màn hình, Tab không tới nút duyệt dưới lớp phủ, mọi
    nút trong dock ≥40px, không cuộn ngang)
- **Gửi tin lúc canvas đang mở: chữ gõ trong canvas lưu xong rồi tin mới đi, ô soạn tin giữ chữ ở chế
  độ chỉ đọc tới khi server nhận**
  - vitest: `web/src/lib/canvas-handoff-flush.test.ts` (`handoffsSettled` trả ngay khi không lần lưu
    nào đang bay, chờ mọi lần lưu đang bay kể cả lần hỏng hay ném lỗi và không chờ lần bắt đầu sau lúc
    hỏi; `within` trả giá trị của việc khi nó xong kịp rồi xoá timer, trả giá trị muộn khi hết giờ chứ
    không sớm hơn, chuyển lỗi của việc đi và xoá timer; `flushAll` trả phiên bản panel vừa lưu khi mọi
    lần lưu đang bay đã xong, giữ phiên bản ấy khi một lần lưu chưa về tới trần, chờ panel và các lần
    lưu đang bay dưới một trần chung rồi trả null khi panel không còn, chỉ chờ các lần lưu đang bay
    khi không có panel, bỏ chờ ở trần, xoá timer khi mọi thứ đã về; trần tính sau hạn của lần lưu đang
    bay: panel chờ hạn 60 giây thì trả null ở 65 giây, hạn của các lần lưu đã rời tính lâu nhất chứ
    không cộng dồn, hạn của panel và của các lần lưu ấy lấy cái dài hơn, không bao giờ ngắn hơn trần,
    giữ phiên bản của panel khi lần lưu chậm của canvas đã rời còn trong hạn, trả lời ngay khi mọi thứ
    đã về; "waits for a save left behind only as long as it was first given, not for the deadline it
    has grown": lần lưu đã rời có hạn đầu 60 giây và hạn đã nới 600 giây thì trả null ở 65 giây; nhóm
    `handoffOut`: đúng với canvas mà lần lưu để lại còn bay và sai với canvas khác, sai trở lại khi lần
    lưu ấy xong hay hỏng);
    `web/src/hooks/use-canvas-dock-flush.test.ts` ("answers the version the open panel's last save
    landed", null khi không phiên bản nào giữ chữ trong trần, chờ lần lưu của canvas đã rời trước đó
    và giữ phiên bản của panel khi lần lưu kia muộn, chờ lần lưu của canvas đã rời khi không có panel
    và trả null, một hàm duy nhất suốt lúc dock còn gắn, rời canvas bằng tay chỉ hỏi panel đang mở
    chứ không chờ các lần lưu khác; lần lưu của panel được hạn riêng của nó rồi mới tới trần và trả
    null ở 65 giây khi hạn là 60, trả phiên bản ngay khi lần lưu hạ cánh trong hạn, hỏi hạn của panel
    sau khi lần lưu đã bắt đầu vì chính lần lưu đặt ra hạn ấy, và chờ cả hạn của lần lưu canvas đã
    rời); `web/src/components/composer-send-lock.test.tsx` ("holds the
    text in a read-only box and sends it once, however it is asked again", chữ được nhận thì ô và
    bản nháp đã giữ được xoá, không được nhận hay bị từ chối thì ô trả lại cùng chữ và bản nháp để
    gửi lại được, từ chối còn báo ra console, `onSend` không trả gì thì xoá ô ngay như cũ; khoá thuộc
    về hội thoại nơi chữ được gõ: chữ được nhận thì bản nháp của hội thoại đã rời bị xoá còn bản của
    hội thoại đang ở giữ nguyên, không được nhận thì bản nháp ấy được giữ; Stop trả chữ xếp hàng về ô
    trong lúc chờ thì chỉ phần đã gửi bị xoá, gợi ý thay chữ trong lúc chờ thì giữ gợi ý, danh sách
    lệnh `/` bị dẹp và không nhận lệnh khi ô đang giữ)
  - vitest, cả App trên `FakeCanvas`: `web/src/app-canvas-send.test.tsx` ("saves the typing in the
    canvas first, then sends the message naming that canvas": PUT canvas đi trước POST tin; "names no
    canvas when none was opened in this tab": thân POST chỉ có `{text}`; "holds the words in a
    read-only box until the canvas is saved, and sends once however often Enter comes"; rời sang hội
    thoại khác trước khi lần lưu về thì không gửi gì và chữ trở lại ô khi quay lại; ở hội thoại khác
    tin mới vẫn chờ lần lưu của canvas người vừa bỏ lại; "does not blame a passage the message never
    named, and leaves the words in the box": tin từ ô soạn nêu canvas mà không mang đoạn chọn, nên
    422 của nó (ở đây là danh sách `string_too_long` của server) được nói bằng câu tiếng Việt cho
    yêu cầu không hợp lệ chứ không bảo đoạn chọn không còn khớp, mã lỗi của server không lộ ra, chữ
    ở lại ô, ô gõ lại được và không có
    bong bóng; dưới ô soạn tin chỉ hiện "Đang lưu canvas…" khi lần chờ quá 300 ms và thôi hiện khi tin
    đi, lưu ngay thì không hiện gì, lần lưu hỏng thì tin vẫn đi)
  - Playwright: `canvas-send.spec.ts` ("a message sent over typing the canvas has not saved yet waits
    for the save, then names the canvas": lần lưu bị giữ thì chưa có POST nào và ô soạn tin chỉ đọc
    còn nguyên chữ, thả ra thì thứ tự là lưu rồi gửi, thân tin nêu canvas, ô trống và mở lại)
- **Tin gửi đi không chờ theo hạn đã nới của lần lưu: chờ hết hạn đầu của lần lưu (cộng 5 giây) rồi
  đi kèm bản đã lưu gần nhất, và cuộc trò chuyện nói rõ điều đó**
  - vitest, hook: `web/src/hooks/use-canvas-dock-message.test.ts` (nhóm "the wait of a message on a
    save given longer after saves that had no reply in time": panel có hạn đầu 60 giây và hạn đã nới
    600 giây thì `flush` trả null ở 65 giây chứ không sớm hơn một mili giây, lần lưu của canvas đã rời
    cũng vậy; nhóm "whether a message about to go names a canvas with text no version holds":
    `flushForMessage` trả `false` khi chưa mở canvas nào, khi lần lưu của canvas đang mở đã xong, khi
    canvas đã bị xoá, khi lần lưu còn bay là của canvas khác với canvas tin nêu, khi tin không nêu
    canvas nào (kể cả khi một panel có lần lưu hỏng vẫn còn gắn vào dock), và khi người mở canvas
    khác trong lúc tin còn chờ; trả `true` khi lần lưu hỏng, khi
    hết lượt chờ mà lần lưu chưa về (và không trả gì trước đó), khi canvas tin nêu đã được cất đi trên
    màn hẹp mà lần lưu cuối còn bay; nhóm "the note that a message went before the canvas it names
    was saved": `sentUnsaved` bật và tắt theo `noteSentUnsaved`, thuộc về hội thoại tin đã đi (sang
    hội thoại khác không hiện, quay lại thì hiện), hàm lấy ở hội thoại nào thì nói về hội thoại ấy dù
    người đã sang nơi khác, mỗi hội thoại giữ lời của riêng mình, không hội thoại nào mở thì không
    có); `web/src/hooks/use-canvas-dock.test.ts` giữ việc rời canvas vẫn hỏi hạn đã nới: panel giả
    trả 0 cho hạn đầu và 20 giây cho hạn đã nới thì vẫn đóng được, trả 20 giây cho hạn đầu mà hạn
    đã nới đã hết thì ở lại; `web/src/components/canvas/canvas-dock-view.test.tsx` nhóm "the line
    saying a message went before its canvas was saved" (không có cho tới khi dock nói, là `status`
    chứ không phải `alert`, đứng cạnh thông báo lần lưu không về và mỗi dòng được ẩn bằng nút riêng)
  - vitest, cả App trên `FakeCanvas`: `web/src/app-canvas-send-unsaved.test.tsx` ("goes once the save
    has had the time it was first given, with the version saved before, and says so": 500 KiB
    markdown trên đường truyền mất 100 giây, ba lần lưu hết hạn, tin chưa đi ở 45 giây thiếu một mili
    giây và đi ở đúng 45 giây, ô soạn tin mở lại, server chưa có chữ mới; "leaves the save the
    longer time it was given": lần lưu ấy vẫn hạ cánh ở giây 100 và dòng báo còn đó; dòng báo mang
    đúng câu chữ, lớp `notice warn canvas-notice` và nằm trong cột chat; tin sau gửi lúc canvas đã lưu
    thì dòng báo đi; "goes with a question about a passage of the canvas, which went with the canvas
    saved": câu hỏi về một đoạn của canvas, đi kèm bản panel vừa lưu, cũng làm dòng báo đi; câu hỏi
    ấy không tới được server thì dòng báo còn, vì tin gửi gần nhất vẫn là tin cũ; nút "Ẩn thông báo"
    cất nó mà không gửi gì thêm; tin server không nhận thì không báo; canvas lưu kịp hay không mở
    canvas nào thì không báo)
- **Canvas mà server đang mở ở hội thoại: vào hội thoại thì web mở lại nó mà không giành focus và không
  ghi gì; chỉ báo server khi người đóng canvas trên màn rộng**
  - vitest, hook: `web/src/hooks/use-canvas-focus.test.ts` nhóm "coming into a conversation" (màn rộng
    thì mở lặng lẽ canvas server đang mở ở hội thoại ấy và không ghi gì, server không mở gì thì không
    mở gì và tin đi không kèm canvas, hỏi lại ở mỗi hội thoại đổi sang, màn hẹp không hỏi gì và không
    hỏi lại khi màn thành rộng hay dock đổi, id server không bao giờ tạo thì không mở, mở đúng một
    lần và không ghi gì dù StrictMode chạy effect lần hai, câu trả lời tới sau khi người sang hội
    thoại khác hay sau khi người mở rồi đóng canvas thì không mở gì, đọc hỏng chỉ ghi console và dock
    vẫn dùng được); `web/src/hooks/use-canvas-focus-close.test.ts` ("tells the server once, from a
    canvas opened here, and opening it told nothing": đóng trên màn rộng gửi `PUT {artifact_id:
    null}` đúng một lần, cả khi chỉ mới hiện danh sách; về danh sách, màn hẹp, hay sang hội thoại
    khác với canvas đang mở thì không báo gì; ghi hỏng chỉ ghi console và dock vẫn đóng; `focusId`
    thành `null` mà người không đóng gì, lúc hook gắn hay cùng lúc đổi hội thoại, thì không báo, và
    lần đóng thật sau đó vẫn báo); `web/src/hooks/use-canvas-dock-restore.test.ts` ("opens it
    quietly, and names it, when nothing has moved since the ticket"; người đã sang hội thoại khác rồi
    quay lại, hay giữ tham chiếu lấy ở hội thoại đã rời, thì không mở gì; id không đúng mười hai chữ
    số hex thường thì không mở: `a1`, `../x`, chữ hoa, thiếu, thừa, xuống dòng ở cuối, rỗng);
    `web/src/hooks/use-canvas-dock-focus.test.ts` nhóm "a canvas opened quietly" (đánh dấu tới bước
    kế, mở thường thì không đánh dấu; canvas khác mở, danh sách mở, dock đóng hay bị buộc đóng đều
    hết đánh dấu); `web/src/components/canvas/canvas-dock-view.test.tsx` nhóm "focus when a canvas
    opens without being asked for" (mở thường thì focus vào dock dù từ đâu tới; mở lặng lẽ thì focus
    ở đâu vẫn ở đó: không đâu thì vẫn không đâu, ở ô soạn tin thì vẫn ở ô soạn tin)
  - vitest, server giả: `web/src/api/artifact-client.test.ts` ("reads what a conversation has open,
    null when nothing, and sets or closes it under an encoded id", "rejects a focus request the
    server refused, with its status"); `web/src/test/fake-canvas-focus.test.ts` (route canvas đang mở
    của hội thoại đọc và ghi như server: chưa mở gì thì null, mở một canvas thì chia sẻ nó với hội
    thoại, `null` đóng, canvas không có thì 404 và giữ nguyên cái đang mở, đoạn chọn dài nhất cho
    phép đếm theo ký tự, canvas bị xoá thì không còn mở ở đâu, canvas tạo trong hội thoại thì mở ở
    đó và không kèm đoạn chọn còn canvas tạo riêng thì không mở ở đâu, một lần đọc cũng giữ và thả
    được như request canvas khác, từ chối hay mất reply theo yêu cầu, method không có route thì 405; tin mang `canvas` được áp trước khi đi tiếp: không mang hay
    mang `null` thì để yên, id thật thì mở và chia sẻ, id đã mất thì đóng, đoạn chọn ghi đè đoạn
    trước, đoạn ghi chú sẽ bỏ thì 422 và không áp gì; `FakeBackend` từ chối nguyên tin với 422 mà
    không lưu gì). Dụng cụ dùng chung: `web/src/test/canvas-app.tsx` (cả App trên hai hội thoại
    "Một", "Hai" và canvas "Ghi chú"), `canvas-dock-hook.ts` (dock trên server giả), `screen-width.ts`
    (bề rộng cửa sổ giả cho `matchMedia`)
  - vitest, cả App trên `FakeCanvas`: `web/src/app-canvas-focus.test.tsx` ("tells the server once on a
    wide screen, and the next message names no canvas", "tells nothing on a narrow screen, where the
    canvas put away is still the one the message names", "opens beside the chat without taking the
    focus from the box, and writes nothing": chữ gõ ngay sau đó vào ô soạn tin chứ không vào canvas,
    "carries no canvas from a read that was answered after the person went to another conversation")
- **Canvas agent ghi hiện thành thẻ trong hội thoại và mở được từ đó; canvas agent vừa tạo ở lượt của
  chính tab này tự mở bên cạnh mà không giành focus**
  - vitest, thư viện: `web/src/lib/artifact-tag.test.ts` (đọc canvas và phiên bản từ thẻ ở đầu kết quả
    ghi, kể cả lần ghi không đổi gì; không có thẻ, thẻ không nằm ở đầu, thẻ không trọn, id server không
    bao giờ tạo hay phiên bản số không giữ chính xác được thì không đọc; id là đúng mười hai chữ số hex
    thường, có xuống dòng ở cuối thì bị từ chối); `web/src/lib/canvas-title.test.ts` (tên được làm sạch
    đúng như server: xuống dòng và chuỗi khoảng trắng thành một dấu cách, mọi ký tự `isspace` của Python
    tính là dấu cách, BOM bị bỏ chứ không thành dấu cách, ký tự điều khiển và định dạng kể cả bidi và
    khoảng trắng rộng bằng không bị bỏ, ký tự nối giữ emoji liền nhau được giữ, chữ gõ rời được ghép
    lại, không còn gì nhìn thấy thì xin tên khác, tối đa 200 ký tự và nói đã thấy bao nhiêu, mỗi ký tự
    đếm một lần dù chiếm mấy đơn vị UTF-16, đếm sau khi làm sạch chứ không trước)
  - vitest, hook: `web/src/hooks/use-canvas-list-verify.test.ts` nhóm "the title of a canvas a card
    names" (tên là tên danh sách đang giữ và không hỏi server thêm; canvas chưa ai đọc thì chưa biết
    tên; canvas danh sách không giữ thì đọc một lần rồi giữ; danh sách giữ canvas rồi thì lấy tên của
    danh sách), nhóm "asking whether a canvas is still there" (chờ danh sách đọc xong nên canvas danh
    sách giữ không bao giờ bị hỏi; hỏi khi danh sách đã về mà không giữ canvas; hỏi lại sau mỗi lần đọc
    danh sách khi chưa có câu trả lời; mất mạng không phải câu trả lời; 404 là canvas đã xoá và báo mọi
    bên nghe đúng một lần; từ chối khác không phải xoá; mỗi canvas một lần đọc tại một lúc; id server
    không tạo thì không hỏi; sang hội thoại khác thì quên việc định hỏi; một hàm duy nhất) và nhóm "a
    canvas deleted" (nghe thấy từ luồng, vẫn là đã xoá sau khi danh sách đọc lại mà thiếu nó, khác với
    canvas đổi); `web/src/hooks/use-canvas-list-memory.test.ts` (danh sách nhớ gì về các canvas thẻ
    nêu: tên của mọi canvas đã đọc chứ không chỉ canvas đọc sau cùng, mọi canvas đã xoá chứ không chỉ
    canvas xoá sau cùng; chờ danh sách của cuộc trò chuyện vừa mở và không lấy danh sách của cuộc
    trước làm của nó, nên canvas chưa biết không bị hỏi trước khi danh sách mới về);
    `web/src/hooks/use-canvas-dock-typing.test.ts` (`typing()` là không khi chưa có panel,
    là điều panel nói và hỏi lại mỗi lần, lại là không khi panel buông, một hàm duy nhất);
    `web/src/components/canvas/canvas-dock-keyboard.test.tsx` (dock thật trong cột: `typing()` là
    không khi bàn phím không ở đâu hay ở ô soạn tin dù canvas đang mở; là có khi bàn phím ở một nút
    của canvas đang mở, ở một tab của dock, ở một dòng trong danh sách canvas, ở khung của trang
    HTML mà app chỉ thấy là `iframe`, và ở phần hoạt động dock đang hiện khi chưa mở canvas nào;
    lại là không khi bàn phím về ô soạn tin; chữ chưa lưu thì vẫn là có sau khi bàn phím đã rời dock;
    nhóm "whether the open canvas holds the person's typing…": `editing()` hẹp hơn, là không khi bàn
    phím ở một nút của canvas, ở một tab, trong khung trang hay khi chưa mở canvas nào dù `typing()`
    là có, là có khi bàn phím ở ô chữ của canvas và khi còn chữ chưa lưu);
    `web/src/hooks/use-canvas-auto-open.test.ts` (mở lặng lẽ khi lệnh tạo xong ở lượt tab này đang
    xem, đúng một lần dù thread vẽ lại bao nhiêu, hai canvas trong một lần vẽ thì mở theo thứ tự tạo,
    lấy canvas thẻ nêu chứ không lấy tham số, cần thẻ ở đầu kết quả, mở được cả khi chưa tải chi tiết
    hội thoại; không bao giờ tự mở: sửa hay viết lại, lệnh tạo hỏng hay bị từ chối hay bị dừng, canvas
    của hội thoại tab chỉ mới đọc dù lúc gắn hay lúc tải, canvas của lệnh đã xong trước khi màn hình
    được vẽ, canvas trên màn quá hẹp kể cả khi màn rộng ra sau đó, canvas xong lúc người đang gõ kể
    cả khi họ ngừng;
    lệnh chưa xong thì bỏ qua và xét một lần khi xong, đang chờ duyệt thì bỏ qua rồi mở khi xong, xét
    theo lúc kết thúc chứ không lúc bắt đầu; nhóm "a call still going when the screen was drawn, as
    when the person comes back to the chat mid-turn": lệnh đang chạy hay đang chờ duyệt lúc màn hình
    được vẽ thì mở canvas khi xong, lệnh giao việc cũng vậy, đúng một lần dù vẽ lại; không mở khi
    lịch sử đã đọc có lệnh ấy, khi lệnh hỏng, bị từ chối hay bị dừng, khi màn quá hẹp hay khi người
    đang giữ bàn phím trong dock; lệnh đã có trong lịch sử đã lưu thì không phải của lượt
    này, không chặn lệnh của lượt này mà lịch sử chưa có, phân biệt theo lệnh chứ không theo canvas nó
    tạo)
  - vitest, thành phần: `web/src/components/canvas/canvas-card.test.tsx` (thẻ nói canvas đã tạo, tên
    và phiên bản, và mở được; sửa, viết lại và "không đổi" nói đúng phiên bản; là thẻ riêng chứ không
    phải thẻ công cụ thường; thẻ đang chạy nói đang viết kèm vòng quay — xong thì hết vòng quay —,
    không có nút mở và không hỏi server; tên của
    lệnh tạo đang chạy làm sạch như server, tên server sẽ từ chối thì vẫn gọi là Canvas; sửa hay viết
    lại canvas thread chưa biết thì gọi là Canvas bất kể tham số, tham số hợp lệ chỉ để tra tên; id tham
    số mà server không tạo thì bỏ qua; tham số không phải mapping, của lần chạy cũ, vẫn là thẻ; tên là
    tên thread biết chứ không phải tên trong tham số, kể cả tên rỗng; ký tự ẩn hay đảo chiều hiện thành
    dấu, cả trong nhãn nút; canvas mở là canvas thẻ nêu bất kể tham số, sửa hay viết lại không có thẻ
    thì lấy id đã đưa, lệnh tạo không có thẻ thì không có nút; thẻ không ở đầu kết quả thì không có
    canvas; canvas đã xoá thì nói vậy, giữ tên và không có nút, và đổi từ có nút sang không có khi
    canvas mất; mỗi canvas hỏi server một lần dù vẽ lại, hỏi lại khi thẻ đang chạy xong; không bao giờ
    hiện tham số hay chữ của kết quả); `web/src/components/tool-call-card-canvas.test.tsx` (ba lệnh ghi
    thành thẻ canvas khi đang chạy và khi xong; lệnh hỏng, bị từ chối, bị dừng hay đang chờ duyệt giữ
    thẻ thường và hiện lý do; lệnh đọc giữ thẻ thường; thread không có đường mở canvas thì giữ thẻ
    thường; lệnh giao việc và công cụ khác như cũ; trong thread, thẻ nhận đúng đường mở của thread và
    nằm đúng thứ tự giữa các thẻ của lượt); `web/src/components/canvas/canvas-panel-typing.test.tsx`
    (canvas vừa mở thì chưa là đang gõ dù ô soạn đã có; chữ chưa lưu là đang gõ và hết khi đã lưu; ô
    soạn đang giữ bàn phím là đang gõ dù đã lưu và hết khi buông; bàn phím ở chỗ khác trong panel thì
    không; canvas đang đọc không có ô để gõ; chữ chưa lưu vẫn là đang gõ ở chế độ đọc; ô soạn biến mất
    mà không còn gì chưa lưu thì hết; hỏi lại mỗi lần qua một tay cầm duy nhất)
  - vitest, cả App trên `FakeCanvas`: `web/src/app-canvas-thread.test.tsx` ("opens beside the thread at
    once, leaves the keyboard in the box and writes nothing", "goes with the next message the person
    sends as the canvas they have open", "does not take the panel from a canvas the person has the
    keyboard in", "does not take the panel from a canvas the person has the keyboard on a button of,
    and still opens from its card" (bàn phím ở nút "Xem" chứ không ở ô soạn của canvas: canvas mới
    không tự mở, bàn phím ở nguyên, nút Mở trên thẻ vẫn mở nó), "does not take the panel for a file
    read into a new canvas either, with the keyboard on a tab of the dock, and still opens from its
    card" (lệnh `artifact_import` tạo canvas mới lúc bàn phím ở tab "Hoạt động" của dock: cũng không
    tự mở, bàn phím ở nguyên, nút Mở trên thẻ vẫn mở nó), "opens only the once, however the
    person goes from the chat to the crew and back", "opens when its call ends after the person left
    the chat mid-turn and came back" (lệnh tạo đang chờ duyệt, người sang Quản lý rồi về chat và cho
    phép: canvas mở cạnh thread khi lệnh xong, không lần ghi "canvas đang mở" nào);
    màn hẹp chỉ hiện thẻ có nút mở và không tự mở gì; lượt trước tạo canvas thì thẻ nằm trong thread đã
    lưu, chỉ mở khi được bấm và kéo bàn phím vào dock; server không còn canvas thì thẻ nói vậy và không
    có nút)
  - Playwright: `canvas-thread.spec.ts` (ở 1440 px canvas agent tạo mở bên cạnh thread trong khi bàn
    phím ở ô soạn tin, nút Mở của thẻ đưa canvas đã đóng trở lại; ở 390 px thẻ có nút Mở và một lần
    chạm phủ canvas lên thread); `touch-targets-phone.spec.ts` ("the canvas card's Open button and the
    note chip in the thread are big enough for a finger": ≥40px mỗi chiều ở 390 px)
- **Chọn một đoạn của canvas rồi hỏi agent về đoạn ấy: tin gửi đi mang đoạn trích đúng các dòng người đã
  chọn, ở chế độ Sửa lẫn chế độ Xem**
  - pytest: `tests/test_api_canvas_focus.py`
    ("test_a_selection_cut_through_a_character_is_422_and_nothing_changes",
    "test_a_selection_with_a_whole_emoji_in_it_is_stored": đoạn cắt giữa một ký tự — nửa emoji, hai đơn
    vị UTF-16 bị tách rời — bị từ chối 422 và vùng chọn đang mở giữ nguyên, emoji nguyên vẹn được lưu;
    thân yêu cầu gửi như trình duyệt gửi, đơn vị lẻ viết thành escape, vì httpx không mã hoá nổi nó);
    `tests/test_api_chat_canvas.py` (cùng hai ca ở POST tin nhắn: bị từ chối trước khi tin vào hàng đợi,
    cả khi cuộc trò chuyện đang bận, không để lại tin, hàng đợi hay lần chia sẻ nào; đoạn cắt ở cuối
    dòng, như web cắt đoạn dài hơn một tin, vẫn được ghi chú đặt theo dòng với dòng cuối đã hạ cho khớp;
    đoạn đã cắt mà còn giữ dòng cuối của cả vùng chọn thì ghi chú đặt theo chữ (`PICK_TEXT`) và không
    nêu dòng nào, vì các dòng ấy chạy quá đoạn)
  - vitest, thư viện: `web/src/lib/rehype-source-lines.test.tsx` (mỗi đoạn văn, tiêu đề mọi kiểu kể cả
    tiêu đề gạch dưới trải hai dòng, mục danh sách — mục có danh sách lồng mang cả các dòng của phần
    lồng —, bảng và từng hàng của nó (không phải hàng ngăn cách hay ô), khối code và code trong khối
    với các dòng của khối kể cả hàng rào, khối trích dẫn và đoạn trong nó đều mang các dòng đã viết; code
    trong câu, nhấn mạnh, liên kết, danh sách nói chung, đường kẻ và ô để nguyên; phần tử không có vị
    trí thì không có dòng nào để nêu mà vẫn giữ thuộc tính; markup trong chữ chỉ hiện thành chữ nên
    không giả được dòng); `web/src/components/markdown-body.test.tsx` nhóm "the source lines a canvas
    needs to place a selection" (khối được đánh dấu dòng khi được yêu cầu, code trong khối rào mang dòng
    của khối vì đó là phần trang giữ lại của khối, code trong câu không có dòng, không yêu cầu thì vẽ
    đúng HTML như trước, markup trong chữ không giả được dòng); `web/src/lib/canvas-selection.test.ts`
    (nhóm "a passage clipped to what a message can take": đoạn trong giới hạn và đúng bằng giới hạn giữ
    nguyên, giới hạn là đúng 20000 ký tự server nhận — hơn một hay kém một đều sai —, đếm ký tự như
    server — một cặp đơn vị mã là một —, nên các dòng trọn đúng bằng giới hạn theo ký tự vẫn giữ nguyên
    dù một cặp làm chúng dài hơn theo đơn vị mã; đoạn chỉ toàn khoảng trắng không có gì để hỏi; đoạn
    dài hơn bị cắt ở cuối dòng cuối cùng còn vừa và dòng cuối hạ xuống dòng liền trước, kể cả khi cuối
    dòng ấy đúng là ký tự cuối của giới hạn, và khi một dòng vừa chạm giới hạn thì ký tự xuống dòng liền
    sau nó là ký tự đầu tiên bị bỏ; ký tự xuống dòng ở chỗ cắt và các dòng chúng thêm không nằm trong
    đoạn cắt; một dòng dài hơn giới hạn thì cắt theo ký tự, không bao giờ giữa một cặp; khi ký tự xuống
    dòng duy nhất trong giới hạn lại là ký tự đầu thì cũng cắt theo ký tự và giữ dòng trống ở đầu; dòng
    đầu một mình đã quá giới hạn thì đoạn cắt dừng ở dòng đầu; đoạn cắt chỉ còn khoảng trắng thì không
    có gì. Nhóm "the passage selected in the editor": đoạn giữa dòng, đoạn
    qua nhiều dòng với mỗi đầu ở đúng dòng của nó, đoạn dừng ngay sau ký tự xuống dòng không tính dòng
    kế, đoạn bắt đầu ở ký tự xuống dòng không tính dòng trước, bỏ mọi ký tự xuống dòng ở hai đầu như khi
    ba lần nhấp chọn một dòng, giữ thụt lề và dòng trống ở giữa; con trỏ, khoảng trắng hay chỉ ký tự
    xuống dòng thì không đọc ra gì; đoạn quá giới hạn bị cắt mà vẫn nói đã chọn bao nhiêu ký tự, đếm
    theo ký tự chứ không theo đơn vị mã); `web/src/lib/canvas-selection-view.test.tsx` (vùng chọn trong
    canvas đang đọc: trong một đoạn văn là mọi dòng của đoạn, qua hai mục danh sách là dòng của cả hai,
    từ tiêu đề xuống đoạn văn gồm cả dòng trống ở giữa, trong khối code là cả khối kể cả hàng rào, trong
    ô bảng là cả hàng, trong mục có danh sách lồng là dòng của mục và của các mục lồng; số ký tự báo là
    chữ nhìn thấy chứ không phải dấu markdown; code thì mỗi dòng đứng riêng, kể cả dòng trống và dòng cuối
    không có ký tự xuống dòng; nhãn nút sao chép của khối code nằm giữa hai đoạn văn không làm lệch;
    vùng chọn kết thúc ngay đầu khối kế, như ba lần nhấp để lại — dù đầu ấy là chữ, là phần tử, hay là
    chữ ngoài vùng đọc — không lấy khối kế; con trỏ, khoảng trắng, không có vùng chọn, một đầu nằm ngoài
    vùng đang đọc hay chữ không nêu dòng nguồn nào đều không đọc ra gì, và chữ ở trước vùng đọc kèm
    khoảng trắng ở sau nó vẫn là chữ ngoài vùng; vùng chọn bắt đầu ở khoảng trắng trước vùng đọc rồi
    kết thúc trong nó thì đọc được; vùng chọn quá giới hạn bị cắt như mọi vùng khác. Ca vùng chọn kết
    thúc ở vị trí 0 của một nút chữ — dạng Firefox và WebKit để lại — chỉ có test jsdom này, vì Chromium
    không bao giờ để lại nó); `web/src/lib/canvas-selection-markup.test.tsx` (vùng chọn trong markup do
    thứ khác vẽ, để thử riêng từng điều kiện đặt ra cho khối: khối nêu dòng nhưng nằm quanh vùng đọc
    chứ không trong nó thì bị bỏ; vùng chọn đi từ dòng đầu sớm nhất tới dòng cuối muộn nhất của khối ở
    hai đầu, khối lồng nằm ở đầu nào cũng vậy; khối nêu dòng mà nguồn không có thì không đọc ra gì, còn
    nguồn đủ dòng thì đọc được; dòng đầu trước dòng thứ nhất, dòng âm, dòng không nguyên ở đầu hay ở
    cuối, giá trị không phải số đều không đọc ra gì; dòng nguyên nằm trong nguồn thì đọc ra đúng các dòng
    ấy)
  - vitest, thành phần: `web/src/components/canvas/canvas-ask.test.tsx` (thanh hỏi không hiện gì khi
    chưa chọn gì và hộp còn đóng, hay khi đang ẩn; hiện đoạn chọn, các dòng nó nằm trên và nút hỏi; đoạn
    trên một dòng gọi tên dòng ấy một mình; đếm ký tự như server; đoạn trích hiện tối đa số ký tự cho
    phép, cắt giữa các ký tự nguyên, đoạn vừa thì hiện nguyên không dấu đã cắt, khoảng trắng quanh đoạn không tính vào đoạn trích; ký tự không nhìn thấy
    được viết ra thành dấu để người thấy điều agent sẽ nhận, dấu BOM cũng vậy dù mẫu khoảng trắng coi nó
    là khoảng trắng; nhóm "what is said when more is sent than was selected": nói rằng cả các dòng sẽ
    đi và chỉ sang Sửa khi các dòng chứa nhiều hơn hẳn phần đã chọn, đến ngưỡng thì không nói, và thanh đếm số ký tự sẽ đi chứ không đếm số đã chọn; nhóm "the
    question box": hộp mở bằng nút, nhận con trỏ và vẫn để đoạn chọn hiện, bấm nút không làm mất vùng
    chọn của trang, không gửi được khi rỗng hay chỉ có khoảng trắng bằng nút hay Enter, trang nhận Enter
    và Escape thay cho ô — không để lại ký tự xuống dòng hay hành vi mặc định của phím — còn Shift+Enter
    và phím của chữ đang gõ bằng bộ gõ thì để cho ô, Huỷ và Escape
    đóng hộp, bỏ chữ đã gõ và lần sau mở ra rỗng, trả con trỏ về nút khi đóng bằng Escape hay Huỷ nhưng
    không giật con trỏ đang ở chỗ khác, giữ đoạn đã chọn khi người rời trang để vào hộp, theo đoạn chọn
    mới khi hộp đang mở và giữ đoạn ấy khi vùng chọn mất, biến khi ẩn và trở lại như cũ; nhóm "why asking
    is off": mỗi lý do khoá nút và nói đúng lý do ấy, hỏi được thì không nói gì, hộp đang mở thì khoá Gửi
    và Enter nhưng vẫn cho viết tiếp câu hỏi, hết lý do thì mở lại Gửi);
    `web/src/components/canvas/canvas-ask-send.test.tsx`
    (lưu canvas trước rồi mới gửi đoạn ở đúng phiên bản lần lưu cho, kèm câu hỏi đã bỏ khoảng trắng hai
    đầu; Enter gửi, Shift+Enter và Enter kết thúc một chữ đang gõ bằng bộ gõ thì không; server nhận hay
    xếp hàng đều đóng hộp và báo panel; server từ chối thì hộp và câu hỏi còn nguyên, báo điều đã sai và
    lần thử kế bắt đầu sạch; không lưu được canvas thì không hỏi gì, báo và giữ câu hỏi; canvas đổi giữa
    lúc lưu thì không hỏi, bảo chọn lại đoạn và giữ câu hỏi, chọn lại thì hỏi về đoạn mới với câu hỏi
    như cũ và bỏ lời báo cũ; bấm bao nhiêu lần cũng hỏi một lần, hộp bị khoá — chỉ đọc, Gửi và Huỷ tắt,
    Escape không đóng — tới khi lưu xong; hỏi được câu thứ hai về đoạn khác khi câu đầu đã đi qua);
    `web/src/components/canvas/canvas-ask-failure.test.tsx` (lời báo về câu hỏi server đã từ chối: còn
    nguyên khi đúng đoạn ấy được báo lại; mất khi đoạn chọn khác đi — chữ khác, dòng đầu khác hay dòng
    cuối khác — mà câu hỏi gõ dở vẫn còn; mất khi chữ của canvas đã đổi dù chữ chọn vẫn thế; không còn
    khi hộp mở lại sau khi đóng; panel cứ đưa đoạn chọn trước lúc chữ đổi thì câu hỏi không đi, thanh
    báo chữ đã đổi và bảo chọn lại);
    `web/src/components/canvas/canvas-panel-ask.test.tsx`
    (chạy cho cả canvas đang sửa lẫn đang đọc: đề nghị hỏi về đoạn đang chọn với các dòng của nó, chưa
    chọn gì thì không đề nghị gì, panel không có đường hỏi thì không đề nghị dù chọn gì; đặt con trỏ vào
    chữ thay cho đoạn thì thôi đề nghị, con trỏ đi nơi khác thì vẫn đề nghị; chữ đổi thì thôi đề nghị
    đoạn cũ và đề nghị đoạn chọn kế; người chuyển sang cách hiển thị kia thì thôi; canvas bị xoá thì hết,
    kể cả đoạn chọn sau đó; nói lý do tắt như chat nói; ẩn khi xem lịch sử, giữ câu hỏi đã bắt đầu qua
    lần xem và không đưa lại đoạn chỉ chọn trước lần xem; hai bản xung đột thì không đề nghị gì; gửi câu
    hỏi từ panel: lưu chữ đã gõ trước rồi hỏi về đoạn ở bản đã giữ nó, lấy phiên bản từ lần lưu của dock
    — lần lưu có giới hạn thời gian —, chữ đổi trong lúc lưu thì không hỏi và bảo chọn lại);
    `web/src/components/canvas/canvas-editor.test.tsx` nhóm "the selection the editor reports" (đoạn đang
    chọn kèm các dòng, chỉ con trỏ thì báo không có, chữ đúng như đã gõ, vẫn ghi con trỏ cho các lần
    thay của máy khi chẳng ai nghe) và nhóm "a selection that no key or mouse made" (vùng chọn mà trình
    duyệt chỉ báo bằng `selectionchange` — tay cầm chọn trên màn cảm ứng, `setSelectionRange`, chọn tất
    cả trong menu — được báo khi ô đang giữ bàn phím và bị bỏ qua khi bàn phím ở chỗ khác; con trỏ cho
    các lần thay của máy dời theo như khi phím tạo vùng chọn; tài liệu chỉ được nghe khi trình sửa còn
    trên trang, một trình nghe thêm vào và chính nó gỡ ra. Test bắn `selectionchange` vào chính ô, như
    Chromium, vì React bỏ qua bản ấy và chỉ nghe bản bắn vào tài liệu — bắn vào tài liệu thì test vẫn
    xanh dù trình sửa hỏng trên trình duyệt thật); `web/src/components/canvas/canvas-view-selection.test.tsx`
    (canvas đang đọc báo gì về vùng chọn vượt ra ngoài nó: có cả hai đầu trong nó thì báo đoạn chọn;
    bắt đầu trong nó rồi chạy tiếp ra trang, hay từ trang đi vào nó, thì báo không có đoạn nào; không
    đầu nào nằm trong nó — kể cả vùng chọn chạy ngang qua nó — thì không nghe gì; chọn chữ khi không
    ai nghe, và bỏ hẳn vùng chọn, đều không ném lỗi — test bắt sự kiện `error` mà jsdom bắn khi một
    listener ném, vì không bắt thì lỗi ấy chỉ hiện thành "lỗi chưa xử lý" của cả lần chạy, không gắn
    với test nào);
    `web/src/components/canvas/canvas-view-memo.test.tsx` (canvas đang đọc không vẽ lại chữ khi cái nó
    nhận không đổi, như khi panel vẽ lại vì người đang gõ câu hỏi, và vẽ lại khi chữ đổi; test đếm số
    lần thân markdown được vẽ)
  - vitest, cả App trên `FakeCanvas`: `web/src/app-canvas-ask.test.tsx` (một tin duy nhất mang đoạn chọn
    và câu hỏi, không lưu hay ghi gì thêm, cho cả canvas đang sửa lẫn đang đọc; chữ đã gõ được lưu trước
    và đoạn được hỏi theo bản đã lưu; tin của người có chip ghi chú server giữ cùng câu hỏi; hộp đóng mà
    canvas vẫn ở cạnh chat khi lượt vừa bắt đầu còn chạy, và hộp cũng đóng khi server xếp câu hỏi sau
    một lượt tab này không thấy; câu hỏi bị từ chối bằng 409, 422 hay 429 thì hộp giữ câu hỏi, nói lý do
    bằng lời của web chứ không bằng chữ của server, và lần thử kế đi qua; mất mạng thì hộp giữ câu hỏi và
    nói không tới được server; sang cuộc trò chuyện khác trước khi canvas lưu xong thì không gửi gì;
    canvas phủ lên chat được cất đi khi câu hỏi đã đi qua để câu trả lời hiện ra, còn nguyên cả canvas
    lẫn câu hỏi khi server từ chối, Escape trong hộp chỉ đóng hộp, và không đụng tới canvas người mở ở
    cuộc khác trong lúc câu hỏi còn trên đường; hỏi tắt khi lượt của tab đang chạy và bật lại khi xong,
    khi kênh khác đang chạy lượt, khi cuộc trò chuyện chờ quyết định về một công cụ, khi đã hết ngân
    sách, và chỉ nói một lý do một lúc: quyết định trước ngân sách, lượt đang chạy trước cả hai; nhóm
    "sending the errors a page reported from the canvas beside the chat": lỗi trang báo đi thành một
    tin duy nhất nêu canvas mà không nêu đoạn nào, chỉ khi người bấm gửi, không lưu canvas và không
    ghi canvas đang mở). Hàm
    dùng chung: `web/src/test/canvas-pick.ts` (chọn chữ trên DOM như một cú kéo để lại, trong trang đọc
    hay trong ô sửa; đặt dòng chữ ngoài canvas lên trang và dọn đi sau mỗi test), `web/src/test/canvas-ask.tsx` (thanh hỏi đứng riêng với hàm lưu và hàm gửi giả), và
    `FakeBackend.refuseMessage` (POST tin nhắn từ chối với đúng trạng thái và `detail` đã đặt)
  - Playwright: `canvas-ask.spec.ts` (ở 1440 px: đoạn chọn trong ô sửa bằng `setSelectionRange` đi cùng
    câu hỏi với đúng `line_start` và `line_end`, câu hỏi và câu trả lời hiện trong thread, chip ghi chú nằm
    ngay dưới tin của người và mở ra đúng ghi chú, canvas vẫn ở cạnh chat; đoạn chọn bằng phím —
    `Shift+ArrowRight` từng chữ, vì `End` trên Mac nhảy tới cuối văn bản chứ không phải cuối dòng — được đề
    nghị khi còn chọn và hết cùng con trỏ; đoạn chọn trong canvas đang đọc bằng một `Range` dựng qua
    `page.evaluate`; ba lần nhấp chọn đúng đoạn văn dưới nó, đoạn đầu, đoạn giữa và đoạn cuối, kể cả khi
    Chromium để vùng chọn kết thúc ở một phần tử nằm ngoài vùng đọc như thanh hỏi; ở 390 px canvas phủ lên
    chat được cất đi sau khi gửi để câu hỏi và câu trả lời hiện ra); `touch-targets-phone.spec.ts` ("the
    buttons of the bar that asks about a passage of the canvas are big enough for a finger": nút hỏi, ô
    câu hỏi, Gửi và Huỷ ≥40px mỗi chiều ở 390 px)
- **Canvas trên web: trang html và mermaid chạy trong khung sandbox không dính gì tới app; bản mới
  thay khung sau một giây đứng yên, trang tự đi sang địa chỉ khác thì bị gỡ**
  - vitest: `web/src/components/canvas/canvas-frame.test.tsx` (khung, cửa sổ của nó và các tin nó
    gửi dựng bằng `web/src/test/canvas-frame.tsx`, dùng chung với `canvas-frame-keyboard.test.tsx`)
    nhóm "the page of a canvas, in its
    frame" ("runs the page in a frame that has a script and nothing of the app": `sandbox` đúng bằng
    `allow-scripts` — thêm `allow-same-origin` là test đỏ —, `allow` là `fullscreen`, `referrerpolicy`
    là `no-referrer`, tiêu đề của canvas; địa chỉ là route `render` không kèm phiên bản; nói đang tải
    tới khi trang tải xong lần đầu; báo cho panel bản vừa đưa lên), nhóm "a newer version of the page"
    (khung được thay bằng khung mới một giây sau lần đổi bản cuối, chờ bản đứng yên rồi đưa bản cuối
    lên; người đang giữ focus trong trang thì giữ khung và mời bản mới bằng một nút, nút đưa lên bản
    đang có lúc bấm, không có bản mới thì không có nút; tab ẩn thì chờ tab hiện lại rồi đưa lên ngay,
    bản vẫn thế thì không đưa lại), nhóm "the live stream" (luồng nối lại sau khi rớt thì đưa trang
    lên lại với bản mới nhất; lần nối đầu và luồng chưa từng nối thì không), nhóm "a page that moves
    to another address" (tải lần thứ hai là bị gỡ và người được báo, tải một lần dù lâu thì không;
    "takes a late load of the frame it replaced for no load of its own": `load` của khung cũ tới sau
    khi khung mới được hẹn mà chưa được vẽ thì khung mới vẫn nói đang tải, lần tải thật đầu của nó
    không làm nó bị gỡ và lần thứ hai vẫn gỡ nó; đã
    gỡ thì đứng yên tới khi người bảo chạy lại, khi ấy bản mới nhất được đưa lên và chạy như mọi
    trang; "is told to the panel under the version that was up, though a newer one was waiting its
    second"; trang đã gỡ thì bỏ nút mời bản mới);
    `web/src/components/canvas/canvas-panel-kinds.test.tsx` nhóm "a canvas shown as a page" (html của
    agent mở thành trang trong khung, html vừa tạo ở đây mở ở Sửa trong phông code, sơ đồ mermaid cũng
    là một trang; "turns to the page at once when nothing is unsaved, and sends nothing": đổi ngay
    trong cú bấm; "saves what was typed before turning to the page, and says so on the View button
    meanwhile"; "keeps the last click: Edit pressed while the save is out stays in Edit when it
    lands"; lịch sử mở trong lúc lưu thì vẫn mở; lưu bị từ chối thì hiện bản đã lưu gần nhất và nói
    chữ đang gõ chưa có trong đó; "opens the saved page in a new tab, and only once nothing is
    unsaved": `window.open` với `noopener,noreferrer`; canvas mới biết tên mà chưa đọc xong thì chưa
    có trang để mở; trang có ký tự ẩn thì nói; canvas đã xoá thì không còn trang để mở) và nhóm "a
    kind the web does not know" (hiện thành chữ trong phông code, không khung, không hình);
    `web/src/hooks/use-save-then-show.test.ts` (lần chuyển sang cái server đang giữ: đổi ngay khi
    không có gì phải chờ và không xin lưu, chờ lần lưu và nói đang chờ, lần lưu ném lỗi vẫn đổi và
    thôi nói chờ, lần chuyển sau thắng lần đang chờ, huỷ thì bỏ lần đang chờ)
  - Playwright: `canvas-render.spec.ts`, trang html do `web/e2e/mock-render.ts` trả kèm đúng chính
    sách và reporter của server (hai tệp mà `tests/test_render_fixtures.py` giữ bằng server từng byte;
    mermaid không được phục vụ vì trang ấy tải thư viện từ CDN); `web/e2e/render-page.ts` dựng trang
    và mở nó trong canvas, dùng chung với `canvas-keyboard.spec.ts`. Mở thẳng địa chỉ render: "has an
    origin of its own and no storage, by the policy it comes with" (`window.origin` là `null`, đọc
    `localStorage` ném `SecurityError`; bỏ `sandbox` khỏi `render-policy.txt` là test đỏ). Trong khung
    ở 1440×900: "runs under an origin that is not the app's, and what it throws is listed"; "fills
    the panel, down to the lower edge of the room the canvas has" (mép dưới của khung trùng mép dưới
    của `.canvas-saved` và khung cao hơn nửa cửa sổ; hộp `.canvas-frame-box` không co giãn hoặc
    không còn là flex cột thì khung chỉ cao 150px và test đỏ); "cannot call the api: the policy
    stops the request before it leaves, and says so" (không request nào đi từ khung, lời báo là
    `connect-src blocked`); "cannot keep anything in the browser's storage";
    "cannot put a dialog over the app"; "cannot move the app to another address" (`top.location` ném
    `SecurityError`, app vẫn ở địa chỉ cũ); "is taken out when it moves itself to another address,
    and the person is told" (trang đổi `location` sau khi tải xong; trang tự đi ngay lúc còn đang
    parse thì không bị bắt, đó là phần rủi ro đã ghi nhận). Ở 390×844 cảm ứng: "gets most of the
    screen, and its errors fit a finger without a sideways scroll" (khung cao ít nhất 60% màn hình,
    mọi nút trong dock ≥40px, một từ 300 ký tự trong danh sách lỗi không làm cuộn ngang).
    `web/e2e/canvas-overflow.ts` là hàm đo cuộn ngang dùng chung với `canvas.spec.ts`, đo cả
    `.canvas-errors-list`
- **Canvas trên web: trang trong khung tự lấy focus thì bàn phím về lại chỗ người đang gõ; người đưa
  bàn phím cho trang bằng một cú bấm trong trang hoặc Tab, và lời mời ấy chỉ dùng được cho lần chuyển
  focus đi cùng nó; trang giành tới lần thứ năm thì bị gỡ; trang giành lúc cửa sổ ở phía sau thì bàn
  phím về lại khi người quay lại, kể cả khi quay lại chỉ bằng bàn phím và kể cả khi khung được dựng
  lên lúc cửa sổ đã ở phía sau; khung nói khi bàn phím đang ở trang**
  - pytest: `tests/test_render_pages.py`, bốn test của reporter về lời chào và cú bấm (xem mục trang
    render ở trên): cú bấm chỉ được nói khi trình duyệt bảo một người đã bấm, lúc con trỏ xuống và
    lần nữa lúc nó lên (`pointerup`, `mouseup`); `click` không được nói
  - vitest: `web/src/hooks/use-frame-focus-guard.test.tsx` nhóm "the keyboard a page took unasked"
    (một lần giành là khung có focus rồi cửa sổ app nhận `blur`; app chờ `ATTEST_GRACE_MS` (50 ms)
    xem reporter có nói tới cú bấm không, tới mili giây cuối khung vẫn giữ focus, rồi bàn phím về
    đúng phần tử vừa mất focus bằng `focus({ preventScroll: true })`; "is waited on for no longer
    than a tenth of a second, in which the keys go to the page": khoảng chờ không bao giờ quá 100 ms;
    không phần tử nào giữ focus, phần tử ấy đã bị gỡ hoặc đã bị khoá thì khung bị `blur`; phần tử mất
    focus từ task trước không được trả focus; không bao giờ trả focus cho chính khung; người tự đưa
    focus đi chỗ khác trong lúc chờ thì focus ở yên đó và lần giành vẫn tính; trang tự buông trước khi
    hết giờ vẫn bị tính; trang bị gỡ ở lần thứ năm thì bàn phím vẫn về chỗ cũ; cửa sổ mất focus vì
    người sang cửa sổ khác thì không tính và không đụng tới focus), nhóm "the keyboard the person
    offers the page" (reporter nói tới cú bấm trước khi trang lấy focus, hoặc trong lúc chờ, thì trang
    giữ bàn phím và không lần nào bị tính, nói bao nhiêu lần cũng vậy; "comes too late once the
    keyboard is back": cú bấm nói sau khoảng chờ không xoá lần giành đã tính; Tab là phím cuối thì
    trang giữ bàn phím, Shift+Tab cũng vậy; Tab kèm `ctrlKey`, `metaKey` hay `altKey` không phải lời
    mời và còn thu lại lời mời đang có như mọi phím khác; "is over a task after Tab that did not
    bring the focus to the page": app giữ phím Tab cho mình, như danh sách lệnh trên ô soạn tin, thì
    một task sau lời mời hết, trang lấy focus lúc ấy bị trả bàn phím và tính một lần giành; "is over
    once a press was told and the frame did not take the focus in the time a page is given": cú bấm
    được nói mà sau `ATTEST_GRACE_MS` khung vẫn chưa có focus thì lời mời hết; focus tới 30 ms sau cú
    bấm thì lời mời còn, và cú bấm được nói 30 ms sau khi trang lấy focus vẫn là lời mời (hai test
    neo vào tình huống trình duyệt bận, không neo vào hằng số: rút khoảng chờ xuống vài mili giây là
    đỏ); "is made anew by the second telling of one tap, long after the first was over": ngón tay
    trên điện thoại được nói hai lần, lần đầu hết hạn rồi lần hai vẫn đưa được bàn phím; "is made
    anew when the press is told to be over, for the page that takes the keyboard at the click of a
    button a person held": cú bấm được nói, 150 ms sau (người giữ nút chuột chừng ấy) ô đang gõ vẫn
    giữ focus, lúc nhả được nói thêm một lần rồi khung mới lấy focus thì trang giữ bàn phím và không
    lần nào bị tính; "is not made by a button that is still held": cùng tình huống mà không có lời
    nào lúc nhả thì bàn phím về ô đang gõ và tính một lần giành, tức luật hết hạn không bị nới;
    "stands for as long as the page has the keyboard, however long ago the press was told and
    however often the page is looked at again": cú bấm được nói, khung lấy focus, rồi sáu lần tab bị
    ẩn một giây và hiện lại, mỗi lần hiện khung được xét lại: trang vẫn giữ bàn phím và không lần nào
    bị tính, tức lời mời đứng vững chừng nào khung còn giữ focus chứ không hết theo đồng hồ; cho lời
    mời luôn hết hạn là test đỏ; hạn
    tính từ cú bấm được nói sau cùng; "is made to the frame on show and to no other": lời mời bằng cú bấm
    hay bằng Tab không theo sang khung thay thế; `pointermove`, `pointerover`, `pointerenter`,
    `wheel`, `scroll`, `mousemove`
    trên khung không phải lời mời, và `pointerdown` trên hộp của khung trong app, cái reporter không
    nói tới, cũng không; lời mời đứng vững khi con trỏ di chuyển, rời đi hay cuộn ở chỗ khác và khi
    bấm lên hộp của khung; `pointerdown` ở chỗ khác trong app, một phím khác Tab bấm trong app, Tab
    đưa focus tới một nút của app, hay focus tới một phần tử của app thì lời mời hết và lần giành kế
    tiếp bị trả lại; focus tới chính khung thì không), nhóm "what the app's own handlers keep to
    themselves" (bốn loại sự kiện vẫn được thấy khi handler của app gọi `stopPropagation`: nghe ở pha
    capture), nhóm "a page that goes on taking the keyboard" (bốn lần thì chưa báo, lần thứ năm báo
    đúng một lần và chỉ khi hết khoảng chờ; "is reported again each time it does after that, where
    the app left the page up"; app nhận `blur` nhiều lần trước khi bàn phím về thì vẫn là một lần
    giành; bàn phím do người đưa thì bao nhiêu lần cũng không tính; khung mới thay khung cũ bắt đầu
    từ không, và không phải trả lời cho khung cũ đang được chờ; báo cho callback mới nhất), nhóm "a
    page that held the app up while it had the keyboard" (khoảng chờ tới hạn trễ hơn `LATE_MS`
    (100 ms): lần đầu của một khung chỉ là một lần giành như mọi lần khác, bàn phím về chỗ cũ, tính
    một lần và trang không bị báo, vì có thể chính app đang bận; từ lần thứ hai trang bị báo, và mỗi
    lần sau đó; trễ đúng `LATE_MS` thì chưa là trễ, quá một mili giây thì là trễ; "has the keyboard
    for one task more when the wait comes due late, and no longer": tới hạn trễ thì guard nhường
    đúng một task cho cú bấm đang nằm trong hàng đợi của cổng rồi mới kết luận; "is not held to have
    taken it when the press is told right after the wait came due late": cú bấm được nói trong task
    ấy thì trang giữ bàn phím, không bị báo, không bị tính, và lần trễ ấy không được nhớ cho lần
    sau; khung thay thế bắt đầu lại từ chưa trễ lần nào; khoảng chờ kết thúc bằng một cú bấm thì dù
    cú bấm tới trễ cũng không báo), nhóm "the keyboard a page took while the
    window was behind" (cửa sổ app mất focus về thứ không phải khung thì phần tử đang giữ bàn phím
    được nhớ; trang lấy focus trong lúc ấy, cửa sổ không được báo gì: khi cửa sổ nhận `blur` về khung
    mà không phần tử nào vừa mất focus thì bàn phím về phần tử đã nhớ chứ không rơi xuống `body`;
    `focus` rồi `blur` liền nhau chỉ là một lần giành, và cửa sổ khi ấy đã ở phía trước vì thứ nó mất
    focus về là chính trang của nó: "does not go to what had it before the window said it is in
    front and that it lost the focus to the page, once the person let that go" (người buông phần tử
    đã nhớ rồi thì lần giành sau không đưa bàn phím về nó nữa; huỷ task 0 ms của `focus` ở mọi
    `blur`, kể cả `blur` về khung, là test đỏ); cửa sổ nhận `focus` thì một task sau khung
    được xét lại, chờ đủ khoảng chờ rồi bàn phím về phần tử đã nhớ và tính một lần giành; "is looked
    for a task after the window says it is in front, when the browser has put the focus back": xét
    ngay trong `focus` là test đỏ; người đã quay lại và tự buông focus thì phần tử đã nhớ bị quên;
    tab hiện lại thì khung được xét lại, tab đang ẩn thì không; cửa sổ chưa nói nó ở phía trước mà
    con trỏ đã di chuyển hay bấm trong app thì khung cũng được xét lại; cửa sổ chưa từng ở phía sau,
    hoặc người đã quay lại, thì con trỏ trong app không mở khoảng chờ nào; người quay lại bằng một
    cú bấm trong trang thì trang giữ bàn phím, kể cả khi reporter nói tới cú bấm ấy sau `focus` của
    cửa sổ, và không lần nào bị tính; "goes back within a beat of the person coming back by the
    keyboard alone, which the app's window is told nothing of": không `focus` của cửa sổ, không
    `visibilitychange`, không sự kiện con trỏ, chỉ `document.hasFocus()` đổi thành `true`: lúc còn ở
    phía sau thì ba nhịp trôi qua khung vẫn giữ focus, quay lại thì tới đúng nhịp kế tiếp
    (`BEHIND_LOOK_MS`, 200 ms) khung mới được xét, chờ đủ khoảng chờ rồi bàn phím về phần tử đã nhớ
    và tính một lần giành; "is looked for on a beat no slower than a fifth of a second": đo bằng
    đồng hồ chứ không so hằng số với một con số, người quay lại bằng bàn phím thì 200 ms cộng khoảng
    chờ sau bàn phím đã về phần tử đã nhớ, nên bỏ nhịp hay cho nhịp thưa hơn 200 ms đều là test đỏ;
    người quay lại bằng một cú bấm trong
    trang thì nhịp thấy khung mà không tính gì; nhịp thấy một phần tử của app đang giữ focus thì
    không đổi gì, con trỏ trong app sau đó vẫn được xét; nhịp đã thấy khung thì con trỏ trong app
    không mở khoảng chờ nào nữa và phần tử đã nhớ bị quên; "is looked for on the beat only while the
    window is behind, and on one beat however often it says so": một timer duy nhất dù cửa sổ nói hai
    lần, không timer nào trước khi cửa sổ ra sau và sau khi nó nói đã ở phía trước; nhịp thấy khung
    rồi thì dừng; cửa sổ nói `blur`, `focus`, `blur` trong cùng một task, tức người lướt qua cửa sổ
    app trên đường sang cửa sổ khác, thì task 0 ms của lần `focus` ấy bị huỷ chứ không chạy sau
    `blur` thứ hai mà coi như người đã về: "goes back within a beat of the person coming back by the
    keyboard alone to a window that went behind again before it was settled as back" (phần tử đã
    nhớ còn nguyên, trang lấy focus sau đó giữ nó qua ba nhịp, người quay lại bằng bàn phím thì sau
    một nhịp cộng khoảng chờ bàn phím về phần tử ấy và tính một lần giành), "goes back at a pointer
    in the app, where the window went behind again before it was settled as back" (con trỏ di chuyển
    trong app lúc ấy vẫn mở khoảng chờ), "is still looked for on the beat when the window went
    behind again before it was settled as back, until it says it is in front" (một timer qua ba
    nhịp, hết khi cửa sổ nhận `focus`); bỏ lệnh huỷ ấy là cả ba đỏ: nhịp dừng và phần tử đã nhớ bị
    quên trong lúc cửa sổ vẫn ở phía sau; khung được dựng lên lúc cửa sổ đã ở phía sau, tức
    `document.hasFocus()` là `false`
    lúc guard được dựng và không `blur` nào báo: "goes back within a beat of the person coming back
    by the keyboard alone to a window the page was put up behind": phần tử đang giữ focus lúc dựng
    được nhớ, ba nhịp trôi qua khung vẫn giữ focus, `hasFocus()` thành `true` thì tới đúng nhịp kế
    tiếp khung mới được xét, chờ đủ khoảng chờ rồi bàn phím về phần tử ấy và tính một lần giành;
    "goes back at a pointer in the app, where the window the page was put up behind has not said it
    is in front": con trỏ di chuyển trong app lúc ấy cũng mở khoảng chờ; "is looked for on the beat
    from the time the page is put up behind the window, until the window says it is in front": một
    timer ngay từ lúc dựng, hết khi cửa sổ nhận `focus`), nhóm "a guard that is put up" (hai
    listener `pointermove` và
    `pointerdown` gắn với `passive: true` và không có listener `wheel` nào, nên guard không bao giờ
    giữ một cú cuộn lại), nhóm "a guard that is taken down" (không để lại timer nào trong ba timer
    của nó, lời mời đang chờ hết hạn và nhịp xét lúc cửa sổ ở phía sau cũng dừng, không còn nghe cú
    bấm, gỡ đủ từng listener đã
    gắn với đúng cờ capture: sáu trên `document`, hai trên `window`);
    `web/src/components/canvas/canvas-frame-keyboard.test.tsx` nhóm "a page that takes the keyboard"
    (hộp `div.canvas-frame-box` chỉ mang `class` và `tabindex="-1"`, không còn thuộc tính nào tắt con
    trỏ của khung; một lần giành thì trang vẫn còn và ô đang gõ có lại focus; "does not keep what it
    took while the window was behind: the person is back in front, and so is the keyboard": cửa sổ
    mất focus, trang lấy focus, cửa sổ có lại focus thì ô đang gõ có lại bàn phím; "does not keep what
    it took behind the window when the person comes back by the keyboard alone, and nothing tells the
    app's window so": cùng tình huống nhưng cửa sổ app không nhận `focus`, chỉ `document.hasFocus()`
    đổi: sau một nhịp cộng khoảng chờ ô đang gõ có lại bàn phím, khung còn nguyên; lần thứ năm khung bị
    gỡ, lời báo là "Trang liên tục giành bàn phím nên đã bị dừng." kèm nút Nạp lại, panel được báo
    như khi trang tự đổi địa chỉ; đã gỡ thì đứng yên qua bản mới, nối lại và tab hiện lại; Nạp lại
    đưa khung mới lên và khung ấy lại có đủ năm lần; bàn phím người đưa bằng cú bấm trong trang thì
    sáu vòng cũng không bị gỡ, không có lời báo dừng nào, cả lời báo giành bàn phím lẫn lời báo trang
    tự chuyển địa chỉ, và bản mới chờ sau nút "Có bản mới"; trang tự giành thì không được coi
    là đang dùng, bản mới thay khung không cần nút; nút mời bản mới mất khi trang bị gỡ), nhóm "the
    press a page's reporter tells of" (cổng chỉ được nhận từ tin đầu tiên khung nói, và tin ấy phải
    là lời chào từ chính cửa sổ của khung dưới origin `null`: sau một lời báo, một tin bất kỳ hay một
    lời chào khác thì cổng tới sau bị bỏ, cổng đầu vẫn được nghe khi tin sau mang cổng khác, lời chào
    từ cửa sổ khác hay từ không đâu không được nhận còn lời chào của chính khung sau đó vẫn được,
    lời chào dưới origin khác `null` không được nhận mà vẫn là tin đầu của khung; "is nothing the
    page can say to the window: only the port tells of it": `{type: "press"}` gửi lên cửa sổ không
    bao giờ là lời mời; qua cổng chỉ đúng `{type: "press"}` mới là cú bấm; một nghìn cú bấm qua cổng
    không tính vào năm mươi tin của khung, sau đó trang vẫn được nghe đủ bốn mươi chín lời báo; cổng
    của khung bị thay được đóng và handler cũ của nó không nói thay cho khung mới; cổng đóng khi
    trang bị gỡ vì đổi địa chỉ hay vì giành bàn phím; cổng đóng khi khung đi và không đóng khi khung
    chỉ được vẽ lại), nhóm "the page that has the keyboard" (khung giữ focus thì hộp mang
    `data-keyboard` và dòng "Bàn phím đang ở trang" với `role="status"` nằm trong hộp, khung vẫn là
    đúng phần tử cũ, focus về app thì cả hai mất; được xét lại ở `blur` và `focus` của cửa sổ, ở
    `focusin` và `focusout` của tài liệu; nhóm con "behind the app's window, which is told nothing of
    the focus a page takes there": cửa sổ đã nhận `blur` thì dấu được xét theo cùng nhịp 200 ms mà
    không cần sự kiện nào, hiện trong một nhịp kể từ lúc khung có focus và mất trong một nhịp kể từ
    lúc khung buông; người quay lại bằng bàn phím thì dấu hiện trong một nhịp; khung mới thay khung
    cũ lúc cửa sổ còn ở phía sau vẫn được xét theo nhịp ấy; nhịp của dấu dừng ở nhịp đầu tiên thấy
    `document.hasFocus()` là `true`, và cả hai nhịp dừng khi khung đi; khung được dựng lên lúc cửa sổ
    đã ở phía sau, không `blur` nào báo, thì dấu cũng hiện trong một nhịp kể từ lúc khung có focus,
    hai nhịp của dấu và của guard chạy ngay từ lúc dựng, nhịp của dấu dừng ở nhịp đầu tiên thấy cửa
    sổ ở phía trước và nhịp còn lại dừng khi khung đi; khung thay khung đang giữ bàn phím thì không
    mang dấu ấy;
    khung đi thì gỡ đủ listener đã gắn lên `window` và `document`), nhóm "a stopped page the person
    asks for again" (lời báo đã dừng là một nút DOM khác với hộp của khung cũ và của khung mới; sau
    Nạp lại, nút vừa bấm mất nên focus được đặt lên hộp của khung mới bằng `focus({ preventScroll:
    true })` đúng một lần; trình duyệt không cho nút nhận focus khi bấm thì focus ở yên chỗ người để
    nó; các khung sau không kéo focus về nữa, kể cả khi người đã buông focus và không phần tử nào
    giữ nó; khung không ai xin thì không dời focus, kể cả khi focus đang ở `body`)
  - Playwright: `canvas-keyboard.spec.ts`, Chromium thật với reporter thật của server. Ở 1440×900:
    "goes to the page with a click in it and stays there, however often the person goes back and
    forth" (sáu vòng bấm ô soạn tin rồi bấm vào ô của trang và gõ ngay mười phím cách nhau 30 ms, lâu
    hơn khoảng chờ: trang nghe đủ mười phím mỗi vòng, bàn phím rời trang đúng số lần người lấy nó đi,
    ô soạn tin không nhận phím nào và trang không bị gỡ; đây là test giữ thứ tự giữa cú bấm reporter
    nói và `blur` của app: xét khung ngay trong `blur`, không chờ, thì cú bấm tới sau `blur` bị coi
    là trang tự giành. Trong Chromium của Playwright cú bấm đã nằm trong hàng đợi trước khi cửa sổ
    app nhận `blur`, nên ở đây một timer 0 ms cũng đủ: độ dài 50 ms của khoảng chờ chỉ được giữ bằng
    các test vitest ở trên); "is, for the app, with the page's frame inside the dock once the person
    clicks in the page" (sau một cú bấm thật vào ô của trang, `document.activeElement` của app chính
    là `iframe` của canvas và nằm trong phần tử của dock: đó là thứ duy nhất dock dựa vào để biết
    người đang giữ bàn phím trong nó, nên canvas tự mở không thay trang ấy); "is
    shown to be with the page by a line around it and a word over it, which move nothing and let the
    pointer through" (khung không đổi vị trí hay kích thước, viền là `solid 2px`, dòng chữ nằm góc
    trên bên phải trong khung, bấm lên dòng chữ là bấm vào trang bên dưới; về ô soạn tin thì viền và
    dòng chữ mất); "stays with a message being written when the page focuses itself" (trang gọi
    `window.focus()` rồi focus ô của nó; khi trang đã thấy `blur` của chính nó thì ba mươi phím gõ
    vào đủ ô soạn tin và trang không nghe phím nào); "goes to a page that takes it at the click,
    however long the person held the button and however often" (nút của trang gọi `preventDefault()`
    ở `mousedown` nên cú bấm không dời focus, rồi trang focus ô của nó trong `click`; sáu vòng bấm ô
    soạn tin, `mouse.down()` lên nút, giữ 150 ms trong lúc ô soạn tin vẫn giữ focus, `mouse.up()`
    rồi gõ ngay mười phím: trang nghe đủ mười phím mỗi vòng, bàn phím rời trang đúng số lần người
    lấy nó đi, ô soạn tin không nhận phím nào và trang không bị gỡ; reporter chỉ nói lúc con trỏ
    xuống là test đỏ); "stays with the message when the page takes it while the button is still
    held, long after the press" (đối chứng: cùng nút ấy nhưng trang tự focus bằng timer 150 ms sau
    `mousedown`, nút vẫn đang giữ: bốn lần bàn phím về ô soạn tin, phím gõ lúc còn giữ nút vào ô
    soạn tin, lần thứ năm trang bị gỡ, tức lần nào cũng bị tính); "stays with the message when the
    keys meant for it press a button of a page that goes on taking it" (trang cứ 100 ms lại focus
    một nút của nó, người gõ Enter liên tục: Enter rơi vào nút ấy trong khoảng chờ là một `click`
    trình duyệt bảo là của người, nhưng reporter không nghe `click`, trang bị gỡ sau năm lần và ba
    mươi phím gõ sau đó vào đủ ô soạn tin; để reporter nói mọi `click` `isTrusted` là test đỏ:
    trang giữ được bàn phím và không bao giờ bị gỡ); hai test "stays with the message when that page
    has the click those keys make say a pointer made it" và "… say it is a pointer coming up" (cùng
    trang ấy, nhưng trước khi giành nó viết lại getter `detail` trên `UIEvent.prototype` cho trả 1,
    hoặc getter `type` trên `Event.prototype` cho trả `pointerup`: trang vẫn bị gỡ sau năm lần và
    ba mươi phím gõ vào đủ ô soạn tin; reporter nghe `click` và lọc bằng `detail > 0` hay bằng
    `type` là hai test đỏ ở Chromium, trang giữ bàn phím mà không ai bấm chuột vào nó); "stays with
    the message when the page makes up a press of its own before it takes it" (script của trang tự
    `dispatchEvent` bốn sự kiện reporter nghe, `pointerdown`, `mousedown`, `pointerup`, `mouseup`,
    rồi cả `click`, đều với `detail: 1`, lên ô của nó, trang nghe đủ cả bốn, rồi lấy focus:
    reporter không nói tới cú bấm trình duyệt không bảo là của người, bàn phím về ô soạn tin, ba
    mươi phím gõ vào đủ ô soạn tin, trang không nghe phím nào và dòng "Bàn phím đang ở trang" không
    hiện; bỏ điều kiện `isTrusted` trong reporter là test đỏ); "is not kept by a page that takes it while
    nothing in the app holds it" (khung bị `blur`, focus của app ở `body`; bỏ `taker.blur()` trong
    guard là test đỏ); "stays with the message when the page takes it as the pointer passes over"
    (trang gọi `window.focus()` trong `pointermove` của nó: con trỏ đi qua trang không phải lời mời,
    chữ gõ trước và sau đều vào ô soạn tin); "stays with the message while the wheel turned over the
    page scrolls the page" (ngay sau khi gõ, lăn chuột trên trang thì trang cuộn và chữ gõ tiếp vẫn
    vào ô soạn tin: khung luôn nhận con trỏ); "goes to the page with Tab" (cũng cho thấy hạn một
    task của lời mời bằng Tab là đủ trong trình duyệt thật: cửa sổ app nghe `blur` trước khi task ấy
    tới; bỏ lời mời của Tab là test đỏ, còn lời mời hết hạn thế nào thì trình duyệt không phân biệt
    được, chỉ các test vitest ở trên giữ);
    "stays with the message when the page takes it after Tab pressed with Control, which goes
    through none of the app's controls" (Control+Tab không dời focus; trang lấy focus sau đó thì bàn
    phím về ô soạn tin và ba mươi phím gõ vào đủ ô soạn tin; coi Control+Tab là lời mời và để lời
    mời ấy sống quá một task là test đỏ, chỉ bỏ điều kiện phím bổ trợ thì hạn một task đã che và
    phần ấy do vitest giữ); "stays where the person
    had it while a page that goes on taking it is stopped" (trang `setInterval(window.focus, 100)` bị
    gỡ kèm lời báo, ba mươi phím gõ sau đó vào đủ ô soạn tin mà không cần bấm lại, Nạp lại đưa trang
    mới lên và focus nằm trên `canvas-frame-box` chứ không ở `body`); "is not given to a page that
    wrote itself anew, whose presses nothing vouches for" (trang gọi `document.open()`, xoá mọi
    listener trên cửa sổ của nó kể cả của reporter: bốn cú bấm vào trang đều bị trả bàn phím về ô
    soạn tin, cú thứ năm gỡ trang, năm phím gõ xen giữa vào đủ ô soạn tin). Ở 390×844 cảm ứng: "goes
    to the page with the first tap, which the page hears as a pointer pressed" (cú chạm đầu tới trang
    như một `pointerdown`, mười phím gõ sau đó trang nghe đủ, dòng chữ nằm trong bề ngang của khung,
    khung không dời và không có cuộn ngang). Trang giành lúc cửa sổ ở phía sau chỉ có test vitest:
    Chromium của Playwright luôn coi trang là đang có focus nên cửa sổ không bao giờ nhận `blur` vì
    người sang cửa sổ khác. Trong vitest, `web/src/test-setup.ts` cho `document.hasFocus()` trả
    `true` ở mọi test: jsdom chỉ nói cửa sổ có focus sau khi một phần tử được focus, còn test là một
    người đang ngồi trước app; test nào cần cửa sổ ở phía sau thì spy `hasFocus` thành `false`, trước
    khi dựng khung nếu khung phải được dựng ở đó. Phần còn lại đã ghi nhận: phím bấm trong khoảng
    chờ, tối đa 50 ms giữa
    lúc trang giành và lúc bàn phím được trả lại, thì tới trang; trang giành lúc cửa sổ ở phía sau
    mà người quay lại bằng bàn phím, không có `focus` của cửa sổ, tab không đổi trạng thái và con
    trỏ không động, thì phím tới trang tối đa một nhịp cộng khoảng chờ (250 ms) rồi bàn phím về; khung
    được dựng lên khi cửa sổ đã ở phía sau từ trước thì theo cùng nhịp ấy ngay từ lúc dựng, và phần
    tử được nhớ là cái đang giữ focus lúc dựng; trang chặn hành vi mặc định của cú bấm
    (khung không nhận focus) rồi tự focus hơn 50 ms sau lúc con trỏ xuống mà nút vẫn đang giữ, hoặc
    hơn 50 ms sau lúc nhả (chẳng hạn sau một hoạt cảnh), thì bị coi là tự giành: lời mời của cú bấm
    ấy đã hết; hai sự kiện lúc nhả, `pointerup` và `mouseup`, thừa nhau với chuột trong Chromium (bỏ
    riêng một cái thì test trình duyệt vẫn xanh), từng cái chỉ được giữ bằng test chữ của reporter;
    Enter hay phím cách rơi vào khoảng chờ thì tới trang như mọi phím khác, nhưng không còn là lời
    mời dù trang cho sự kiện của nó tự nói gì; tha lần trễ đầu của một khung có cái giá của nó: ở
    nơi khung chạy trên cùng luồng với app, một trang giành bàn phím rồi chặn luồng thì nghe mọi
    phím gõ trong lúc luồng bị chặn, và mỗi phần tử khung có hai khoảng nghe như thế trước khi trang
    bị dừng, không phải một
- **Canvas trên web: svg và ảnh hiện thành hình từ bản đã lưu; ảnh chỉ để xem; hình không tải được
  thì phân biệt hình hỏng, bản đã mất, server lỗi và mất mạng**
  - vitest: `web/src/components/canvas/canvas-image.test.tsx` nhóm "a picture of a canvas" (hình là
    `raw?version=n` của đúng bản được giao, dưới tên canvas; svg mang lớp `vector`; mỗi bản mới được
    báo lên một lần và vẽ từ địa chỉ của chính nó) và nhóm "a picture that does not load" (địa chỉ
    vẫn trả lời thì cái nó giữ không phải hình: nói hình hỏng; "gives the agent a drawing the server
    holds that does not draw, once": chỉ svg mới được báo cho agent, và một lần; bản đã mất thì đọc
    lại canvas chứ không đổ cho hình; server đang lỗi thì không đổ cho hình hay bản nào; địa chỉ
    không trả lời thì chờ mạng và không nói gì với agent; luồng nối lại sau khi rớt thì vẽ lại, hình
    đang hiện thì để yên, hình hỏng thì không thử lại; hai lần kiểm cùng bay thì lần mới nhất quyết
    định; hình đi thì bỏ lần kiểm còn bay); `web/src/hooks/use-canvas-image.test.ts` (canvas ảnh mở
    ra là đã đọc và đã lưu với chữ rỗng không bao giờ được gửi, ảnh mới tới qua luồng thì đọc một lần
    và chỉ chuyển sang bản ấy, ảnh được khôi phục là bản mới nhất, vẫn không có chữ và không có gì
    để lưu); `web/src/components/canvas/canvas-panel-kinds.test.tsx` nhóm "a canvas shown as a
    picture" (svg của agent vẽ từ bản đã lưu, không có trang để mở và vẫn sửa được; "shows an image
    only to look at, even when it was just made, with nothing to copy": chỉ có Xem, không ô sửa,
    không nút chép, không danh sách lỗi) và nhóm "asking about a passage of a canvas shown as what
    the server holds" (thanh hỏi và hộp đang mở biến mất khi chuyển từ chữ của html, svg hay mermaid
    sang cái nó hiện; ảnh không có chữ để chọn nên không có gì để hỏi);
    `web/src/components/canvas/canvas-saved-view.test.tsx` nhóm "what a drawing reports, in the
    panel" ("stays one picture however often the panel is drawn again"; svg mà trình duyệt không vẽ
    được dù server giữ nó thì vào danh sách lỗi để gửi agent; bản kế là một hình riêng và không lỗi
    nào tính cho nó; "reads the canvas again when the version it draws is gone, and draws the one
    that took its place"; "draws a picture that did not arrive again when the activity stream comes
    back"); `web/src/components/canvas/canvas-history-kinds.test.tsx` (lịch sử của ảnh hiện mỗi bản
    thành một hình riêng, không có dòng để so, không có ô chọn; khôi phục một ảnh cũ chỉ bằng lệnh
    khôi phục và hiện nó là bản mới nhất; với canvas chữ, một dòng dài quá 2000 ký tự trong diff bị
    cắt kèm số ký tự đã bỏ)
- **Canvas trên web: lỗi trang báo được đếm và liệt kê; chỉ tới agent khi người bấm gửi, trong một
  tin rào lỗi lại như dữ liệu; trang không còn được nghe thì panel nói ra, kể cả khi chưa có lỗi nào**
  - vitest: `web/src/lib/frame-messages.test.ts` nhóm "what a page in the canvas frame may tell the
    panel" (nhận lời báo từ chính cửa sổ của khung, origin trình duyệt ghi là `null`; bỏ lời từ cửa
    sổ khác, từ không đâu — kể cả khi khung đã đi —, từ origin khác `null`, dữ liệu không phải object
    hay không phải `canvas-error`, `message` không phải chữ; giữ `message` rỗng; cắt `message` ở 2000
    ký tự và tên tệp ở 300, không bao giờ cắt giữa hai nửa một ký tự ngoài mặt phẳng cơ bản; vị trí
    không phải số đếm thành 0; "turns a position too large to be a count into 0, and keeps the
    largest that is one": `1e308`, `2 ** 53` thành 0 nên danh sách không hiện `1e+308`, còn
    `Number.MAX_SAFE_INTEGER` được giữ; không giữ gì của trang ngoài bốn trường), nhóm "the hello of
    a page's reporter" (lời chào trao cổng nó mang và không phải lời báo; nhiều cổng thì lấy cổng
    đầu, không cổng thì không có gì; không nhận từ cửa sổ khác, từ không đâu hay dưới origin khác
    `null`; lời báo mang cổng thì cổng bị bỏ; "reads what a message carries once, whatever the
    message is" và "reads nothing of a message that is not the frame's own" đếm số lần `data` bị đọc
    bằng một getter), nhóm "what a page's reporter says over the port" (chỉ object `{type: "press"}`
    là cú bấm; chữ `press` gửi lên cửa sổ không là gì cả), nhóm "where a page says its error is" và
    nhóm "a file the page asked for that did not arrive";
    `web/src/lib/clip-text.test.ts` (chữ vừa chỗ thì để nguyên, giữ các đơn vị đầu, bỏ cả cặp chứ
    không để lại nửa đầu của nó); `web/src/components/canvas/canvas-frame.test.tsx` nhóm "what the
    page reports" (chuyển đi lời báo từ cửa sổ của trang; không nhận gì từ cửa sổ khác, từ trang đã
    gỡ hay từ khung đã bị thay; thôi nghe khi khung đi; "tells the panel's newest listener alone,
    once the panel has given it another"; tệp không tới lúc máy mất mạng thì bỏ qua còn lời báo khác
    vẫn giữ, có mạng lại thì liệt kê; mỗi khung chỉ được nghe năm mươi tin: "hears fifty messages of
    a page that sends ten thousand, and reads nothing of the rest" đếm số lần `data` bị đọc bằng một
    getter, tin không phải lời báo cũng tính vào năm mươi tin ấy, khung mới có năm mươi tin của riêng
    nó, tin từ cửa sổ khác không tính cho trang; "tells the panel when it has heard the last of the
    fifty, reports or not, and not before": `onSilenced` được gọi đúng một lần ở tin thứ năm mươi,
    dù đó là lời báo, một tin bất kỳ hay chữ `press`, và không lần nào ở tin thứ bốn mươi chín; lời
    báo thứ năm mươi vừa được chuyển đi vừa được nói là tin cuối; mỗi khung được nói một lần của
    riêng nó; tin từ cửa sổ khác không làm panel được nói; chỉ listener mới nhất của panel được
    nói); `web/src/components/canvas/canvas-errors.test.tsx`
    nhóm "the errors a page reported" (không hiện gì khi trang chưa báo gì, nói số lỗi và giữ danh
    sách đóng tới khi được hỏi, dấu "+" theo việc khung đã thôi nghe trang chứ không theo số lời
    báo: bốn mươi chín hay năm mươi lời báo mà trang còn được nghe thì không có "+", đã thôi nghe thì
    "50+", "49+" hay "1+"; "says the page is no longer heard when it was heard out without one
    report, with nothing to list or send": chưa có lời báo nào mà khung đã thôi nghe thì nhóm chỉ có
    một dòng `role="status"` đúng câu "Trang gửi quá nhiều tin nên lỗi nó báo từ đây không còn được
    nghe" và không nút nào; "leaves saying so to the count once the page has reported something": đã
    có lời báo thì dòng ấy không hiện, dấu "+" nói thay;
    liệt kê cũ trước mới sau, "draws what the page wrote as text and never as markup, with hidden
    characters as marks": cả lời báo lẫn tên tệp ở dòng vị trí, `app[U+202E]gnp.js:3`) và nhóm
    "sending the errors to the agent" (chỉ có nút
    gửi khi có chat để gửi; "sends nothing until the button is pressed, however many errors arrive";
    lưu canvas rồi gửi một tin nêu trang và bản của nó; gửi năm lỗi mới nhất; nút bị giữ trong lúc
    lưu và gửi nên bấm bao nhiêu lần cũng gửi một lần; canvas chưa lưu được thì nói, không gửi và cho
    thử lại; server từ chối thì hiện lời của web và lần bấm sau gửi lại; lần gửi hay lần lưu ném lỗi
    thì nói một câu chung; tin xếp hàng tính là đã gửi và nút tắt tới khi trang báo lỗi mới; gửi
    đúng các lỗi có lúc bấm; nút tắt và nói lý do khi chat bận, chờ quyết định hay hết ngân sách);
    `web/src/lib/error-report.test.ts` (tin là các lỗi trong một rào giữa một dòng nói đó là gì và
    một dòng xin sửa; "says the fenced text was written by the page, and is data and not a
    request"; tên canvas nằm trong inline code trên một dòng kèm bản được đưa lên, tên có dấu huyền
    thì bọc bằng dãy dấu huyền dài hơn và đệm khoảng trắng khi nó mở đầu hay kết thúc bằng dấu ấy;
    ký tự ẩn hiện thành dấu thấy được; năm lỗi mới nhất của hai mươi lăm, đánh số từ một; lỗi 5000 ký
    tự cắt còn 2000, cắt theo chữ trang viết chứ không theo dấu thay ký tự ẩn; cả tin luôn nằm trong
    giới hạn của route chat; rào là ba dấu huyền và dài hơn mọi dãy dấu huyền trong lỗi, "lets the
    page end no fence early, whatever it writes"; vị trí lỗi chỉ nêu tới mức trang cho);
    `web/src/components/canvas/canvas-saved-view.test.tsx` nhóm "what the page of a canvas reports,
    in the panel" ("lists what the page itself says, and nothing another window says"; "sends the
    errors as those of the version the page was put up for, while a newer one waits its second";
    bản mới được đưa lên thì quên lỗi của trang cũ và đếm lại từ không, và gửi lại được dù lỗi trước
    đã gửi; trang bị gỡ vì tự đi nơi khác thì quên lỗi của nó; "counts every report the page makes
    and keeps the newest five to list"; "stops counting at fifty, says the page reported more, and
    lists the newest five of the fifty": mười nghìn lời báo thì thanh ghi "50+" và danh sách là lỗi
    46 tới 50; bốn mươi chín lời báo thì chưa có "+"; lời chào của reporter tới trước thì mười nghìn
    lời báo sau nó ra "49+" và danh sách là lỗi 45 tới 49, vì lời chào là một trong năm mươi tin;
    "says the page is no longer heard once it has said fifty things, though none was a report": bốn
    mươi chín tin không phải lời báo thì panel chưa hiện gì, tin thứ năm mươi thì hiện câu ấy, lời
    báo tới sau không đổi được nó, và trang kế tiếp thì không còn câu ấy;
    trang kế tiếp chưa nói gì thì không mang dấu "+" của trang trước; luồng nối lại thì trang được
    đưa lên lại và không lỗi nào
    tính cho nó; chat không nhận tin được thì nút gửi tắt và nói lý do; "does not send the errors
    when what was typed could not be saved, and says so")
  - vitest, cả App trên `FakeCanvas`: `web/src/app-canvas-ask.test.tsx` nhóm "sending the errors a
    page reported from the canvas beside the chat" (xem mục hỏi về một đoạn ở trên: một tin duy nhất
    với `selection: null`, không lần lưu và không lần ghi canvas đang mở nào)
  - Playwright: `canvas-render.spec.ts` ở 1440×900 ("is the only window whose reports are listed:
    one the app posts to itself is not"; "is heard for twenty of the twenty-five errors it throws,
    and the list keeps the newest five": reporter dừng ở hai mươi, test chờ bằng một lời báo trang tự
    gửi sau đợt lỗi nên số đếm là 21; "is heard out on fifty messages of the ten thousand reports it
    posts past the reporter": trang gọi thẳng `parent.postMessage` mười nghìn lần, tin đầu trong năm
    mươi tin là lời chào của reporter nên thanh ghi "49+" và đứng yên, danh sách là tin 45 tới 49;
    "is said to be no longer heard when what it posts by the thousand is no report at all": mười
    nghìn tin là chữ thường thì panel chỉ có câu trang không còn được nghe, không nút nào;
    "reports a picture from elsewhere that the policy keeps it from
    loading": cả dòng `img-src blocked` lẫn dòng `failed to load`, và request kết thúc với lỗi `csp`
    trước khi ra mạng; "reports a promise nothing caught as one error"; "shows at most two thousand
    characters of an error of five thousand": cái reporter gửi đi cũng đã chỉ dài 2000, đo ngay trên
    cửa sổ của app trước khi app cắt; "sends what it reported to the agent only when asked, as one
    message that fences it as data": chưa bấm thì không có POST nào, bấm thì đúng một tin với
    `selection: null`, từng dòng của tin khớp mẫu và tin hiện trong thread)
- **Canvas trên web: canvas nhập từ tệp nói nó từ đâu tới và đọc lại tệp bằng "Nhập lại"; lần nhập
  của agent là một thẻ trong hội thoại, và canvas vừa nhập tự mở như canvas vừa tạo**
  - vitest, thư viện: `web/src/lib/canvas-source.test.ts` (nguồn `workspace:<agent>/<đường dẫn>` cắt
    ở dấu `/` đầu tiên nên mã agent có gạch ngang và đường dẫn có `/` hay `:` vẫn đúng; thiếu agent
    hay thiếu đường dẫn thì không phải tệp; địa chỉ http và https là trang web; "is no link when the
    address names who logs in there, by a name, a password or both": địa chỉ có tên đăng nhập hay
    mật khẩu trước `@` thì không là nguồn nào, phần đăng nhập rỗng thì trình duyệt đã bỏ `@` nên vẫn
    là link, `@` trong đường dẫn, truy vấn hay mảnh thì giữ; "is no link when the host holds a
    character that would read as part of the words around it": mười lăm host có ngoặc, phẩy, nháy
    hay ký tự lạ mà bộ đọc URL của trình duyệt vẫn nhận đều không thành link, còn host gồm chữ, số,
    chấm, gạch và gạch dưới, có hay không có cổng, host chữ có dấu (thành `xn--…`) và địa chỉ số
    trong ngoặc vuông thì thành; "is no link to the app's own address, where a page an agent wrote
    would open as the app's": cùng origin với app thì không có link, khác cổng hay khác scheme thì
    có; "is a workspace file only when the text
    opens with the word, not when a link or a sentence holds it": link có đoạn `workspace:` trong
    đường dẫn vẫn là link, câu có chữ đó ở giữa thì không là gì; "gives the link whole, as the host
    it names is read, so a page cannot resolve it to somewhere else": `https:example.com/thuc don`
    viết thiếu `//` trả về `https://example.com/thuc%20don`, vì để nguyên thì một trang cùng scheme
    sẽ phân giải nó về chính địa chỉ của mình trong khi nhãn ghi host khác; `javascript:`, `data:`, `file:`, chuỗi
    rỗng và chữ thường đều không là nguồn nào); `web/src/lib/hidden-chars.test.ts` nhóm "what a path
    holds that nobody would see" (hai mươi ba ký tự server có lưu trong đường dẫn mà mắt không thấy,
    gồm khoảng trắng không phải dấu cách thường, ký tự chèn, bộ chọn biến thể, ô chữ nổi trống và
    vùng dùng riêng, mỗi ký tự hiện thành mã `[U+XXXX]`; dấu cách ở đầu hay cuối một đoạn của đường
    dẫn hiện thành `[U+0020]` từng dấu một, dấu cách giữa tên thì giữ; ký tự đảo chiều vẫn hiện
    thành dấu; tên tiếng Việt dạng tổ hợp lẫn dạng tách, tiếng Hàn dạng tách, tiếng Nhật, emoji và
    tệp chấm đầu giữ nguyên); `web/src/lib/canvas-import-call.test.ts` (tham số
    đọc từ mapping model gửi, lệnh cũ không có mapping thì không có gì; lần nhập "có `id`" là khi
    `id` là chữ không rỗng, như server đọc một giá trị trống; "reads a blank as Python's strip does,
    which is not what trim strips": `id` chỉ gồm U+001C tới U+001F hay U+0085 là trống như `strip()`
    của server, còn U+FEFF thì không; tên tệp là phần cuối của `path`, không
    có khi `path` thiếu, toàn dấu `/`, không phải chữ hay trống theo cách server đọc; đoạn cuối chỉ
    gồm dấu cách vẫn là tên tệp, vì server đọc đúng tệp tên đó; cả hai chỉ hỏi về lệnh nhập);
    `web/src/api/artifact-client.test.ts` ("asks for a canvas's file to be read again, on the version
    the text stands on": `POST …/reimport` dưới id đã mã hoá, body chỉ có `base_version`; "passes a
    read's signal, a re-import's, and a save's signal and keepalive, through to fetch": `signal` của
    lần nhập lại tới đúng `fetch`; "reads the newest version alone from a 409, which a picture's
    carries with no text": `conflictHeadOf` lấy `head_version` của 409 kể cả khi `content` là null,
    số viết thành chữ, 409 không phải của canvas, mã khác hay lỗi mạng thì không có gì)
  - vitest, máy trạng thái và hook: `web/src/lib/canvas-machine-sync.test.ts` ("reads once for a
    version it hears of twice while the read is out", "reads again for a version it hears of during
    a read that was asked for before it", "reads once for a version heard of twice across a
    conflict"); `web/src/hooks/use-canvas-imported.test.ts` (`imported(summary)` đọc bản mới như khi
    luồng báo; lần đọc đó hỏng thì trạng thái là "Có thay đổi mới" chứ không phải "Đã lưu"; luồng
    báo trước rồi reply tới, hay reply tới trước rồi luồng báo, đều chỉ một lần đọc và đúng chữ;
    được báo về bản đang hiện thì không đọc gì; người đang gõ thì giữ chữ của họ và nói có thay đổi
    đang chờ); `web/src/hooks/use-canvas-reimport.test.ts` ("sends nothing and says the text is
    not saved, whether the flush names none or one below the first": `flush` trả null, 0 hay -1 thì
    không có request nào và lời báo là "Chưa lưu được bản đang sửa nên chưa nhập lại."; "asks on the
    first version, which is one": `flush` trả 1 thì `POST` mang `base_version: 1`)
  - vitest, thành phần: `web/src/components/canvas/canvas-source.test.tsx` nhóm "where a canvas came
    from" (dòng nguồn nêu tên agent và tệp, thư mục và tên tệp tách riêng, cả đường dẫn ở `title`,
    nút nhập lại là nút phụ `ghost`;
    "shows what the server stores of a path and nobody would see as marks, on hover too": U+00A0,
    U+3164, U+FE0F và dấu cách cuối đoạn, những thứ server có lưu, hiện thành dấu ở thư mục, ở tên
    tệp và ở `title`; ký tự đảo chiều cũng vẫn hiện thành dấu; "shows a character that hides or
    reorders text in the agent's name as a mark as well": tên agent có U+202E thì ký tự đó hiện
    thành dấu ở thư mục và ở `title`; nguồn là trang web thì có
    link chữ "Mở nguồn (example.com:8787)", tên truy cập "Mở nguồn (example.com:8787) (mở trong tab
    mới)", `title` là cả địa chỉ, `target="_blank"` và `rel="noopener noreferrer"`, không có nút nhập
    lại; "shows no line for a link that carries a login, names a host no label can hold, or leads
    to the app": ba loại link đó không có dòng nguồn, không có thẻ `a` nào và mật khẩu không nằm
    trong trang; nguồn rỗng, chữ thường, `javascript:` hay `data:` thì không có dòng và không có link nào)
    và nhóm "reading a canvas's file again" ("saves the typing first, then asks on the version that
    holds it, and shows the file's text after one read": `PUT` rồi `POST` với `base_version` của
    `PUT` đó, đúng hai lần `GET`, lời báo đúng chữ "Đã nhập lại thành v3. Bản trước ở Lịch sử.",
    vẻ `info`, nằm ngay dưới dòng nguồn, dòng lịch sử ghi "Nhập từ tệp"; "shows the version the file
    became on the reply alone, when the stream says nothing of it": luồng im thì canvas vẫn đọc bản
    mới nhờ reply; chữ chưa lưu được thì không có
    `POST` nào và nói vậy; tệp không đổi thì nói vậy và không đọc lại; "reads a version saved
    unheard that holds what the file does, so what it calls the same is what shows": tệp giống một
    bản đã lưu mà canvas chưa nghe tới thì vẫn nói không đổi, và canvas đọc bản đó chứ không đứng ở
    chữ cũ; "says the typing is not saved when the save met a version written meanwhile, beside the
    choice that version asks for": lần lưu gặp 409 thì không có `POST` nào, thanh xung đột hiện và
    lời "Chưa lưu được bản đang sửa nên chưa nhập lại." vẫn đứng cạnh nó; "is held off while the
    file is read, takes no second press, and forgets what it said last": nút mang
    `aria-disabled="true"` chứ không bao giờ có thuộc tính `disabled`, ghi "Đang nhập…", bấm lần
    nữa không thành request thứ hai, lời báo trước biến mất; "is held off until the canvas has been
    read, and a press before then asks for nothing": luồng báo tên canvas trước khi lần đọc đầu về
    thì dòng nguồn đã hiện nhưng nút bị giữ, bấm không gửi gì và không nói gì, đọc xong thì bấm
    được; "stays held off on a canvas whose first read failed, which stands on no version to ask
    on": lần đọc đầu hỏng thì nút vẫn bị giữ và lần bấm không thêm câu nào vào lời panel đang nói;
    "gives a read that never answers thirty seconds, then says so and offers the button again":
    `AbortSignal.timeout` được gọi đúng với 30 000, ở 29 999 ms nút còn "Đang nhập…", thêm 1 ms thì
    nút trở lại và lời báo đúng chữ "Không nhập lại được: máy chủ không phản hồi", không đọc lại
    canvas; "cuts no read that answers in time, however long after the deadline was set"; "words a
    read the browser cut short itself as a lost connection, for no deadline ran out": request bị
    huỷ bằng `AbortError` chứ không phải `TimeoutError` thì lời báo là "Không nhập lại được: mất kết
    nối", không phải câu của hạn chờ, và nút trở lại; "says its
    news in a place that was there before it had any, and an error apart from it": phần tử
    `role="status"` nằm ngay sau dòng nguồn từ trước khi có lời nào, rỗng và không mang lớp
    `notice`, lời báo tin hiện trong chính phần tử đó, còn lời báo lỗi là một `role="alert"` khác;
    403, 410, 413, 422 mỗi cái một câu của web, so nguyên văn nên hai lời từ chối không lẫn chữ của
    nhau, vẻ `error`, không bao giờ hiện chữ của server, và không lần nào đọc lại canvas; câu của
    422 là "Tệp nguồn không đọc được, không phải tệp thường, hoặc không hợp với loại canvas này.",
    đúng cho mọi lý do server trả 422; 413 đúng một câu dù server trả câu chữ hay object cỡ; tệp
    không còn là 410; 409 thì đọc lại canvas, nói đúng chữ "Không nhập lại được: máy chủ có bản mới
    hơn" và không hiện gì của body từ chối; canvas đã xoá thì chỉ còn lời báo đã xoá, nút bị giữ và
    bấm lần nữa không gửi gì; 500, 507 và mất mạng nói bằng lý do của web, đúng chữ "Không nhập lại
    được: máy chủ không phản hồi", "…: hết chỗ lưu canvas trên máy chủ" và "…: mất kết nối", và
    cũng không đọc lại canvas) và nhóm "what a re-import said, once the canvas has a newer version"
    (lời báo tin lẫn lời từ chối đều biến mất khi agent ghi một bản mới hơn hay khi lần lưu của
    chính người dùng tạo ra một bản, và chỗ nói tin trở lại rỗng; "stands when a refusal follows a
    save of the typing, for that version is the one it was said on": bản do lần lưu trước khi nhập
    lại tạo ra không xoá lời từ chối vừa nói; "stands through the read of the version a conflict
    told of, when it was said before that read answered": lời báo 409 hiện khi canvas còn đứng ở v1
    và lần đọc lại còn đang treo, lần đọc về v2 thì lời báo vẫn đứng; "is taken back by a version
    newer than the one a
    conflict told of, not by that one": lời báo 409 đứng qua lần đọc bản mà 409 nêu và chỉ biến mất
    ở bản sau đó; "is said again by the next press, on the version the canvas has by then");
    `web/src/components/canvas/canvas-card-import.test.tsx` nhóm "a file read into a canvas, in the
    thread" (là thẻ canvas khi đang chạy và khi xong, thẻ thường khi hỏng, bị từ chối, bị dừng hay
    chờ duyệt; "Đang nhập…" kèm vòng quay; "Đã nhập · v1" khi lệnh không nêu canvas, "Đã nhập lại ·
    v4" khi có nêu, `id` rỗng, trống theo cách server đọc hay không phải chữ tính là không nêu; "Không đổi · v<n>" dù có nêu
    canvas hay không; không có thẻ ở đầu kết quả thì không có số phiên bản; nút mở canvas thẻ nêu)
    và nhóm "the title of a file being read into a canvas" (tên trong tham số, làm sạch như server;
    không có tên hay tên server sẽ từ chối thì lấy tên tệp, ký tự ẩn trong tên tệp hiện thành dấu;
    "shows what the server stores of a name and nobody would see as marks": tên tệp có dấu cách ở
    đầu hay cuối, U+034F, U+FE0F, U+3164, U+00A0, U+202F hay ký tự vùng dùng riêng hiện thành dấu
    trên thẻ đang chạy, tệp chỉ tên là U+3164 hay một dấu cách không còn là thẻ trống tên; tên model
    đặt thì vẫn làm sạch như server và giữ dấu cách giữa chữ;
    không có cả tệp thì gọi là Canvas; canvas thread đã biết thì lấy tên thread biết; thẻ đã xong
    không bao giờ lấy tên tệp; lệnh tạo không bao giờ lấy tên tệp);
    `web/src/hooks/use-canvas-auto-open-import.test.ts` (nhập không nêu canvas thì mở lặng lẽ, `id`
    rỗng, không phải chữ hay chỉ gồm ký tự `strip()` của server bỏ đi cũng vậy; nhập vào canvas có nêu thì không tự mở; thẻ `unchanged` thì
    không tự mở; chờ lệnh xong, lệnh hỏng hay bị từ chối thì không; `artifact_export` không bao giờ
    tự mở dù kết quả viết gì; "does not open for an import the conversation's saved history holds,
    only for one of this turn": lệnh nhập đã nằm trong lịch sử server trả về thì không tự mở, lệnh
    nhập của lượt này thì mở; "a file read into a new canvas while the person has the keyboard
    inside the dock": dock nói bàn phím đang ở trong nó thì canvas vừa nhập không tự mở, bàn phím
    rời đi rồi cũng không, lệnh nhập kế tiếp thì mở, còn nhập vào canvas có nêu thì không hỏi bàn
    phím ở đâu; "a file still being read into a new canvas when the screen was drawn, as when the
    person comes back to the chat mid-turn": lệnh nhập còn chạy hay còn chờ duyệt lúc màn hình được
    vẽ thì xong là mở `{ quiet: true }`, trừ khi lịch sử server trả về có lệnh ấy, lệnh kết thúc
    hỏng hay bị từ chối, hoặc lúc ấy bàn phím đang trong dock; lệnh nhập đã xong lúc màn hình được
    vẽ thì không tự mở); `web/src/components/tool-call-card-canvas.test.tsx` ("keeps the plain
    card for a canvas written out to a file, which shows the canvas and the file it names": lệnh
    xuất giữ thẻ thường khi chờ duyệt, đang chạy và đã xong, nên người duyệt thấy `id` và `path`; bốn
    lệnh ghi, kể cả nhập, thành thẻ canvas); `web/src/components/canvas/canvas-history.test.tsx`
    ("calls a version read from the canvas's file by that, not by the word the server keeps for
    it": ghi chú `import` hiện là "Nhập từ tệp"; "shows a note that only opens with the word the
    server keeps for a re-import as it is written": ghi chú `imported by hand` hiện nguyên văn);
    `web/src/components/canvas/canvas-panel.test.tsx`
    nhóm "where the canvas came from" (dòng nguồn đứng đầu thân panel, trên chữ của canvas, và vẫn
    ở đó khi mở lịch sử; "stays above what the panel says of the canvas": dòng nguồn, rồi chỗ nói
    tin của lần nhập lại (rỗng), rồi mới tới lời báo canvas đã xoá, chứ lời đó không chen lên trên; "saves the typing through the dock before the file
    is read, and asks for nothing when the dock could not": nút gọi đúng `flush` của dock một lần,
    dock trả null thì không có `POST` nào; canvas tạo ở đây thì không có dòng nguồn và không có nút
    nhập lại)
  - Playwright: `canvas-import.spec.ts` ở 1440×900 ("saves the typing first, then reads the file
    again on the version that save made": request `PUT` đi trước `POST …/reimport` và `POST` mang
    `base_version` của `PUT` đó, chữ người gõ còn lại là phiên bản ngay dưới bản nhập, và nút "Nhập
    lại" nằm sát cuối dòng dù đường dẫn ngắn, lời báo đúng chữ "Đã nhập lại thành v3. Bản trước ở
    Lịch sử."; "says the file holds what the canvas does, and writes nothing": đúng chữ "Tệp nguồn
    không đổi."; "says its news in a place that was in the panel before, which takes no room while
    it has none": phần tử `role="status"` đã gắn trong trang và rỗng trước lần bấm, cao 0 px, chữ
    của canvas bắt đầu đúng một khoảng `row-gap` dưới dòng nguồn như khi không có phần tử đó, và
    lời báo hiện ra trong chính phần tử ấy (so cùng một node); "keeps the keyboard on the button
    while the file is read, and takes no second press": trong Chromium thật, nhấn Enter khi nút
    đang giữ focus và request bị giữ lại thì nút ghi "Đang nhập…", `aria-disabled="true"`, thuộc
    tính `disabled` là false, focus vẫn ở nút, `opacity` 0.45 và con trỏ `not-allowed`; Enter, phím
    cách và một cú bấm chuột nữa không thành request thứ hai; thả request thì nút trở lại "Nhập
    lại", vẫn giữ focus; "gives nothing under the pointer or under a press while the file is
    read": trong lúc nút bị giữ, đưa chuột lên rồi nhấn giữ chuột thì màu nền, màu chữ và
    `transform` của nút (đọc sau khi mọi transition của nút chạy xong) vẫn y như lúc chưa có
    chuột, nền trong suốt và không co lại; nhả chuột không thành request thứ hai; thả request
    thì nút sáng lên dưới con trỏ như mọi nút `ghost`; "gives up a read that never answers, says the server did not, and offers
    the button again": `AbortSignal.timeout(30 000)` của trang được rút ngắn bằng `addInitScript`,
    request không bao giờ được trả lời thì trình duyệt huỷ đúng request `POST …/reimport`, lời báo
    là "Không nhập lại được: máy chủ không phản hồi", nút trở lại và chữ của canvas còn nguyên;
    "links the page a canvas was taken from,
    named by its host, in a tab that cannot reach back": tìm link bằng đúng tên truy cập "Mở nguồn
    (tin-tuc.example.com) (mở trong tab mới)", chữ trên dòng không có đoạn sau, `title` là cả địa
    chỉ) và ở 390×844 cảm ứng ("keeps the name of
    the file in view and gives the folder up, with a button a finger can hit": đường dẫn dài thì
    thư mục bị cắt còn tên tệp nguyên tới chữ cuối và nút "Nhập lại" nằm trọn trong màn, nút cao ít nhất 40 px, không
    phần nào của canvas cuộn ngang, kể cả sau khi lời báo "Đã nhập lại thành v2. Bản trước ở Lịch
    sử." hiện ra, nhãn, tên tệp và nút
    nằm trên một hàng có chung đường giữa và có khoảng hở giữa các phần; "shows the link to a
    page as a control a finger can hit, inside the width": link "Mở nguồn" cao ít nhất 40 px và chữ
    của nó nằm giữa chiều cao đó; "cuts a name too long for the width with an ellipsis, and nothing
    runs past the row": tên tệp rộng hơn màn thì thư mục nhường hết chỗ (rộng 0), tên tệp chiếm cả
    phần đường dẫn, bị cắt bằng `text-overflow: ellipsis` chứ không chạy quá mép phần đó, cả tên
    vẫn ở `title`, nút "Nhập lại" nằm trọn trong màn và `scrollWidth` của trang không quá
    `innerWidth`; "wraps the name of a host too long for the width, and nothing
    scrolls sideways": host dài không có gạch ngang thì xuống dòng trong bề ngang, link vẫn nằm trọn
    trong màn); bản
    giả của route nằm ở `web/src/test/fake-canvas-import.ts`, dùng chung cho vitest và Playwright
- **Canvas trên web: thư viện ở màn Quản lý liệt kê mọi canvas, tìm theo tên, nói ai tạo, từ đâu tới
  và mọi phiên bản nặng bao nhiêu, và xoá được sau khi hỏi lại**
  - vitest, đường dẫn và màn: `web/src/hooks/use-route.test.ts` ("reads the canvas library, and the
    canvas a page is opened on, out of a manage link": `#/manage/canvas` và `#/manage/canvas/<id>` đi
    về qua `parseRoute`/`routeHash`, mục viết khác đi thì về Hoạt động);
    `web/src/screens/manage-screen.test.tsx` ("lists the canvases under the crew, after the memory, and
    opens their library": mục Canvas đứng cuối nhóm Đội, sau Trí nhớ; "names the agent that made a
    canvas as the rest of the screen names it": thư viện gọi agent bằng tên mà màn Quản lý đang dùng;
    "reads the canvases again when the stream comes back": màn Quản lý báo cho thư viện biết stream
    vừa nối lại)
  - vitest, client: `web/src/api/artifact-client.test.ts` ("deletes a canvas under an encoded id, and
    reads nothing from the server's empty answer": `DELETE /api/artifacts/<id đã mã hoá>`, 204 không
    có thân)
  - vitest, hook: `web/src/hooks/use-canvas-library.test.ts` (đọc mọi canvas bất kể hội thoại, với
    `limit=200` và không `conversation_id`; 201 canvas thì hiện 200 và số đếm vẫn là 201; danh sách và
    dung lượng là hai lần đọc gửi cùng lúc, cái nào về trước hiện trước; không đọc được dung lượng thì
    vẫn có danh sách; lần đọc đầu hỏng thì báo và đọc lại khi thử lại, lần đọc sau hỏng thì giữ danh
    sách cũ cùng chữ đã tìm; tìm theo tên chờ 250 ms sau phím cuối (249 ms thì chưa hỏi, con số viết
    thẳng trong test) và gửi tên thành tham số `q` riêng;
    ô chỉ khác dấu cách thì không hỏi lại; câu trả lời hay lỗi về sau lần hỏi mới hơn thì bỏ; một loạt
    thay đổi gom thành một lần đọc sau nửa giây; stream nối lại và tab hiện lại thì đọc lại với chữ
    đang tìm; rời thư viện thì thôi đọc); `web/src/hooks/use-canvas-library-delete.test.ts` (canvas
    rời danh sách và tổng khi server trả lời, không sớm hơn; 404 cũng là đã xoá; 500 hay mất mạng thì
    giữ canvas và ghi nhận nó bị từ chối cho tới lần thử sau; hai canvas cùng bị từ chối thì cả hai
    được ghi nhận, thử lại một canvas chỉ gỡ ghi nhận của chính nó; canvas chưa đọc được cỡ thì tổng
    giữ nguyên; nơi khác đang hiện canvas ấy được báo; lời đáp nói canvas đã hết hay chưa: không khi
    server giữ nó, có khi server xoá hay đã không còn nó)
  - vitest, thành phần: `web/src/components/canvas/canvas-library.test.tsx` (mỗi dòng nói loại, phiên
    bản, ai tạo, lúc nào và cỡ mọi phiên bản; sáu loại, canvas mã kèm ngôn ngữ, loại lạ in nguyên;
    ngôn ngữ chỉ nói ở canvas mã dù server giữ ngôn ngữ cho loại nào cũng được; thời điểm là lần ghi
    cuối, không phải lúc tạo; người là "bạn", agent là tên của nó kể cả agent có mã `user`, ký tự ẩn
    trong tên agent được viết ra; tiêu đề là chữ thuần, ký tự ẩn được
    viết ra, thẻ HTML không thành phần tử; nguồn tệp là `<agent>/<đường dẫn>`, nguồn web là "agent ghi
    nguồn: <host>", không có link nào; thiếu cỡ thì không có dòng cỡ và không có "NaN", cỡ 0 là "0 B";
    dòng tổng "<n> canvas · <đã dùng> / <trần>" đếm mọi canvas dù lần tìm chỉ ra ít hơn; ô tìm dài tối
    đa 200 ký tự; bốn trạng thái: đang tải,
    lỗi kèm "Thử lại", trống, không khớp tên; "Hiện 200 canvas mới nhất…" khi còn canvas cũ hơn và
    không đang tìm; xoá hỏi `window.confirm` với đúng tiêu đề đang hiện, từ chối thì không gọi server,
    server không xoá thì câu báo nằm dưới đúng dòng đó; nhóm "once a canvas is deleted from the
    library": bàn phím sang tên của dòng kế sau, sang dòng trước khi dòng bị xoá là dòng cuối, vào ô
    tìm khi không còn dòng nào, và dòng `role="status"` nói "Đã xoá canvas <tên>" với tên đúng như
    dòng đã hiện, kể cả ký tự ẩn và canvas không tên; 404 cũng vậy; server không xoá thì bàn phím ở
    nguyên nút xoá và dòng ấy không nói gì; lần xoá kế tiếp vừa bấm thì thôi nói về canvas trước;
    người đã đưa bàn phím đi chỗ khác trong lúc chờ server thì bàn phím ở lại chỗ đó);
    `web/src/components/canvas/canvas-section.test.tsx` (mục Canvas chỉ hỏi `/artifacts?limit=200`,
    không hỏi canvas của hội thoại nào; lần lưu để lại phía sau mà hỏng thì câu "lưu hỏng, nháp còn
    giữ" hiện phía trên thư viện và cất đi được; câu "tin đi kèm bản đã lưu gần nhất" không hiện ở
    đây; stream nối lại thì thư viện đọc lại)
  - Playwright: `web/e2e/canvas-library.spec.ts` (ở 1440 px và 390 px: ba canvas với người tạo, nguồn,
    cỡ và dòng tổng, không link nào, tiêu đề và đường dẫn dài không làm trang, mục, thư viện hay dòng
    nào tràn ngang; tìm không dấu "ke hoach" ra đúng một canvas, tên lạ ra câu không khớp, xoá ô thì
    đủ lại; bấm xoá rồi từ chối thì canvas còn, đồng ý thì dòng mất, server giả hết canvas ấy và tổng
    giảm; trong Chromium thật, dòng nói "Đã xoá canvas…" không chiếm chỗ nào khi còn trống, và sau khi
    xoá dòng cuối thì bàn phím nằm ở tên của dòng trước, dòng ấy hiện đúng tên canvas vừa xoá, cùng
    cỡ chữ và không lề riêng như dòng tổng; "the canvas library is reached from the crew's part of
    the manage screen");
    `web/e2e/touch-targets-phone.spec.ts` (trang "the canvas library": nút xoá của một dòng đủ 40 px);
    bản giả của `GET /api/artifacts/usage` nằm ở `web/src/test/fake-canvas-usage.ts`
    (`web/src/test/fake-canvas.test.ts`, "counts what every version of each canvas holds, on a path
    no canvas's id answers")
- **Canvas trên web: mỗi canvas có trang riêng ở `#/manage/canvas/<id>`, mở từ tên của nó trong thư
  viện hoặc nút "Mở riêng" của panel; rời trang không mất chữ; trang nói canvas dùng trong những hội
  thoại nào**
  - vitest, mục Canvas: `web/src/components/canvas/canvas-section.test.tsx` ("shows the library for %j,
    which is no canvas's id, and asks the server nothing about it": `a1`, chữ in hoa, thừa hay thiếu
    một ký tự, `..%2F..%2Fsettings`, id kèm `?x=1` và chuỗi rỗng đều ra thư viện, và chỉ hai lần đọc
    của thư viện được gửi; "is shown on its page instead of the
    library, with the way back above it"; "is read anew when the address names another, and nothing
    typed in the first is lost"; "a save that fails after its page was left": câu "lưu hỏng, nháp còn
    giữ" hiện phía trên thư viện vừa quay về, hoặc phía trên canvas vừa chuyển sang, và ở lại qua lần
    chuyển kế; "is not said of a canvas deleted from the library before the save got there": xoá
    canvas ngay sau khi rời nó thì không có câu báo nào và nháp đi theo; "opens the canvas whose name
    is clicked in the library"; "shows what was written to it while the stream was down, once the
    stream is back": bản ghi lúc mất stream không ai báo, stream nối lại thì trang đọc lại và hiện
    chữ mới; "names a conversation it came to be used in while the stream was down, once the stream
    is back": hội thoại nhận canvas lúc mất stream không ai báo, stream nối lại thì dòng "Dùng
    trong…" có tên nó); `web/src/components/canvas/canvas-section-crash.test.tsx` (trang vỡ
    thì nút "← Canvas" vẫn đứng phía trên chỗ vỡ vì nó nằm ngoài `ErrorBoundary`; địa chỉ đổi sang
    canvas khác hoặc về thư viện thì chỗ vỡ bị bỏ lại)
  - vitest, trang: `web/src/components/canvas/canvas-page.test.tsx` (trang dùng đúng panel mà hội
    thoại dùng; không có thanh hỏi agent, không có "Mở riêng", không ghi "canvas đang mở" cho hội
    thoại nào; "opens a canvas an agent wrote to be read, under its name and not a box to name it in":
    trang mở canvas như một canvas có sẵn, không như canvas vừa tạo; "opens the next canvas the way
    that one opens, not the way the one before it was left": đổi id thì chế độ xem hay sửa tính lại
    từ đầu; "goes back to the library at once with words unsaved, and their save goes on behind";
    nút đóng và nút về danh sách của panel đều là đường về; canvas không có hay bị xoá lúc đang mở thì
    panel nói "đã bị xoá" và đường về còn; "Nhập lại" gửi đi không kèm hội thoại nào; dòng "Dùng trong
    <n> hội thoại" gọi từng hội thoại bằng tiêu đề, hội thoại không tên hay tab chưa liệt kê thì bằng
    sáu ký tự đầu của id, không hội thoại nào hay đọc hỏng thì không có dòng; trang không mở và không
    đóng gì trong dock nó mượn; đổi canvas thì không còn gì của canvas trước trong lúc đọc canvas
    sau); `web/src/hooks/use-canvas-conversations.test.ts` (đọc một lần theo thứ tự server trả; đọc
    lại khi stream báo đúng canvas ấy đổi, không đọc vì canvas khác; lần đọc sau hỏng thì thôi nêu
    tên; canvas bị xoá thì hết tên mà không hỏi gì và câu trả lời còn bay bị bỏ; câu trả lời cũ về sau
    câu mới thì bỏ; đổi canvas thì câu trả lời về canvas trước bị bỏ; rời trang thì thôi hỏi; "when
    the stream comes back after a drop": stream nối lại thì đọc lại, nên lần đọc hỏng lúc server vắng
    được bù và hội thoại nhận canvas lúc mất stream có tên; lần nối đầu tiên của stream không đọc
    thêm lần nào; canvas đã bị xoá thì stream nối lại không hỏi gì; canvas trước bị xoá không chặn
    việc đọc lại canvas đang được gọi tên)
  - vitest, panel và dock: `web/src/components/canvas/canvas-panel.test.tsx` ("the way from the panel
    to the canvas's own page": `window.open(<địa chỉ>, "_blank", "noopener,noreferrer")` và không lưu
    gì trên đường; còn chữ chưa lưu thì nút bị giữ lại bằng `aria-disabled`, bấm không mở gì, và nhận
    lại khi một phiên bản giữ chúng; "stays within the keyboard's reach while words are unsaved, and
    says why it cannot be taken yet": nút không `disabled` nên vẫn nhận bàn phím, lý do "Lưu trước khi
    mở riêng" nằm ở `title` và ở dòng mà `aria-describedby` trỏ tới, dòng ấy mang lớp `sr-only` nên
    chỉ được đọc lên chứ không vẽ ra, lưu xong thì lý do không còn và bàn phím vẫn ở nút; đứng cạnh
    nút "Mở trang" của canvas trang, mỗi nút một tên; không có khi
    panel không được cho địa chỉ, khi canvas mới biết tên chưa đọc xong, và khi canvas bị xoá);
    `web/src/components/canvas/canvas-dock-view.test.tsx` ("the open canvas's own page": ở cột lẫn lớp
    phủ, địa chỉ là `#/manage/canvas/<id>` của canvas đang mở);
    `web/src/components/canvas/canvas-library.test.tsx` ("opens the canvas whose name is clicked, one
    with no name too, and deletes nothing by it")
  - vitest, cả app: `web/src/app-canvas-page.test.tsx` (link tới trang mở đúng trang, "← Canvas" đưa
    địa chỉ về `#/manage/canvas`, tên trong thư viện đưa địa chỉ về lại `#/manage/canvas/<id>`; bấm
    tên hội thoại thì sang `#/chat/<id>`; chọn mục khác rồi quay lại mục Canvas thì là thư viện, id đã
    rời địa chỉ; link có id không hợp lệ thì chỉ `/artifacts/usage` được hỏi dưới `/artifacts/`;
    "shows the library, not a blank screen, for a link whose canvas is written %j": link cụt giữa một
    ký tự mã hoá (`%`, `%E0%A4%A`, `%zz`) ra thư viện thay vì màn trắng, và cũng chỉ `/artifacts/usage`
    được hỏi; "Mở riêng" từ dock của hội thoại gọi `window.open` với đúng địa chỉ trang)
  - vitest, đường dẫn: `web/src/hooks/use-route.test.ts` ("opens the section alone when what it is
    opened on is written %j, an escape that cannot be read": `%`, `%E0%A4%A`, `%zz`, `ghi%2` ở chỗ
    của id thì chỉ còn mục, phần cần hiện và `?job=` đi theo nó; "keeps what the section is opened on
    and drops the part to show, when only that part cannot be read"; "reads a broken escape anywhere
    else in the address as the letters it is written in": ở tên mục, ở id hội thoại và trong `?job=`
    không có gì phải giải mã nên không gì ném lỗi; "starts on the section, and follows the address
    bar to one, when the address holds an escape that cannot be read": `useRoute` lúc khởi động và
    lúc `hashchange` đều ra mục chứ không ném lỗi)
  - Playwright: `web/e2e/canvas-page.spec.ts` (ở 1440×900 và 390×844: bấm tên trong thư viện thì địa
    chỉ có id, trang chạm đúng chân mục mà mục không cuộn dọc, panel là cả trang trừ dòng "Dùng
    trong…" và cao hơn nửa màn, ô soạn chiếm phần panel mà đầu panel để lại, không chỗ nào tràn
    ngang, tải lại vẫn ở trang đó; rời trang ngay khi chữ chưa lưu thì lần lưu vẫn tới server và không
    có câu báo; lần lưu bị từ chối thì câu báo hiện phía trên thư viện, mở lại canvas là thấy nháp;
    dòng hội thoại đúng thứ tự và mở đúng cuộc; tiêu đề dài không ngắt được vẫn nằm trong màn; canvas
    không còn thì nói đã xoá và "← Canvas" vẫn về thư viện; địa chỉ `..%2F..%2Fsettings` ra thư viện
    và không địa chỉ nào dưới `/api/artifacts/` ngoài `usage` được hỏi; "an address cut short in the
    middle of an escape shows the library instead of a blank screen": `#/manage/canvas/%E0%A4%A` ra
    thư viện và trang không ném lỗi nào; "opens on its own page in a
    new tab cut off from this one, once what was typed is saved": nút bị giữ lại cho tới khi lần lưu
    xong mà vẫn nhận bàn phím: `aria-disabled`, không `disabled`, lý do ở `title` và ở mô tả, mờ như
    nút tắt, Enter, Space và cú bấm chuột đều không gọi `window.open` lần nào (trang ghi lại từng
    lần gọi, vì tab mới chỉ hiện trong danh sách trang của trình duyệt sau một lúc); lưu xong thì bàn
    phím vẫn ở nút và lý do không còn, cú bấm lúc này là lần gọi duy nhất và đúng địa chỉ; tab mới có
    `window.opener` là `null` và `document.referrer` rỗng, tab cũ vẫn ở cuộc trò chuyện; "gives
    nothing under the pointer or under a press while words are unsaved": lúc bị giữ lại, nút không
    đổi nền, màu chữ hay `transform` khi rê chuột vào và khi nhấn giữ, cú nhấn không mở gì; lưu xong
    mà chuột còn trên nút thì nút sáng lên như mọi nút cùng loại);
    `web/e2e/touch-targets-phone.spec.ts` ("every control on a canvas's own page is big enough for a
    finger, a conversation named in one letter too"; "the name that opens a canvas from the library is
    big enough for a finger, one letter long too"); nút "Mở riêng" trong dock ở 390 px và 1000 px nằm
    trong phép kiểm sẵn có của `web/e2e/canvas.spec.ts` (`smallTargets(page, ".canvas-dock")`, không
    tràn ngang)
- **Canvas trên web: thẻ giao việc nêu từng canvas agent con viết kèm nút "Mở"; canvas đầu tiên tự mở
  cạnh thread ở màn rộng mà không lấy bàn phím; canvas đã xoá thì nói đã xoá và không có nút**
  - vitest, dòng canvas: `web/src/components/canvas/delegate-canvases.test.tsx` (đúng thứ tự của kết
    quả, mỗi dòng có tên, `v<n>` và nút "Mở" gọi đúng id; là một danh sách có tên; tên lấy từ thread
    trước, rồi từ dòng kết quả, rồi "Canvas"; ký tự ẩn được viết ra, thẻ HTML không thành phần tử; mỗi
    canvas được hỏi `verify` một lần, vẽ lại không hỏi lại; canvas đã xoá chỉ còn tên và "Canvas đã bị
    xoá", không phiên bản, không nút; kết quả nêu một canvas hai lần thì vẽ cả hai dòng, và khi kết
    quả được đọc lại với một dòng chen lên đầu thì các dòng vẫn đúng theo kết quả, không dòng nào
    thừa; không canvas nào thì không vẽ gì và không hỏi gì)
  - vitest, thẻ: `web/src/components/delegate-cards.test.tsx` ("the canvases a handed-off task wrote,
    on its card": danh sách đứng dưới dòng trạng thái và chi phí, trên nút xem kết quả; thread không
    đưa đường mở canvas thì không có dòng nào; khối canvas rỗng là ca đối chứng: không dòng nào và
    không hỏi server; câu trả lời của agent con mở đầu bằng một dòng giống thẻ canvas thì không thành
    dòng nào; việc hết giờ vẫn nêu canvas đã viết kèm lý do; việc đang chạy thì chưa có; kết quả mở ra
    chỉ còn lời của agent con)
  - vitest, tự mở: `web/src/hooks/use-canvas-auto-open.test.ts` ("opening the canvas a handed-off task
    wrote": mở lặng lẽ khi lệnh giao việc xong, chỉ canvas đầu tiên, một lần dù vẽ lại, bất kể
    `outcome` là gì miễn lệnh gọi xong; hai việc giao song song thì việc xong sau là canvas còn mở; "a
    handed-off task that opens nothing by itself": không viết canvas nào; hết giờ, hỏng, bị từ chối
    hay bị dừng; lệnh đã có trong lịch sử hay đã xong lúc màn hình được vẽ; màn hẹp, kể cả khi sau đó
    rộng ra;
    người đang gõ trong canvas, kể cả khi sau đó thôi gõ; dòng thẻ chỉ nằm dưới dòng trống, khối lẫn
    dòng lạ, khối không có dòng trống, kết quả không có dòng `outcome`, output rỗng hay rác; tool
    canvas có output trông như kết quả giao việc)
  - vitest, cả app: `web/src/app-canvas-delegate.test.tsx` (ở 1440 px: hai dòng trên thẻ, canvas đầu
    mở cạnh thread, bàn phím ở lại ô soạn, không lần ghi "canvas đang mở" nào; tên trên dòng là tên
    server đang giữ, mỗi canvas được hỏi đúng một lần; tin kế tiếp mang canvas vừa tự mở; nút "Mở" của
    dòng khác thay canvas đang mở và tin kế tiếp mang canvas ấy; thay canvas người đang mở khi bàn
    phím đã về ô soạn tin, không thay canvas người đang đặt con trỏ, không thay trang HTML mà khung
    của nó đang giữ bàn phím — dòng của canvas mới vẫn mở nó khi bấm —, không thay canvas mà bàn
    phím đang ở một nút của nó; canvas bị xoá lúc đang hiện thì dòng thôi mời mở;
    khối rỗng và câu trả lời giống thẻ thì không dòng, không mở, không hỏi server; việc hết giờ có
    dòng mà không tự mở; ở 1000 px có dòng, không tự mở, bấm thì thành lớp phủ; lượt đã lưu từ trước
    có dòng, chỉ mở khi bấm và khi đó bàn phím vào dock; canvas server không còn thì "Canvas đã bị
    xoá")
  - Playwright: `web/e2e/canvas-delegate.spec.ts` (ở 1440×900 và 390×844: hai dòng đúng tên và phiên
    bản, nằm dưới dòng chi phí, xếp chồng, nút ở cuối dòng, không chỗ nào tràn ngang; khối rỗng và câu
    trả lời giống thẻ thì không dòng nào và không canvas nào mở; canvas server không có thì "Canvas đã
    bị xoá" và không nút; tiêu đề dài không ngắt được thì chính tiêu đề xuống dòng, còn phiên bản, nút
    và chữ "đã bị xoá" giữ nguyên một dòng; ở màn rộng canvas đầu mở cạnh thread, ô soạn vẫn giữ focus
    và tin kế tiếp mang canvas ấy, nút "Mở" của dòng thứ hai thay canvas đang hiện; ở điện thoại không
    canvas nào tự mở và chạm "Mở" thì canvas phủ lên thread); `web/e2e/touch-targets-phone.spec.ts`
    ("the Open button of each canvas a handed-off task wrote is big enough for a finger, beside a name
    one letter long too")
- **Canvas trên web: dòng `FILE: artifact:<id>` hoặc `MEDIA: artifact:<id>` của một câu trả lời hiện
  thành chip tên canvas kèm nút "Mở", không thành link tải tệp; dòng ghi sai mã thì hiện lại đúng
  như đã viết, không chip, không câu "Canvas đã bị xoá" và không hỏi server**
  - vitest, đọc đường dẫn: `web/src/lib/artifact-ref.test.ts` (cùng bảng với `artifact_ref` của
    Python: mã 12 ký tự hex thường là canvas, khoảng trắng quanh mã được bỏ; mở bằng `artifact:` mà
    phần sau không phải đúng một mã thì là `""`; còn lại là `null`, kể cả `Artifact:` viết hoa,
    `artifact:` đứng giữa đường dẫn hay sau một dấu cách)
  - pytest: `tests/test_channels_telegram.py::test_the_web_tells_a_line_that_sends_a_canvas_by_the_prefix_the_channel_reads`
    (tiền tố `ARTIFACT_REF` trong `web/src/lib/artifact-ref.ts` bằng đúng hằng của Python)
  - vitest, tách dòng: `web/src/lib/reply-blocks.test.ts` (`splitMedia`, nay ở
    `web/src/lib/reply-blocks.ts`: dòng `MEDIA:` và `FILE:` tách khỏi lời, giữ đúng thứ tự, câu chỉ
    nhắc tới tiền tố và tiền tố trần vẫn là lời; dòng gửi canvas dưới cả hai tiền tố thành khối
    `canvas` mang mã và nguyên dòng đã viết; dòng tệp workspace không đổi; mã sai thành khối
    `canvas` có mã rỗng, kể cả mã đúng có đuôi `.md` hay dấu chấm theo sau, và khối vẫn giữ nguyên
    dòng đã viết)
  - vitest, trong thread: `web/src/components/message-thread.test.tsx` ("a line of a reply that
    sends a canvas": thread có đường mở canvas thì câu trả lời có chip, không link tệp, không chữ
    `FILE:`, lời quanh dòng còn nguyên và nút gọi đúng mã; dòng ghi mã kèm đuôi `.md` là một đoạn
    chữ đúng như đã viết, đứng cạnh chip của dòng ghi đúng, không câu "đã bị xoá" và chỉ mã đúng
    được hỏi; thread không có đường mở canvas thì dòng là một đoạn chữ)
  - vitest, chip: `web/src/components/canvas/canvas-ref-chip.test.tsx` (tên thread đang giữ, biểu
    tượng, đúng một nút và nút gọi đúng mã; không in lại dòng hay mã; chưa biết tên thì là "Canvas"
    và vẫn mở được; ký tự ẩn được viết ra; `verify` được gọi một lần, vẽ lại không gọi lại, đổi mã
    thì gọi lại, và được đưa một `verify` khác thì hỏi lại qua `verify` ấy; canvas đã xoá còn tên
    và "Canvas đã bị xoá", không nút; mã rỗng thì là đúng dòng đã viết trong một đoạn chữ, không
    chip, không nút, không hỏi `verify`, `titleOf` hay `isGone`; không có đường mở canvas thì cũng
    là đúng dòng đã viết, trong một đoạn chữ)
  - vitest, cả app: `web/src/app-canvas-ref-chip.test.tsx` (câu trả lời đã lưu: chip mang tên canvas
    và bấm thì canvas mở cạnh thread; bấm lúc khung "đang viết" của một canvas khác đang hiện thì
    khung ấy rời đi, panel hiện canvas của chip và thẻ "đang viết" vẫn còn; sau lần bấm ấy khung
    không tự nổi lại trong cả lượt, kể cả khi model viết lại câu trả lời và bản nháp mới đã đủ dài
    để tự hiện, còn nút trên thẻ "đang viết" vẫn gọi được khung ra với bản nháp mới; canvas không
    gắn với hội thoại lấy tên server đang giữ sau đúng một lần hỏi; canvas server không còn thì
    "Canvas đã bị xoá" cạnh một chip còn mở được; ba dòng ghi sai mã, `FILE: artifact:xyz`, mã của
    một canvas đang có kèm đuôi `.md` và mã ấy kèm dấu chấm cuối, mỗi dòng là một đoạn chữ đúng như
    đã viết, không chip, không câu "đã bị xoá", không nút, không link tệp, không ảnh và không gây
    lời hỏi `/artifacts/` nào)
  - Playwright: `web/e2e/canvas-thread.spec.ts` (ở 1440 px chip nằm trong câu trả lời, tên đứng
    trước nút, chữ của nút trên một dòng, không link tệp, bấm thì canvas mở cạnh thread; cũng ở
    1440 px chip của một canvas tên ngắn là một khung nhỏ, hẹp hơn nửa bề ngang câu trả lời, nên bỏ
    luật `.bubble .canvas-ref` thì chip thành một thanh ngang suốt câu trả lời và test đỏ; ở 390 px
    `smallTargets(page, ".canvas-ref")` rỗng, nút cao ít nhất 40 px và chạm thì canvas phủ lên
    thread; tiêu đề một từ rất dài thì chính tiêu đề xuống dòng trong câu trả lời, nút vẫn nguyên
    một dòng và không chỗ nào tràn ngang)
- **Mã agent khớp cả chuỗi: chữ thường, số và gạch ngang, không cả xuống dòng ở cuối**
  - pytest: `tests/test_api_agents_edit.py::test_an_id_that_is_not_a_safe_folder_name_is_refused`
    (`../escape` và `coder` có xuống dòng ở cuối đều bị từ chối, không thư mục nào được tạo);
    `tests/test_artifact_guards.py`
    ("test_an_author_that_is_neither_the_person_nor_an_agent_is_refused",
    "test_a_creator_that_does_not_match_its_author_is_refused": `agent:Coach` và mã có xuống
    dòng ở cuối không ghi được canvas); mẫu ở `my_agent_crew/agent_ids.py`
- **Thread bám theo tin mới nhất khi câu trả lời đổ về một lượt; chỉ cuộn lên mới nhả**
  - vitest: `hooks/use-auto-scroll.test.ts` ("stays pinned when its own scroll is reported after the
    content grew again, and lets go once the reader moves up": trình duyệt báo cú cuộn của chính hook
    chậm một khung hình, lúc đó nội dung đã dài thêm nên khoảng cách tới đáy đọc ra xa dù không ai
    cuộn, thread vẫn bám và chỉ nhả khi vị trí đi lên; "stays pinned when the report of its own jump
    finds the element exactly where it left it"; "counts the jump its size observer makes as where
    the element was left": bộ quan sát kích thước cũng ghi lại chỗ nó vừa nhảy tới; "does not take
    hold again on a scroll down that stops short of the bottom"; "lets go when the reader scrolls up
    straight after a jump to the newest"). Lỗi thật thấy trên trình duyệt (390 px và 1000 px, model
    echo): sau vài tin thread ngừng bám giữa chừng, nút "Tin mới nhất" hiện lên và câu trả lời nằm
    ngoài màn hình
  - vitest: `components/message-thread.test.tsx` ("marks the thread as following while it is at its
    newest line, so the browser's anchoring stays out of it", "drops the mark once the reader scrolls
    up, and offers the way back to the newest line", "brings the mark back when the reader jumps to
    the newest line": thread mang `data-following` khi đang ở dòng mới nhất, mất khi người đọc cuộn
    lên và có nút "Tin mới nhất" để quay về)
  - Playwright: `thread-follow.spec.ts` (390 px, hội thoại tám lượt với câu trả lời nhiều dòng, câu
    trả lời của lượt mới được giữ lại tới khi test thả ra; "the browser's own anchoring is off while
    the thread follows its newest line and on once it is read": `overflow-anchor` tính ra là `none`
    khi thread bám, `auto` khi người đọc cuộn lên và `none` lại sau "Tin mới nhất", đây là test ghim
    nguyên nhân; "a reader who scrolled back keeps their place when the buttons above leave": đầu câu
    trả lời đang đọc không xê dịch khi nút rẽ nhánh phía trên biến mất, chặn việc tắt neo cuộn cho
    mọi thread; "a turn that starts with the thread on its newest line leaves it there": lượt bắt đầu
    rồi câu trả lời về xong, thread vẫn ở dòng mới nhất và không có "Tin mới nhất")
  - Nguyên nhân thứ hai của cùng triệu chứng, thấy khi kiểm tay ở 390 px với câu hỏi về một đoạn
    canvas: lúc lượt bắt đầu các nút rẽ nhánh phía trên biến mất (khoảng 44 px mỗi tin của người) và
    Chrome hạ vị trí cuộn theo (scroll anchoring) để giữ yên dòng đang xem, trong khi khoảng 93 px
    nội dung mới (tin của người và khối đang nghĩ) hiện ra bên dưới: chỗ còn lại cách đáy
    93 − 44 × (số hàng nút từ điểm neo trở xuống) px, tức 49 px khi còn một hàng, vượt ngưỡng 48 px.
    Nếu sự kiện cuộn đến trước bộ quan sát kích thước, hook thấy cách đáy hơn 48 px và coi là người
    đọc cuộn lên. Thứ tự hai việc đó khác nhau giữa các đường gửi (đã đo: gửi từ ô nhắn thì bộ quan
    sát bám trước, gửi từ thanh hỏi về canvas thì sự kiện cuộn đến trước), nên test "a turn that
    starts…" đạt cả trước khi sửa; chỉ test ghim công tắc `overflow-anchor` đỏ trước khi sửa
- **Địa chỉ mở web (`web_url`): đọc từ `config.yaml` hoặc `MY_AGENT_WEB_URL`; giá trị không phải một
  địa chỉ http trơn thì dừng lúc nạp cấu hình**
  - pytest: `tests/test_config.py::test_the_web_address_comes_from_yaml_or_env_and_defaults_to_none`
    (env thắng tệp, `/` cuối được bỏ, chưa đặt là rỗng, khoá có trong `YAML_KEYS`);
    `tests/test_config.py::test_no_web_address_reads_as_empty`;
    `tests/test_config.py::test_a_web_address_keeps_its_scheme_host_port_and_path_without_the_last_slash`
    (`127.0.0.1`, `localhost`, tên miền có cổng, tên có gạch nối và gạch dưới, IPv6 trong ngoặc
    vuông kể cả dạng bọc IPv4; khoảng trắng ở hai đầu và dấu `?` hay `#` không có gì theo sau
    được bỏ đi cùng dấu `/` cuối);
    `tests/test_config.py::test_a_web_address_that_is_not_a_plain_one_is_refused` (scheme khác
    `http`/`https`, thiếu scheme, thiếu host, có tên đăng nhập, query, fragment, khoảng trắng và ký
    tự ẩn ở path lẫn ở host, ký tự điều khiển đứng đầu mà phép tách địa chỉ sẽ lặng lẽ bỏ, nửa
    cặp surrogate, cổng không đọc được, path có ký tự phải mã hoá, giá trị không phải chuỗi; host
    có `\`, `*`, chữ có dấu, dấu `:` không kèm cổng, ngoặc vuông chứa thứ không phải IPv6 trơn;
    câu lỗi của hàng nào cũng không lặp lại giá trị);
    `tests/test_config.py::test_a_refused_web_address_stops_the_load_and_is_not_repeated` (câu lỗi
    nêu khoá `web_url` và không lặp lại giá trị, vì giá trị có thể mang mật khẩu)
- **Dòng báo một đính kèm không gửi được mà chính nó cũng không gửi được thì chỉ vào log; các đính
  kèm đứng sau vẫn tới chat**
  - pytest (`tests/test_reply_file_line.py`):
    `::test_a_notice_that_cannot_be_sent_does_not_stop_the_next_attachment`
    (`sendMessage` trả 500 trong lúc một tệp và một ảnh không có: `ok.pdf` vẫn tới, `send` không ném,
    mỗi dòng báo hỏng một dòng log mức `warning`);
    `::test_an_upload_telegram_refuses_is_said_and_does_not_stop_the_next` (tệp có thật mà Telegram
    từ chối lúc tải lên: chat nhận một dòng báo, `ok.pdf` vẫn tới); bản giả Telegram
    (`tests/telegram_fake.py`) cho một method trả lỗi bằng `fail`, giữ một lời gọi bằng `hold`, và
    đọc tên tệp, caption, bytes của mỗi lời tải lên vào `uploads`
- **Dòng `FILE: artifact:<id>` hoặc `MEDIA: artifact:<id>` của một câu trả lời gửi canvas đó tới
  chat Telegram dưới dạng tệp, dựng trong bộ nhớ, sau các tệp workspace**
  - pytest (đọc dòng, `tests/test_telegram_canvas_file.py`):
    `::test_a_path_names_a_canvas_only_as_the_prefix_and_a_whole_id`
    (mã 12 ký tự hex thường là canvas; mở bằng `artifact:` mà phần sau không phải đúng một mã thì là
    `""`, không bao giờ được tìm như một tệp; còn lại là đường dẫn tệp);
    `::test_lines_that_misname_a_canvas_get_one_notice_that_repeats_none_of_them` (một dòng báo cho
    mọi dòng ghi sai mã, không lặp lại chữ của model);
    `::test_a_canvas_named_twice_in_one_reply_is_sent_once`;
    `::test_workspace_files_go_first_and_as_before_then_the_canvases`
  - pytest (tệp gửi đi): `::test_a_markdown_canvas_arrives_as_a_document_with_its_secrets_covered`
    (giá trị biến môi trường mang tên khoá và chuỗi dạng `sk-…` được che trong nội dung);
    `::test_a_text_canvas_is_named_so_a_phone_opens_it_as_text` (markdown giữ `.md`, các loại chữ
    khác kết thúc bằng `.txt`); `::test_a_picture_is_named_by_what_its_bytes_are`;
    `::test_a_picture_arrives_as_a_photo_with_its_bytes_as_they_are` (loại canvas quyết định cách
    gửi, không phải tiền tố của dòng); `::test_a_text_canvas_on_a_media_line_is_still_a_document`;
    `::test_the_newest_version_is_sent_and_the_caption_says_which`;
    `::test_the_caption_ends_with_a_link_when_the_web_has_an_address`;
    `::test_a_link_that_would_make_the_caption_too_long_is_left_out` (đúng 1024 ký tự thì còn link,
    1025 thì bỏ cả link);
    `::test_a_secret_in_the_title_reaches_neither_the_caption_nor_the_file_name`;
    `::test_the_caption_is_plain_text_like_every_message`;
    `::test_bytes_are_uploaded_under_a_name_with_a_bounded_wait` (`send_bytes`: không có phần
    `caption` khi rỗng, không `parse_mode`, mỗi lần tải lên chờ tối đa 60 giây)
  - pytest (khi hỏng): `::test_a_picture_refused_as_a_photo_arrives_as_a_document` (`sendPhoto` trả
    400 thì gửi lại một lần bằng `sendDocument`);
    `::test_a_picture_refused_both_ways_is_tried_once_more_and_no_further`;
    `::test_a_photo_that_fails_for_another_reason_is_not_sent_again`;
    `::test_a_document_that_is_refused_is_not_sent_again`;
    `::test_a_canvas_that_cannot_be_sent_does_not_stop_the_next` (lý do chỉ vào log);
    `::test_a_canvas_over_what_a_chat_takes_is_not_uploaded` (đo bằng byte, bằng đúng mức trần thì
    vẫn gửi); `::test_a_canvas_that_is_not_there_is_said_so`;
    `::test_a_canvas_deleted_while_it_is_read_reads_as_one_that_is_not_there` (bị xoá giữa lúc tìm
    thấy và lúc đọc nội dung: cùng câu với canvas không có, không có lời tải lên nào);
    `::test_a_notice_about_a_canvas_that_cannot_be_sent_stops_nothing`;
    `::test_the_log_names_the_canvas_by_id_version_and_size_alone` (log không mang tiêu đề hay nội
    dung)
  - pytest (ai được gửi canvas nào, `tests/test_telegram_canvas_scope.py`):
    `::test_a_canvas_out_of_reach_reads_as_one_that_is_not_there` (cùng một câu với canvas không tồn
    tại, để câu trả lời không dò được mã nào có thật);
    `::test_an_agent_sends_what_it_made_whatever_became_of_the_conversation`;
    `::test_a_linked_canvas_is_sent_for_its_conversation_alone`;
    `::test_what_the_root_of_a_delegation_shares_reaches_its_child`;
    `::test_the_master_sends_a_canvas_of_any_agent_and_any_conversation`;
    `::test_a_canvas_imported_from_a_file_no_reply_could_send_is_not_sent` (canvas nhập từ tệp
    workspace có đuôi không thuộc danh sách `FILE:` cũng không phải một loại canvas, ví dụ `.env`,
    `.pem`, tệp không đuôi);
    `::test_a_canvas_imported_from_a_file_of_a_known_kind_or_a_link_is_sent`;
    `::test_a_picture_is_sent_whatever_its_file_was_called`;
    `::test_reach_is_checked_before_where_a_canvas_came_from`;
    `::test_a_turn_in_the_chat_sends_what_its_conversation_holds_however_it_began` (lượt mở bằng
    một tin nhắn, bằng `/approve` cho lượt đang dừng, hay bằng tin đã chờ trong hàng: câu trả lời
    nào cũng được gửi theo hội thoại của lượt, nên canvas gắn với hội thoại đó tới được chat)
- **Dòng `FILE: artifact:<id>` trong câu trả lời của agent con đi tiếp tới agent cha theo tầm với
  của agent con, không qua đường chép tệp workspace**
  - pytest (`tests/test_delegate_canvas_lines.py`):
    `::test_a_canvas_line_that_is_carried_rides_on_as_it_is`;
    `::test_a_canvas_line_that_is_not_carried_becomes_the_sentence_of_a_lost_file` (dòng ghi sai mã
    được hỏi bằng `""`); `::test_a_line_that_opens_as_a_canvas_is_never_looked_up_as_a_file` (kể cả
    khi workspace của agent con có tệp đúng tên đó);
    `::test_workspace_files_beside_a_canvas_line_are_copied_as_before`;
    `::test_canvas_lines_are_asked_about_when_parent_and_child_share_a_workspace` (chung workspace
    chỉ miễn việc chép tệp, không nói gì về canvas agent con với tới);
    `::test_an_answer_with_nothing_to_carry_comes_back_as_it_was` (không có gì phải đổi thì trả lại
    đúng từng ký tự, kể cả dấu ngắt dòng)
  - pytest (`canvas_carrier`):
    `::test_a_canvas_within_the_childs_reach_is_carried_and_linked_to_the_parent` (canvas của chính
    nó, canvas gắn với hội thoại của nó, canvas gốc chia sẻ; liên kết tạo ra không chia sẻ cho các
    agent con khác);
    `::test_a_canvas_outside_the_childs_reach_is_not_carried_and_links_nothing` (kể cả canvas của
    chính agent cha, canvas agent cha giữ riêng, mã không có canvas, mã rỗng);
    `::test_the_master_as_a_child_carries_every_canvas_that_is_there` (master với tới mọi mã, nhưng
    mã không có canvas vẫn không được mang);
    `::test_with_no_conversation_to_link_a_reached_canvas_is_still_carried`
  - pytest (qua tool `delegate`):
    `::test_a_delegated_canvas_reaches_the_parent_with_the_reach_to_send_it` (trước khi giao việc
    agent cha không với tới canvas, sau đó thì có);
    `::test_a_delegated_line_for_a_canvas_the_child_cannot_reach_is_said_in_words`
  - pytest (đặt lại dòng bị bỏ sót): `::test_a_canvas_line_the_parents_reply_left_out_is_put_back`
    (dòng đã thành câu báo thì không đặt lại)
- **Kênh gửi câu trả lời và đường chuyển câu trả lời của agent con tách dòng bằng cùng một hàm
  (`reply_lines`), nên một dòng đính kèm đứng sau dấu ngắt dòng Unicode không lọt qua bên nào**
  - pytest (`tests/test_delegate_canvas_lines.py`):
    `::test_a_reply_is_cut_into_lines_at_every_line_break_a_string_knows`;
    `::test_a_line_after_any_line_break_is_an_attachment_to_the_channel_and_the_relay` (`U+2028`
    trước dòng `MEDIA:` và dòng `FILE: artifact:`: tệp được chép, canvas được hỏi);
    `::test_the_childs_last_words_are_read_line_by_line_the_same_way`;
    `::test_dropped_lines_are_looked_for_line_by_line_the_same_way`
- **Sau câu trả lời trên Telegram, chat nhận danh sách các canvas lượt đó đã ghi: tiêu đề, phiên
  bản lượt để lại, và đường dẫn mở trên web khi có `web_url`. Danh sách đọc từ kết quả tool của
  chính lượt đó, không đọc từ lời của model, và chỉ nêu canvas agent còn với tới**
  - pytest (`tests/test_telegram_canvas_notice.py`, đọc thẻ):
    `::test_a_tag_reads_back_as_what_it_was_built_from`;
    `::test_a_line_that_does_not_open_with_a_tag_reads_as_none`;
    `::test_the_web_reads_a_tag_by_the_pattern_the_server_writes_it_to` (mẫu `TAG_RE` của server
    trùng mẫu ở `web/src/lib/artifact-tag.ts`, đọc từ tệp TS)
  - pytest (`tags_of`, `merged`, `WrittenCanvases`):
    `::test_each_tool_that_writes_a_canvas_names_the_version_it_left` (bốn tool ghi, chạy thật);
    `::test_a_tool_that_writes_no_canvas_names_none_whatever_its_result_says`;
    `::test_a_write_that_was_refused_names_nothing`;
    `::test_a_write_that_changed_nothing_names_nothing`;
    `::test_a_delegated_task_names_what_its_child_wrote_even_when_the_wait_ran_out`;
    `::test_a_live_turn_keeps_what_a_child_wrote_before_its_wait_ran_out` (kết quả giao việc hết
    giờ là một kết quả hỏng: xem lúc lượt đang chạy hay đọc lại từ run đều nêu cùng canvas);
    `::test_a_canvas_written_twice_is_named_once_at_its_newest_version_where_it_first_stood`;
    `::test_a_live_turn_is_watched_without_changing_what_passes`;
    `::test_a_turn_that_breaks_is_still_broken_and_keeps_what_it_wrote_by_then`
  - pytest (`written_by`, đọc từ tin tool run đã lưu):
    `::test_a_run_with_no_lapsed_approval_names_everything_it_wrote` (thẻ trong lời của model
    không tính);
    `::test_a_run_whose_approval_lapsed_names_only_what_it_wrote_after_the_last_one` (phần trước
    mốc đã được nêu lúc run dừng lại; yêu cầu bị từ chối không phải mốc);
    `::test_a_person_who_quotes_the_lapsed_sentence_marks_nothing`;
    `::test_what_another_run_of_the_conversation_wrote_is_not_this_runs`;
    `::test_no_run_and_a_run_that_does_not_know_where_it_began_name_nothing`
  - pytest (`notice_text`, lời của danh sách):
    `::test_the_notice_names_each_canvas_with_the_version_written_and_its_page`;
    `::test_without_an_address_the_notice_says_where_to_look`;
    `::test_the_notice_names_only_what_the_agent_still_reaches` (canvas đã xoá và canvas ngoài
    tầm bị bỏ; không còn canvas nào thì không có danh sách);
    `::test_a_long_list_is_cut_at_ten_and_the_rest_counted`;
    `::test_a_canvas_renamed_since_is_named_by_its_new_title`;
    `::test_a_secret_in_a_title_is_covered`
  - pytest (`tests/test_delegate_outcome.py`, khối canvas trong kết quả giao việc):
    `::test_the_canvases_a_result_names_are_read_back_as_they_were_written`;
    `::test_a_result_that_names_no_canvas_reads_as_none`;
    `::test_a_tag_in_the_childs_own_words_is_not_a_canvas_it_wrote`;
    `::test_anything_but_the_block_as_the_tool_writes_it_names_no_canvas` (cùng luật với thẻ
    giao việc trên web: dòng outcome, dòng trống bên dưới, mọi dòng ở giữa mở bằng thẻ; chữ
    `outcome=` agent con tự viết bên dưới dòng trống không phải dòng outcome)
  - pytest (`tests/test_telegram_canvas_notice_sent.py`, run gửi sau qua `deliver`):
    `::test_a_brief_is_followed_by_its_files_then_its_canvases_then_why_it_stopped`;
    `::test_a_run_that_only_wrote_canvases_is_answered_by_their_list` (không còn canvas nào để
    nêu thì vẫn là câu "không có nội dung" như trước);
    `::test_a_run_that_stopped_without_a_word_names_what_it_wrote_before_saying_so`;
    `::test_a_run_that_wrote_no_canvas_gets_no_list`;
    `::test_what_no_run_is_known_to_have_written_is_not_named`;
    `::test_a_crew_members_list_goes_out_under_its_name`;
    `::test_a_brief_sends_and_names_what_its_own_conversation_holds`;
    `::test_a_wordless_brief_names_what_its_own_conversation_holds`;
    `::test_a_run_delivered_twice_names_each_canvas_once` (chờ duyệt rồi hết hạn: hai lần gửi,
    mỗi canvas nêu một lần);
    `::test_the_list_is_of_what_the_run_had_written_when_delivery_began` (thứ run ghi thêm, hay
    run sau ghi, trong lúc đang gửi thuộc về lần gửi sau)
  - pytest (lượt sống qua `reply_to`):
    `::test_a_turn_names_its_canvases_after_its_reply_and_the_files_it_attached`;
    `::test_a_turn_that_only_wrote_canvases_is_answered_by_their_list`;
    `::test_a_wordless_turn_that_wrote_nothing_is_answered_as_it_always_was`;
    `::test_a_turn_that_breaks_still_names_what_it_wrote`;
    `::test_a_turn_sends_and_names_what_its_own_conversation_holds`;
    `::test_each_leg_of_a_turn_that_waited_for_approval_names_its_own` (vòng lặp thật, `/approve`)
  - pytest (job và lúc Telegram từ chối):
    `::test_a_job_names_what_it_wrote_unless_it_has_nothing_to_report` (job trả lời `OK` vẫn im
    lặng dù có ghi canvas);
    `::test_a_list_that_cannot_be_sent_costs_the_turn_one_line` (một dòng báo, lượt không bị coi
    là hỏng);
    `::test_a_wordless_run_whose_list_cannot_be_sent_is_not_called_empty`;
    `::test_with_nothing_to_name_nothing_is_sent_and_with_nothing_written_nothing_is_read`;
    `::test_a_title_that_reads_like_an_attachment_line_attaches_nothing` (tiêu đề là `FILE: …`
    không làm Telegram nhận một lời tải lên nào)
- **Mốc "đã nêu tới đây" của một run là yêu cầu không ai trả lời, dù đó là duyệt tool hay câu hỏi
  `ask_user`, và được nhận ra bằng chính yêu cầu đã hết hạn của lời gọi (`tool_call_id`), không bằng
  chữ của kết quả tool. Run dừng để hỏi, được gửi lúc chờ rồi tự đi tiếp, nêu mỗi canvas đúng một
  lần**
  - pytest (`tests/test_telegram_canvas_notice.py`):
    `::test_a_question_nobody_answered_marks_the_run_like_an_approval_that_lapsed` (câu hỏi có và
    không có mặc định);
    `::test_only_a_request_nobody_answered_is_a_mark_whatever_a_result_says` (kết quả tool chứa
    hay trùng hẳn câu báo hết hạn, câu hỏi được trả lời, tool bị từ chối, mã lời gọi lặp lại dưới
    tool khác: không cái nào là mốc)
  - pytest (`tests/test_telegram_canvas_notice_sent.py`):
    `::test_a_run_whose_question_lapsed_between_two_deliveries_names_each_canvas_once` (lần gửi
    thứ hai là lời của run rồi danh sách chỉ có canvas thứ hai; không có dòng báo hết hạn duyệt);
    `::test_a_job_that_asked_and_went_on_unanswered_names_each_canvas_once` (job thật và lượt quét
    hết hạn thật)
  - Các bước dựng dùng chung ở `tests/lapse_helpers.py`: lời gọi của model, yêu cầu nó mở, và tin
    tool đóng yêu cầu bằng chính lời của vòng lặp (`close_interrupted`).
- **Một yêu cầu hết hạn chỉ là mốc một lần: kết quả đầu tiên của chính tin assistant đã mở nó. Model
  gửi lại mã lời gọi ấy thì kết quả của lời gọi mới không phải mốc thứ hai, nên canvas ghi giữa hai
  kết quả vẫn được nêu**
  - pytest (`tests/test_telegram_canvas_notice.py`):
    `::test_a_request_is_closed_once_whatever_comes_under_its_call_id_afterwards` (tool chạy được,
    bị từ chối lần nữa, bị báo trùng mã, câu hỏi được đáp lại như lần trước; có và không có lời gọi
    của model đứng trước kết quả; id của tin nhắn khác thứ tự của nó trong hội thoại);
    `::test_a_result_under_another_tools_name_closes_no_request` (kết quả đứng đầu dưới mã ấy mà
    mang tên tool khác thì không đóng yêu cầu);
    `::test_a_request_is_closed_by_its_own_call_wherever_that_stands_in_the_message` (một tin của
    model gọi ba tool, lời gọi phải chờ đứng đầu, giữa hay cuối: kết quả của chính nó là mốc,
    canvas ghi trước nó đã được nêu lúc dừng, canvas ghi sau nó còn phải nêu)
  - pytest (`tests/test_telegram_canvas_notice_sent.py`):
    `::test_a_job_whose_model_asks_again_under_the_same_id_names_what_it_wrote_between` (job thật,
    lượt quét hết hạn thật, vòng lặp thật đáp cùng một mã hai lần);
    `::test_a_later_run_that_sends_a_lapsed_calls_id_again_names_all_it_wrote` (hết hạn ở run
    trước, run sau dùng lại mã: qua ba lần gửi mỗi canvas được nêu đúng một lần)
- **Dòng khép một lượt trên Telegram (danh sách canvas, hay câu "không có nội dung" được giữ lại
  cho lúc không còn canvas nào để nêu) mà không gửi được thì chat vẫn nghe báo lượt hỏng theo loại
  lỗi, như mọi lỗi khác của lượt**
  - pytest (`tests/test_telegram_canvas_notice_sent.py`):
    `::test_a_closing_line_that_cannot_be_sent_is_a_failure_the_chat_hears_of` (lượt không lời có
    ghi canvas, canvas bị xoá trước khi lượt xong, Telegram từ chối câu còn lại: chat nhận
    `TELEGRAM_TURN_FAILED`, log ghi lỗi kèm nguyên nhân)
- **Câu của chính runtime gửi lên Telegram (báo duyệt hết hạn, lượt dừng sớm, lượt chưa có câu
  trả lời, lượt không có nội dung, lỗi của lượt đang chạy) được gửi nguyên văn, không đọc để tìm
  dòng `FILE:`/`MEDIA:`: dòng trông như vậy nằm lại trong câu và không tệp, ảnh hay canvas nào
  được gửi theo**
  - pytest (`tests/test_telegram_runtime_sentences.py`):
    `::test_why_a_failed_run_stopped_is_said_whole_and_attaches_nothing` (run hỏng, lý do là lỗi
    của provider có ba dòng đính kèm trỏ tới thứ có thật; có lời và không lời);
    `::test_the_question_a_job_waits_on_is_said_whole_and_attaches_nothing` (job thật được giao
    lúc đang chờ câu hỏi của chính nó);
    `::test_no_sentence_of_a_delivery_is_read_for_attachment_lines_whatever_it_says` (từng câu
    trong bốn câu của `deliver`, đổi hẳn lời thành một dòng `FILE:`);
    `::test_a_reason_longer_than_one_message_arrives_whole` (lý do dài hơn một tin vẫn tới đủ,
    cắt ở chỗ xuống dòng);
    `::test_a_live_turn_that_broke_says_the_error_whole_and_attaches_nothing` (vòng lặp thật,
    provider lỗi);
    `::test_a_turn_that_spoke_before_it_broke_attaches_what_it_named_and_no_more` (lời của agent
    vẫn được đọc, câu lỗi bên dưới thì không, cả hai vẫn chung một tin);
    `::test_a_reply_keeps_its_error_apart_and_reads_whole_as_it_always_did` (`collect_reply` giữ
    câu lỗi riêng ở `error`, `said` là phần còn lại, `to_dict` cho relay API không đổi);
    `::test_only_the_error_a_reply_ends_with_is_kept_out_of_what_was_said` (agent tự trích đúng
    câu lỗi đó trong lời của mình thì `said` vẫn giữ đủ lời: chỉ câu lỗi ở cuối bị tách ra)
- **Câu trả lời của `/status`, `/tools`, `/new` và lệnh lạ trên Telegram cũng là câu của runtime:
  gửi nguyên văn, không đọc để tìm dòng `FILE:`/`MEDIA:`, nên tiêu đề hội thoại trông như dòng
  đính kèm vẫn nằm trong `/status` và không tệp nào được gửi theo. `/approve` và `/deny` như cũ:
  tự nó không nói gì, còn câu trả lời của lượt chạy tiếp là lời của agent nên vẫn được đọc**
  - pytest (`tests/test_telegram_runtime_sentences.py`):
    `::test_a_status_is_said_whole_whatever_the_conversation_is_titled` (tiêu đề lần lượt là dòng
    trỏ tới một canvas, một ảnh, một tài liệu đều có thật);
    `::test_no_answer_to_a_command_is_read_for_attachment_lines_whatever_it_says` (`/tools`,
    `/new` lúc rảnh và lúc còn tin xếp hàng, lệnh lạ, `/approve` và `/deny` khi không có gì chờ
    duyệt: đổi hẳn lời thành một dòng `FILE:`);
    `::test_a_command_is_answered_under_no_name_in_a_chat_a_crew_shares` (chat cả đội dùng chung:
    câu trả lời không mang tên thành viên nào ở đầu);
    `::test_a_decision_says_nothing_itself_and_the_reply_it_resumes_is_the_agents` (`/approve` và
    `/deny` khi một tool đang chờ: chat chỉ nhận lời của lượt, tệp lời ấy nêu vẫn được gửi)
- **Lý do một run con dừng dở được trích vào kết quả `delegate` trên một dòng và cắt như mọi
  trường trích khác, nên dòng `FILE:`/`MEDIA:` trong lỗi của provider hay trong câu hỏi của con
  không thành dòng đính kèm của cha**
  - pytest (`tests/test_delegate_unfinished.py`):
    `::test_the_reason_a_run_stopped_for_is_quoted_on_one_line_and_cut_like_the_calls_under_it`
    (lý do nhiều dòng về một dòng; lý do dài bị cắt ở `FIELD_CHARS`; không có lý do thì dùng
    trạng thái);
    `::test_a_child_whose_error_names_files_hands_the_parent_no_attachment_to_send` (con thật có
    provider lỗi, `dropped_attachments` của cha trả về rỗng)
