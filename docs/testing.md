# Kiểm thử

**Phiên bản**: 0.9.2 · **Cập nhật**: 2026-09-28

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

- **ngân sách kích thước tệp**: không tệp nguồn nào quá 200 dòng, để module đọc gọn trong một màn hình;
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
  trong tham số viết thành JSON, lượt đếm từ 1), `max_calls`, `reply_contains`,
  `reply_not_contains` (không phân biệt hoa thường và dấu), `delegates_to` (`{agent, outcome?}`;
  `outcome` là một trong năm giá trị của dòng `outcome=` trong kết quả giao việc) và `max_cost_usd`.
  Khoá lạ, regex hỏng hay id trùng bị từ chối *trước* khi tốn đồng nào. Việc một agent con làm
  tính vào lượt của cha đã giao nó.
- **Mỗi case chơi `--runs` lần** (mặc định 3) và đạt khi ít nhất hai phần ba số lần đạt. Số tiền
  là mức sổ cái của server tăng lên kể từ lúc bắt đầu, lời gọi bên cạnh lượt cũng tính; trước mỗi
  lần chơi mà đã hết `--max-usd` (mặc định 0.5) thì dừng. Có lời gọi provider không báo giá thì
  tổng chỉ là cận dưới và báo cáo nói vậy.
- **Kết quả** ghi vào `<out>/results/` (`--out`, mặc định `$TMPDIR/my-agent-crew-evals`, không
  được nằm trong repo): `results.md` nêu kỳ vọng nào hỏng ở lần chơi nào, kèm lời đáp rút gọn;
  `results.json`; `server.log`. Ghi sau mỗi lần chơi, nên cuộc chạy bị cắt vẫn để lại số của
  những lần đã xong.
- **Một lượt quá `--turn-timeout`** (300 giây, tính cả khi luồng SSE vẫn gửi keep-alive) hay một
  lỗi HTTP dừng cả cuộc eval: nó không còn biết server có sống không. Ctrl-C và SIGTERM cũng
  dừng server và xoá bản sao.
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
  biến chứa token bot mà hồ sơ live gọi tên bị giữ ngoài môi trường của server, và
  `MY_AGENT_SHELL_ALLOW_PATTERNS` cũng vậy.

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
lại: `HOME` của server trỏ vào bản sao, môi trường của shell chỉ có một danh sách nhỏ biến, bản
sao không có `.venv` và không có symlink. Một chuỗi trong manifest hay `config.yaml` vẫn nêu
đường dẫn live được báo trong cảnh báo của lần chạy chứ không bị viết lại.

Model giả (`fake:echo`) cấp cho mỗi lệnh gọi một mã riêng, như provider thật vẫn làm: agent con
được tìm lại theo mã lệnh gọi của cha, nên hai cuộc trò chuyện giao việc ở cùng một chỗ mà cùng
mã thì cuộc sau nhận nhầm agent con của cuộc trước.

Mã nằm trong `scripts/`, tách theo việc để mỗi tệp ≤ 200 dòng như mã của gói: `run_evals.py`
(điểm vào), `eval_cli.py` (tuỳ chọn, chọn case, từ chối sớm), `eval_play.py` (chơi một lần, chạy
hết các case), `eval_home.py` + `eval_copy.py` + `eval_layout.py` (bản sao), `eval_cases.py` +
`eval_expect.py` + `eval_check.py` (đọc và chấm case), `eval_observe.py` (biến một cuộc trò
chuyện thành thứ chấm được), `eval_client.py` (duyệt, câu hỏi, sổ cái), `eval_report.py` (báo
cáo). Server và client HTTP chia với bench: `llm_bench_server.py`, `llm_bench_client.py`.

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
- **Kiểm thử hành vi bằng model thật, chạy trên bản sao của home**
  - pytest: `tests/test_eval_cases.py` (đọc case từ tệp hay thư mục; khoá lạ, thiếu id hay
    agent, tin nhắn không phải chuỗi, regex hỏng, id trùng bị từ chối trước khi tốn tiền; từng
    loại kỳ vọng: gọi và không gọi tool theo tên, tham số, agent và lượt, xin duyệt, số lần gọi tối đa,
    câu đáp chứa và không chứa, giao việc cho agent nào và việc đi tới outcome nào (không nêu
    outcome thì outcome nào cũng được, outcome lạ bị từ chối), giá tối đa; "hai phần ba số lần
    chơi đạt thì case đạt");
    `tests/test_eval_observe.py` (mỗi lệnh gọi mang số lượt và agent, việc của agent con tính
    vào lượt của cha đã giao, outcome của mỗi lần giao việc đọc từ dòng hai kết quả của nó, kết
    quả cũ không có dòng đó thì không có outcome; lời đáp cuối, lỗi và giá, tìm ra các cuộc con);
    `tests/test_eval_client.py` (duyệt và từ chối được ghi lại, lệnh nêu đường dẫn live bị từ
    chối kể cả khi chính sách là duyệt, câu hỏi lấy câu trả lời kế tiếp và hết thì hỏng, một
    lượt vẫn bị cắt khi luồng cứ gửi keep-alive, yêu cầu duyệt của agent con được trả lời, được
    hỏi lại khi nó xin lần nữa, và hỏng rõ ràng khi không trả lời được);
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
    mất server dừng cả cuộc, các từ chối trước khi chép gì, chạy thử qua một server thật);
    `tests/test_llm_bench_client.py` (môi trường của server bench và eval không mang home,
    token bot hay danh sách cho phép lệnh shell của người chạy);
    `tests/test_serve_flags.py` (`--no-schedule` tắt cả scheduler lẫn kênh, không đụng `--port`);
    `tests/test_echo_provider.py` (mỗi lệnh gọi của model giả có mã riêng, như provider thật,
    nên hai cuộc trò chuyện giao việc ở cùng một chỗ không nhận nhầm agent con của nhau)
  - Thủ công, tốn tiền thật: `scripts/run_evals.py` trên các case trong `<home>/evals/`
- **Kết quả giao việc nói việc đi tới đâu (`outcome=` ở dòng hai), không chỉ run kết thúc ra sao;
  chỉ việc đi tới `done` mới được chuyển thẳng cho người dùng**
  - pytest: `tests/test_delegate_outcome.py` (dòng `Status:` theo mọi kiểu model viết,
    `DONE_WITH_CONCERNS` không bị đọc thành `DONE`, dòng cuối thắng, trạng thái lạ bị bỏ qua, lý do
    lấy từ `Summary:` khi dòng `Status:` không có, chữ `BLOCKED` trần chỉ tính khi không có dòng
    `Status:`; runtime thắng lời khai: run không xong là `failed`, approval tool quyết định gần nhất
    bị từ chối hay hết hạn là `blocked`, câu hỏi không ai trả lời thì không; hết giờ chờ vẫn giữ
    dòng một);
    `tests/test_tools_delegate.py::test_the_first_two_lines_are_the_ones_the_web_card_reads`
    (Python và regex của thẻ web đọc cùng hai dòng),
    `::test_a_child_that_needs_more_context_is_not_handed_on`,
    `::test_a_child_done_with_concerns_goes_back_to_the_parent_whole`,
    `::test_a_child_that_declares_done_is_handed_on_word_for_word`,
    `::test_a_child_whose_last_approval_was_refused_is_blocked`,
    `::test_a_child_still_waiting_when_the_wait_runs_out_failed`;
    `tests/test_delegate_relay.py::test_a_child_that_needs_more_context_goes_back_through_the_boss`,
    `::test_a_child_halted_for_repeating_itself_is_reported_as_failed`;
    `tests/test_delegation_contract.py::test_every_status_the_skill_offers_is_one_the_parent_reads`
  - vitest: `lib/delegate-result.test.ts` ("reads what the task came to, and why, from the second
    line", "reads an outcome with no reason, and one with no reply after it", "leaves the outcome
    out for a result written before there was one", "goes by the outcome when there is one", "goes
    by how the run ended for a result that has no outcome"); `components/delegate-cards.test.tsx`
    ("says in words what the task came to, and marks one that is not done", "marks a task that
    failed apart from one that only stopped short", "reads a finished task as done, with nothing
    more to explain")
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
