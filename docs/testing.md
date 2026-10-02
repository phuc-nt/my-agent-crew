# Kiểm thử

**Phiên bản**: 0.10.0 · **Cập nhật**: 2026-09-30

Ba tầng, một quy tắc: **mỗi tính năng ra kèm một test ở tầng thấp nhất có thể thấy nó.**
Bản thân các tệp test là bản kiểm kê đầy đủ; trang này nói mỗi tầng dùng để làm gì, chạy ra
sao, và — ở mục cuối trang — tính năng nào được test ở đâu, để người sửa một tính năng biết
test nào phải đổi theo. Số lượng test không giữ ở đây — chạy lệnh.

| Tầng | Chạy bằng | Thấy được gì |
|---|---|---|
| pytest (`tests/`) | `uv run pytest -q` | vòng lặp, tool, store, provider, profile, scheduler, kênh, HTTP API và các stream SSE của nó — mọi thứ server làm, với model thay bằng `MY_AGENT_ROUTES=fake:echo` |
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
  - vitest: `lib/error-text.test.ts`; `components/cap-editor.test.tsx`
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
- **Ảnh từ trang khác trong câu trả lời và trang wiki chỉ tải khi bấm, không gửi referrer**
  - vitest: `components/markdown-body.test.tsx` "an image in a reply"
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
  - Playwright: `touch-targets-phone.spec.ts` — quét mọi nút, link, ô nhập, select, summary,
    công tắc và tab trên từng trang (chat, mười trang Quản lý) và trong drawer cuộc trò chuyện ở
    390×844 cảm ứng; checkbox đo theo label bọc nó, link nằm trong câu được miễn như WCAG
    ("every control on %s is big enough for a finger",
    "every control in the phone's conversation drawer is big enough for a finger")
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
    stopped", "aborts a queueing POST still in flight when the conversation is switched", nhóm
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
- **Lượt Telegram chạy nền: chat được đọc trong lúc lượt chạy**
  - pytest: `tests/test_telegram_background.py` (`/status` trả lời giữa lượt, tin thứ hai xếp
    hàng không kèm "đang gõ…" rồi được trả lời riêng, `/new` bị từ chối khi đang chạy; `/steer`
    tới lượt đang chạy, `/steer` trơn bị từ chối và không vào hàng; lượt qua nửa đêm giữ cuộc trò
    chuyện; dừng bot chờ lượt xong trong hạn, quá hạn thì huỷ và báo một lần; lượt hỏng chỉ nêu tên
    loại lỗi; bot trả lời tin chờ từ lúc start tới lúc stop; "đang gõ…" treo không giữ câu trả
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
- **Tham số lời gọi tool không phải JSON object thành lỗi tool, lượt vẫn chạy tiếp**
  - pytest: `tests/test_tool_args_invalid.py` (tham số bị cắt giữa chừng báo vị trí chỗ dừng
    chứ không phải chỗ chuỗi bắt đầu, lỗi giữa chừng báo vị trí và vài chục ký tự quanh đó với
    ký tự điều khiển viết thành `<U+000A>`, escape `\u` sai gần cuối không bị coi là bị cắt,
    JSON không phải object được gọi theo kiểu, tham số đúng hay rỗng không bị đánh dấu, chi
    tiết không bao giờ lên wire, lời gọi hỏng lưu và đọc lại được còn lời gọi thường giữ đúng
    dạng hàng cũ, lời gọi hỏng không chạy mà trả lỗi rồi lượt chạy tiếp, `ask_user` và tool cần
    duyệt có tham số hỏng không hỏi ai); `tests/test_openrouter.py`
    ("test_malformed_tool_arguments_complete_as_an_invalid_call")
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
    dự phòng và `filename*` giải mã lại đúng tên);
    `tests/test_server_agents_activity_jobs.py::test_agent_files_are_served_only_from_the_workspace`
    (chỉ tệp trong workspace, kể cả qua symlink)
- **Canvas: tài liệu có phiên bản đi cạnh cuộc trò chuyện (tầng lưu trữ)**
  - pytest: `tests/test_artifact_kinds.py` (mỗi loại là chữ hoặc nhị phân, mỗi loại một trần,
    loại lạ bị từ chối theo tên, lỗi kích thước là `ValueError` để một chỗ trả lời được mọi đầu
    vào sai, "test_a_title_is_one_line_of_visible_text": xuống dòng thành dấu cách, bỏ ký tự
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
    trần không lưu gì, trần đo trên chữ đã đổi xuống dòng, thứ không tồn tại là `KeyError`,
    "test_a_version_gone_from_a_canvas_that_is_there_names_the_newest": bản đã bị gộp hay chưa
    từng có là `VersionGone` kèm số bản mới nhất, xoá canvas bỏ phiên bản, liên kết và focus của
    nó, "test_list_matches_the_title_regardless_of_case_and_accents", hai canvas cùng giây xếp
    theo thứ tự tạo, "test_on_change_hears_every_write_after_commit_outside_the_lock",
    "test_a_failing_on_change_is_logged_and_the_write_stands")
- **Canvas: năm tool để agent tạo, liệt kê, đọc, sửa và viết lại canvas**
  - pytest: `tests/test_artifact_tools.py` (năm tool, không tool nào hỏi duyệt, mô tả đưa tài
    liệu người sẽ sửa dần vào canvas dù chỉ vài dòng và nói cách thêm chữ bằng một lần sửa, tạo lưu canvas
    dưới tên agent và không trả lại nội dung, con được giao việc chia sẻ canvas nó tạo với gốc,
    loại agent không ghi được bị từ chối,
    "test_only_the_web_chat_writes_a_canvas_yet_any_channel_reads_one", con chỉ ghi được trong
    chuỗi bắt đầu từ web chat, canvas master đã đọc không vào tầm của con, lần đọc của một con
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
    "test_a_kind_agents_do_not_write_is_refused_only_once_the_canvas_is_in_reach", diff trích
    dãy backtick có rào dài hơn, sửa khớp hai chỗ bị từ chối trừ khi thay mọi chỗ);
    `tests/test_canvas_tool_wiring.py` (agent không có allow-list, master hay không, nhận đủ năm
    tool theo thứ tự, "test_an_allow_list_keeps_out_the_canvas_tools_it_does_not_name", master
    liệt kê mọi canvas theo giờ của chủ còn agent khác thì không, trang đọc vừa trần đầu ra của
    chính agent)
- **Canvas: kênh nào ghi được, agent với tới canvas nào, một lượt ghi bao nhiêu, ai viết các bản
  chưa thấy**
  - pytest: `tests/test_artifact_scope.py`
    ("test_only_a_turn_from_the_web_chat_writes_a_canvas",
    "test_a_delegated_child_writes_only_when_its_chain_began_in_the_web_chat": con mở trước khi
    chuỗi ghi gốc thì không bao giờ ghi, người gõ thẳng vào cuộc trò chuyện của con thì ghi được từ
    đó, agent chỉ ghi markdown và code, lần ghi thứ 31 cho một canvas trong lượt bị từ chối, một
    lượt tạo tối đa 30 canvas,
    "test_a_batched_call_counts_toward_its_turn_and_a_child_turn_counts_apart", master với tới mọi
    canvas còn agent khác chỉ canvas của mình, canvas một lượt trong chuỗi chỉ đọc không vào tầm
    của con kế tiếp, mỗi lời từ chối của kho thành lời dặn,
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
    giới hạn dòng, `old` quá dài thì không tìm); `tests/test_artifact_diff.py` (hai dạng thẻ đọc lại
    qua cùng một mẫu, thẻ chỉ tính khi đứng ngay đầu kết quả, rào dài hơn mọi dãy backtick bên
    trong, dòng vừa chỗ giữ nguyên, dòng dài hiện quanh phần cần xem,
    "test_removed_lines_take_at_most_half_and_what_was_written_always_shows", dòng dài bị đổi cắt
    quanh chỗ đổi ở cả hai bên, "test_the_diff_never_outgrows_its_budget", số đếm cuối luôn vừa
    ngân sách, dòng thêm dài bị cắt cho vừa chỗ chứ không bị bỏ, tiêu đề đoạn đánh số dòng chỉ theo
    LF và theo chỗ trong chữ mới, không khác gì thì diff rỗng, chỉ phần giữa đã đổi được so,
    "test_a_diff_quoting_a_backtick_run_is_drawn_again_to_fit_a_longer_fence", chỗ quá nhỏ vẫn kết
    thúc bằng số đếm)
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
    "test_every_canvas_tool_argument_that_carries_document_text_is_trimmed",
    "test_a_note_is_always_shorter_than_the_text_it_stands_for")
- **Canvas: lượt không ghi được canvas được báo trước trong system prompt**
  - pytest: `tests/test_canvas_prompt_tail.py`
    ("test_a_turn_that_cannot_write_a_canvas_is_told_so_with_the_same_tools": Telegram, job, API và
    con có chuỗi bắt đầu từ Telegram nghe mục này, sau ghi chú ngày và ngay trước dòng ngày, cùng
    bộ tool; web chat và con của nó thì không,
    "test_the_note_names_only_the_canvas_writes_the_agent_holds", prompt thường trực không có mục
    này, "test_the_note_lists_exactly_the_tools_a_closed_channel_refuses")
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
    hội thoại được chia sẻ và mở ở đó, hội thoại không có thì 404 và không tạo gì, web chỉ tạo
    markdown và code, tiêu đề kho từ chối là 422, quá trần là 413 và không ghi gì, kho đầy là 507
    nêu các canvas lớn nhất,
    "test_the_detail_is_one_version_whole_though_a_write_lands_between_its_reads", canvas không có
    là 404 ở mọi route, "test_a_save_without_a_real_base_version_is_422_and_writes_nothing": thiếu,
    `true` hay `0` đều bị từ chối, lưu trên bản cũ là 409 kèm bản mới nhất và không ghi gì, hai lần
    lưu trong một đợt gộp mà số bản vẫn tăng, đổi tên không thêm bản, danh sách mới nhất trước và
    lọc theo hội thoại hay tiêu đề, `limit` từ 1 tới 200); `tests/test_artifact_errors.py` (mỗi lời
    từ chối của kho ra đúng mã:
    "test_a_version_folded_away_is_404_with_the_newest_number_though_it_is_a_key_error", `KeyError`
    của id khác và `ValueError` bảng không nêu đi tiếp như lỗi thật, 409 đọc lại bản mới nhất chứ
    không dùng bản lúc xung đột, canvas bị xoá giữa chừng là 404, 413 nêu cỡ và trần,
    "test_full_storage_is_507_naming_the_three_largest_canvases_biggest_first", 422 mang lời của kho)
- **Canvas qua REST: lịch sử phiên bản, khôi phục và chữ thô không chạy gì**
  - pytest: `tests/test_api_artifact_history.py` (phiên bản mới nhất trước và không kèm chữ, một bản
    đọc trọn, bản đã gộp là 404 kèm số bản mới nhất, canvas không có là 404 ở mọi route lịch sử,
    "test_a_restore_writes_the_old_version_as_the_persons_newest": ghi chú `restore:<n>`, số bản
    khôi phục phải là số nguyên thật, "test_the_raw_text_is_plain_text_that_runs_nothing": `raw` luôn
    là `text/plain` sandbox kèm `nosniff` và CORP dù canvas chứa HTML, chữ thô của một bản cũ,
    "test_a_download_is_named_after_the_title_in_any_script"); `tests/test_artifact_filenames.py`
    ("test_a_file_name_keeps_the_title_in_any_script_without_what_a_file_system_refuses",
    "test_a_file_name_ends_in_the_extension_of_its_kind": markdown là `.md`, code theo ngôn ngữ, ngôn
    ngữ lạ là `.txt`, code `html` là `.html.txt` để mở tệp tải về chỉ thấy chữ, không chạy script)
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
    "test_the_open_canvas_is_named_once_while_messages_keep_carrying_it")
- **Mọi thay đổi canvas tới web qua luồng hoạt động, kể cả lần ghi từ luồng khác; không lần đọc
  nào đổi trạng thái**
  - pytest: `tests/test_artifact_events.py` ("test_every_change_made_over_rest_is_announced": tạo,
    lưu, đổi tên, khôi phục và xoá, mỗi lần một event `artifact` kèm hội thoại liên kết,
    "test_a_canvas_an_agent_writes_with_its_tool_is_announced",
    "test_a_write_from_another_thread_reaches_the_watchers_loop": loop chạy ở chế độ debug, lần ghi
    từ luồng khác tới watcher trong 0,5 s mà không có lỗi nào; thiếu bước chuyển về loop thì test
    đỏ chứ không treo); `tests/test_api_artifact_invariants.py`
    ("test_every_canvas_route_and_the_chat_message_run_on_the_event_loop",
    "test_no_read_changes_what_a_conversation_knows_or_has_open": mọi `GET` canvas giữ nguyên liên
    kết, con trỏ đọc, canvas đang mở, phiên bản và tin)
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
    tới mọi luồng đang mở)
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
    mất, quá trần hay đang dừng)
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
    `compositionend`, khôi phục đặt chữ và base không chờ luồng); `web/src/lib/canvas-draft.test.ts`
    (nháp chỉ của đúng canvas, xoá khoá cũ trước khi ghi nên kho đầy không để lại nháp, trình duyệt từ
    chối thì báo, "clears a draft only while it still holds the text that was saved", giữ mười nháp mới
    nhất, bỏ nháp quá ba mươi ngày và nháp hỏng); `web/src/lib/local-store.test.ts` (liệt kê khoá theo
    tiền tố, lần ghi báo có được giữ không khi trình duyệt từ chối hay hết quota)
- **Canvas trên web: canvas đang mở lưu 1,5 giây sau phím cuối, rời đi vẫn lưu nốt, keepalive chỉ khi
  vừa trần**
  - vitest, hook trên `FakeCanvas` với đồng hồ giả: `web/src/hooks/use-canvas.test.ts` ("saves once,
    1.5 s after the last of thirty keystrokes and not a moment sooner", Cmd/Ctrl+S lưu ngay và không lưu
    lại khi hết lúc dừng gõ, sửa mà chữ không đổi không lùi lần lưu, "says so when this device cannot
    keep the draft, until it can again", canvas 100 KB ẩn tab hay tháo panel đi bằng request thường và
    nháp giữ phím gõ ngay trước, canvas 10 KB tháo panel thì một `PUT` keepalive đúng base, "forgets the
    draft of a canvas deleted while open once its panel goes");
    `web/src/hooks/use-canvas-switch.test.ts` ("shows the next canvas at once and finishes the last
    one's save behind it", thử lại đang chờ được thử thêm một lần khi rời rồi dừng, ẩn tab lúc canvas
    sau đang tải không lưu gì cho nó, "lets a canvas left behind finish its save without reading it
    again or showing it", cờ nháp hỏng không theo sang canvas sau);
    `web/src/hooks/use-canvas-sync.test.ts` (đọc lại khi luồng nối lại sau lần rớt mà không đọc lúc mới
    nối, khi tab hiện, khi event báo bản mới; lần lưu không reply trong 30 giây là mất và được gửi lại;
    nháp qua lần mount thử của StrictMode; "opens text typed after a save that landed unheard as the
    person's draft, not as a clash"; năm test `flush`); `web/src/lib/canvas-handoff.test.ts` (lần lưu
    cuối của canvas đã rời: 409 của chính mình là đã lưu, lỗi giữ nháp và báo người nghe còn đăng ký,
    gửi chữ gõ sau lần lưu đang bay, ngân sách keepalive tính bằng byte, mỗi lúc một lần lưu keepalive,
    lỗi trả lại ngân sách)
- **Canvas trên web: tên người viết một bản, kích thước đọc được, ký tự ẩn hiện ra**
  - vitest: `web/src/lib/canvas-author.test.ts` (người là "bạn", agent theo tên, agent có id `user` vẫn
    là agent, agent không còn thì theo id); `web/src/lib/format-bytes.test.ts` (bước 1024, một chữ số lẻ
    dưới mười viết bằng dấu phẩy, làm tròn tới 1024 thì lên đơn vị); `web/src/lib/hidden-chars.test.ts`
    ("shows a right-to-left override as a visible mark", mọi ký tự điều khiển bidi và zero-width)
- **Mã agent khớp cả chuỗi: chữ thường, số và gạch ngang, không cả xuống dòng ở cuối**
  - pytest: `tests/test_api_agents_edit.py::test_an_id_that_is_not_a_safe_folder_name_is_refused`
    (`../escape` và `coder` có xuống dòng ở cuối đều bị từ chối, không thư mục nào được tạo);
    `tests/test_artifact_guards.py`
    ("test_an_author_that_is_neither_the_person_nor_an_agent_is_refused",
    "test_a_creator_that_does_not_match_its_author_is_refused": `agent:Coach` và mã có xuống
    dòng ở cuối không ghi được canvas); mẫu ở `my_agent_crew/agent_ids.py`
