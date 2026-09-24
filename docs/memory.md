# Trí nhớ

**Phiên bản**: 0.5.0 (+ chưa phát hành) · **Cập nhật**: 2026-09-24

Trí nhớ là Markdown trên đĩa, cùng hình dạng với thứ một người có thể tự ghi tay. Không có
gì được embed hay tóm tắt sau lưng agent; model đọc gì thì trên đĩa có đúng thứ đó.

Trí nhớ có hai phạm vi:

- **Dùng chung** — điều cả đội biết về *người dùng*, dưới `<home>/users/owner/`. Mọi agent
  đọc cùng một bộ tệp, nên nói cho một agent điều gì không khiến các agent còn lại phải
  đoán.
- **Theo agent** — điều một agent biết về *việc của chính nó*, trong thư mục agent.

## Phạm vi dùng chung

| Tệp | Vai trò | Đọc vào prompt |
|---|---|---|
| `users/owner/USER.md` | người dùng là ai, bằng lời của chính họ | mỗi lượt, mọi agent |
| `users/owner/facts/<name>.md` | mỗi tệp một điều đã ghi nhớ: frontmatter + thân Markdown | chỉ dòng index của nó; thân qua `memory_search` hoặc `workspace_read` |
| `users/owner/facts/INDEX.md` | mục lục sinh tự động, mỗi fact một dòng | mỗi lượt, mọi agent |

Các phần về người dùng bị giới hạn 4 000 ký tự vì chúng đi kèm trong prompt của mọi agent.
Frontmatter của một fact ghi `name`, `description`, `type` (một trong `profile`,
`preference`, `feedback`, `project`, `reference`), `written_by`, `source` và `updated`;
`INDEX.md` được sinh lại sau mỗi lần ghi.

## Phạm vi riêng của một agent

| Tệp | Vai trò | Đọc vào prompt |
|---|---|---|
| `MEMORY.md` | sự thật bền: người dùng là ai, sở thích lâu dài, quyết định, mọi thứ được cài đặt ra sao | mỗi lượt |
| `memory/YYYY-MM-DD.md` | ghi chú ngày: chuyện gì đã xảy ra, số đo, ai đã nói gì | tệp hôm nay và hôm qua, mỗi lượt |
| `memory/*.md` cũ hơn | lịch sử | chỉ qua `memory_search` |

Một ghi chú được đặt tên theo ngày của nó, kèm hậu tố tuỳ chọn — `2026-09-19.md` và
`2026-09-19-1030.md` đều là ghi chú của ngày 19 tháng 9; đó là cách một workspace do tool
khác viết giữ nhiều ghi chú trong một ngày. Hậu tố gồm chữ thường, chữ số và gạch nối, nên
một tên không bao giờ trỏ được ra ngoài thư mục. `memory_save` luôn ghi vào tệp
`YYYY-MM-DD.md` trơn, và chỉ tên đó được đọc vào prompt; ghi chú có hậu tố là lịch sử, tới
được qua `memory_search`, tab Ghi nhớ và cô đọng.

Mỗi tệp trở thành một mục `## <file name>` trong system prompt, giới hạn 24 000 ký tự (cắt
kèm dấu `…` ở cuối). Tệp thiếu thì đơn giản là bỏ qua. Các tệp nằm ở
`<agent dir>/MEMORY.md` và `<agent dir>/memory/` (tạo lúc khởi động); agent mặc định giữ
chúng ngay trong `MY_AGENT_HOME`.

## Ghi trí nhớ

Có vài cách, tất cả đều thấy được trong tab **Ghi nhớ** của màn hình quản lý:

- **`user_memory_save` / `user_memory_forget`** ghi một fact dùng chung. Có ghi hay không
  tuỳ vào ai đang có mặt: trong một lượt có người ở đó (chat, Telegram) thì ghi ngay; trong
  một job theo lịch thì nó trở thành **đề xuất** chờ xem xét, vì không có ai ở đó để sửa một
  phán đoán sai. Tiếp tục một job đang tạm dừng vẫn giữ nguồn của job, nên một lần duyệt
  giữa chừng không biến nó thành lượt chat.
- **`memory_save`** nối thêm một dòng `- HH:MM <text>` vào ghi chú hôm nay, tạo tệp với
  tiêu đề `# YYYY-MM-DD` nếu chưa có. Không cần duyệt: một ghi chú không phải thay đổi
  trạng thái bên ngoài cuộc trò chuyện. Dùng nó cho những điều đáng nhớ tới ngày mai.
- **`workspace_write` / `shell_run`** cho `MEMORY.md` và để viết lại một ghi chú, vì trí
  nhớ bền nên được sửa một cách có chủ đích. `workspace_write` chỉ chạm tới các tệp này khi
  workspace là thư mục agent; nếu không, tệp persona (`AGENTS.md`) nên nói rõ agent duy trì
  `MEMORY.md` bằng cách nào, ví dụ bằng heredoc qua `shell_run` hoặc một script.

## Đọc trí nhớ

- **`memory_search <query>`** trả về tối đa 12 kết quả dạng `[<file> › <heading>]
  <entry>`. Đơn vị là **entry**, không phải dòng: một bullet cùng các dòng tiếp nối thụt
  lề của nó, hoặc một đoạn văn. Một ý viết trên hai dòng — `- Jimny 5 cửa,` /
  `  ngân sách 1.5 tỷ` — là một kết quả có cả hai nửa, điều mà so khớp từng dòng sẽ đánh
  mất. Heading mà entry nằm dưới đi cùng với nó, vừa làm ngữ cảnh trong nhãn vừa là văn bản
  có thể so khớp.
- So khớp bỏ qua dấu ở cả hai phía, nên `sach dang doc` tìm được `sách đang đọc`: một người
  tìm trong ghi chú của mình từ điện thoại hiếm khi gõ dấu. `đ` được xử lý riêng, vì nó là
  một chữ cái của bảng chữ cái tiếng Việt chứ không phải `d` mang dấu, và phép phân rã để
  nó nguyên như cũ.
- Xếp hạng ưu tiên entry có đúng **từ**: một từ tìm thấy nguyên vẹn được tính gấp đôi một
  từ tìm thấy bên trong từ khác, vì khi bỏ dấu, `doc` nằm trong `docs` cũng chắc chắn như
  nằm trong `đọc`. Một từ từ ba ký tự trở xuống chỉ được tính khi tìm thấy nguyên vẹn — `ô`
  thành `o`, thứ có trong gần như mọi entry tiếng Việt. Khi có entry nào đó chứa đủ mọi từ
  của truy vấn, các entry thiếu một từ bị loại; khi không entry nào đủ, các kết quả khớp
  một phần vẫn được hiển thị, vì nửa câu trả lời còn hơn không.
- Thứ tự tệp phân định khi bằng điểm: facts dùng chung trước — điều cả đội biết về người
  dùng xếp trên ghi chú của một agent — rồi đến `MEMORY.md` và mọi tệp markdown trong thư
  mục memory, mới nhất trước, nên một ghi chú mới xếp trên một ghi chú cũ cùng điểm. Các tệp
  không phải ghi chú ngày cũng được tìm, vì một workspace viết tay giữ những thứ như
  `facebook-books.md` ở đó và chúng cũng là trí nhớ. Một fact so khớp trên cả description
  lẫn thân và trả về cả hai, vì một fact là một ý.
- Kết quả dài hơn 300 ký tự được gập về một dòng và cắt kèm `…`.
- Prompt đã chứa sẵn `MEMORY.md` và hai ngày gần nhất, nên model không nên tìm những thứ
  đó.

## Cái gì ghi vào đâu

| Ghi vào | Ví dụ |
|---|---|
| `USER.md` | tên, công việc, người dùng thích được trả lời thế nào |
| một fact | một sở thích lâu dài, một mục tiêu, phản hồi người dùng đã đưa, một dự án họ đang tham gia |
| `MEMORY.md` | hồ sơ người dùng, mục tiêu, ngưỡng, vị trí tool, lịch lặp lại, quy tắc người dùng đã đặt |
| ghi chú hôm nay | một số đo, một quyết định đưa ra hôm nay, một câu hỏi còn bỏ ngỏ, một bản tin đã gửi |
| không ghi đâu cả | bất cứ thứ gì các tệp workspace đã giữ sẵn (tệp dữ liệu, script), output tạm của tool |

Tệp persona (`AGENTS.md` và các tệp cùng nhóm, xem [agents.md](agents.md)) dành cho *cách
hành xử*; trí nhớ dành cho *điều đã biết*. Cả hai đều là dữ liệu cá nhân và ở trong
`MY_AGENT_HOME`, không bao giờ trong repo này.

## Đề xuất

Một job chạy không có người trông, nên lần ghi dùng chung mà nó yêu cầu được giữ trong bảng
`memory_proposals` cho tới khi có người quyết định. Duyệt thì áp dụng lần ghi; từ chối thì
không để lại gì. Quyết định cùng một đề xuất hai lần là xung đột, không phải một lần ghi
mới, nên bấm đúp không thể áp dụng nó lần nữa. `GET /api/stats` mang theo `pending_proposals`
để web UI gắn badge lên tab.

## Cô đọng

Trí nhớ chỉ phình ra: lượt nào cũng có thể nối thêm, không gì xoá bớt, nên `MEMORY.md` trôi
dần thành một danh sách dài những điều từng đúng. Cô đọng nhờ model viết lại tệp từ các ghi
chú ngày gần đây — giữ cái còn đúng, gộp cái trùng, bỏ cái chỉ quan trọng trong một ngày —
và **đề xuất** kết quả thay vì ghi thẳng, vì một lần viết lại có thể làm mất thứ gì đó và
không ai trông job theo lịch. Đề xuất mang theo `previous_body`, văn bản mà nó thay thế,
nên luôn lùi lại được một bước từ danh sách lịch sử.

Một agent tham gia bằng cron `memory_consolidate` trong profile của nó, cron này trở thành
một lịch bình thường (kind `consolidate`) bên cạnh các job prompt và command của nó. Nó đọc
tối đa 7 ngày ghi chú (đếm theo ngày chứ không theo tệp, nên nhiều ghi chú của một ngày vẫn
tính là một ngày đó) trong ngân sách 40 000 ký tự, mới nhất trước, và không làm gì cả khi
không có ghi chú nào mới hơn `MEMORY.md`. Agent được đánh dấu `autonomous` áp dụng bản viết
lại ngay; mọi agent khác thấy nó ở **Ghi nhớ → Đề xuất**. Run xuất hiện trong Activity kèm
chi phí của nó, và một lần viết lại thất bại để tệp y nguyên như cũ.

## Vault wiki

Ghi chú ngày được viết theo ngày, hình dạng đúng để viết nhưng sai để hỏi. "Tôi biết gì về
hạn chót Eco Retreat" rải trên mười một ghi chú, và câu trả lời là mảnh nào tình cờ được
tìm kiếm xếp lên đầu. Vault gom các mảnh đó lên một trang mang tên chính sự vật đó, nên câu
hỏi có một chỗ duy nhất để được trả lời. Nó nằm ở `memory/wiki/` bên trong thư mục agent,
cạnh những ghi chú mà nó được dựng từ đó.

Trang được xếp vào ba thư mục: `entities` cho những thứ có tên (một người, một nơi, một hợp
đồng), `concepts` cho những ý tưởng lặp lại, và `syntheses` cho những trang viết từ nhiều
trang khác chứ không trực tiếp từ ghi chú. Một trang là một tệp markdown có frontmatter —
`title`, `kind`, `sources`, `questions`, `status`, `updated` — và một thân.

Hai quy tắc khiến vault an toàn để dựng lại mỗi đêm:

- **Một trang ghi lại nó đến từ đâu.** `sources` liệt kê các ghi chú hoặc cuộc trò chuyện
  mà nó được dựng từ đó, dạng `note:YYYY-MM-DD` hoặc `conv:<id>`. `wiki_apply` từ chối trang
  không có sources, và lint báo mọi trang đã mất nguồn. Việc này trông như kiểm tra đầu vào
  nhưng thực ra là điểm cốt lõi: một trang không nói được nó đến từ đâu là một trang tự bịa
  ra, và để lọt một trang như thế khiến mọi trang khác kém đáng tin hơn.
- **Chỉ một phần của tệp thuộc về máy.** Mọi thứ giữa cặp marker `wiki:related` được viết lại ở
  mỗi lần compile; mọi thứ còn lại thuộc về người đã viết nó, model hay người, và một lần
  compile trả nó về nguyên vẹn. Không có sự tách bạch đó, vault sẽ hoặc đóng băng hoặc không
  đáng tin.

Tên tệp của một trang là định danh của nó, nên slug quyết định lần ghi nào rơi vào cùng một
trang. Nó bỏ dấu theo đúng cách tìm kiếm làm, nên `Hạn Eco` và `han eco` là một trang chứ
không phải hai trang mỗi trang biết một nửa câu chuyện. Nó giữ chữ cái và chữ số của **mọi**
hệ chữ viết: xếp mọi tiêu đề không phải Latin dưới một tên dự phòng duy nhất không phải là
một cái tên xấu mà là một lần gộp, với trang tiếp theo như thế ghi đè lên trang trước.

### Liên kết

Thân trang liên kết bằng `[[Tên trang]]`. Sau mỗi lần compile hoặc sửa, đồ thị liên kết
được dựng lại, việc này ghi các liên kết vào và ra của mỗi trang vào khối thuộc về máy của
nó. Đó là lý do sửa một trang qua HTTP dựng lại đồ thị ngay lập tức: một liên kết đã sửa
thay đổi điều các trang *khác* nói về nơi chúng được liên kết từ, và để đến lần compile sau
sẽ khiến vault mô tả một đồ thị đúng của ngày hôm qua.

### Compile

Compile đọc các ghi chú gần đây và nhờ model đưa ra một loạt trang, rồi **đề xuất** chúng
thay vì ghi thẳng, đúng như cô đọng làm. Đề xuất mang theo mọi trang cùng lúc dưới dạng
JSON, kèm nội dung trước đó của các trang ấy trong `previous_body`, nên hoàn tác vẫn chỉ
một bước. Agent được đánh dấu `autonomous` áp dụng loạt của chính nó ngay. Model không bao
giờ quyết định một trang có được tồn tại mà không có sources hay không; kiểm tra đó chạy
trên câu trả lời trước khi bất cứ thứ gì được đề xuất.

Không có cron riêng. Compile được nối tiếp vào job `memory_consolidate`, vì cả hai đọc cùng
bộ ghi chú và vault nên ổn định từ cùng một lần đọc trong đêm. Nó có run riêng trong
Activity với chi phí riêng, và một lần compile thất bại được ghi log mà không làm hỏng cô
đọng, vì bản viết lại của cô đọng đã ghi xong rồi.

### Lint và hai bảng tổng hợp

Vault xuống cấp một cách âm thầm: một trang mất nguồn cuối cùng trong một lần viết lại, một
liên kết trỏ tới trang không ai viết, một trang ngừng được cập nhật trong khi thứ nó mô tả
vẫn tiếp tục thay đổi. Không cái nào trong số đó gây lỗi và không cái nào nhìn thấy được từ
một trang đơn lẻ, nên lint đọc cả vault một lượt và báo bốn loại: `unsourced`, `dangling`,
`review` (trang nào có status khác `ok`), và `stale` — cũ hơn 90 ngày hoặc không mang ngày
nào cả, vì coi việc thiếu bằng chứng là còn mới chính là cách một vault bắt đầu nói dối.
Không gì bị xoá; một liên kết dangling thường là một trang *nên* tồn tại, khiến nó là việc
cần làm cho lần compile sau chứ không phải một lỗi để dọn đi.

Hai bảng tổng hợp markdown được sinh lại toàn bộ bên cạnh các trang, ở
`memory/wiki/reports/open-questions.md` và `stale.md`. Chúng là tệp vì người đọc chúng có
thể đang ở trong editor nhiều như ở trong web UI, và vì một tệp có thể mở lại vào năm sau.
Sinh lại toàn bộ, vì một bảng tổng hợp tích luỹ sẽ cứ báo những vấn đề đã sửa từ nhiều
tháng trước, và đó là cách một báo cáo không còn được đọc nữa.

### Tool của chính agent

| Tool | Làm gì |
|---|---|
| `wiki_get` | một trang đầy đủ, theo title; title được slug hoá, nên agent không cần biết tên tệp |
| `wiki_search` | tối đa 8 kết quả dạng `[slug] <matching text>`, tìm trên title cùng với thân, vì người tìm một trang gõ tên của sự vật đó |
| `wiki_apply` | upsert một trang: thay phần người viết sở hữu, không bao giờ thay khối máy viết, và từ chối trang không có sources |

`wiki_apply` giữ trang ở đúng thư mục nó đang nằm. Chuyển nó đi khi viết lại sẽ làm hỏng
mọi liên kết từng trỏ về trang cũ.

### Qua HTTP và trong web UI

| Endpoint | Làm gì |
|---|---|
| `GET /api/agents/{id}/memory/wiki?q=` | vault dưới dạng mục lục, bỏ thân; có `q` thì xếp hạng bằng đúng phép tìm `wiki_search` dùng |
| `GET/PUT/DELETE /api/agents/{id}/memory/wiki/pages/{slug}` | một trang đầy đủ; PUT chỉ đổi các trường được gửi, nên một UI chỉ hiện thân không thể âm thầm làm rơi sources mà nó chưa từng hiển thị |
| `GET /api/agents/{id}/memory/wiki/report` | các vấn đề lint và các câu hỏi mở dưới dạng dữ liệu |
| `POST /api/agents/{id}/memory/wiki/compile` | khởi động một lần compile và trả 202; 409 khi một compile hoặc cô đọng đang chạy cho agent đó |

Tab **Wiki** trong màn hình quản lý chính là các endpoint này: vault nhóm theo thư mục, tìm
kiếm, một trang mở kèm thân và sources, sửa và xoá, báo cáo lint, và một lần compile có thể
khởi động không cần chờ job ban đêm.

## Một agent thấy gì của agent khác

Không gì cả, ngoài task được giao. Người dùng nói chuyện với master trên mọi nền tảng (web,
Telegram, cổng HTTP), nên một chủ đề mang từ Pong sang HLV đi bên trong cuộc trò chuyện của
master và tới HLV như một phần của task giao việc. Phạm vi `users/owner/` dùng chung ở trên
là nơi duy nhất một fact do một agent học được được mọi agent đọc.

## Qua HTTP và trong web UI

Mọi thứ agent thấy trong prompt của nó đều sửa được bởi người dùng, nên họ không bao giờ
phải tranh cãi với một trí nhớ mà họ không chạm tới được.

| Endpoint | Làm gì |
|---|---|
| `GET/PUT /api/memory/user` | đọc/ghi `USER.md`, kèm facts và index |
| `PUT/DELETE /api/memory/user/facts/{name}` | upsert hoặc quên một fact; tên không phải slug hoặc type lạ là 422 |
| `GET/PUT /api/agents/{id}/memory` | đọc/ghi `MEMORY.md` của agent đó |
| `GET/PUT /api/agents/{id}/memory/notes/{day}` | đọc/ghi một ghi chú ngày; tên không phải một ngày kèm hậu tố tuỳ chọn là 422 |
| `GET /api/memory/search?q=&agent_id=` | kết quả trên cả hai phạm vi, mỗi kết quả gắn nhãn phạm vi nó đến từ; không có `agent_id` thì kết quả của các agent được xen kẽ theo hạng, nên entry tốt nhất của mỗi agent đứng trước entry thứ hai của bất kỳ agent nào |
| `GET /api/memory/proposals?status=` | mặc định là đang chờ; `status=all` gồm cả đã quyết định |
| `POST /api/memory/proposals/{id}` | `{approve: bool}`; quyết định hai lần là 409 |
| `POST /api/agents/{id}/memory/consolidate` | khởi động một lần viết lại và trả 202; 409 khi đã có một lần đang chạy cho agent đó |

Tab **Ghi nhớ** trong màn hình quản lý (`#/manage/memory`) chính là các endpoint này: sửa
`USER.md`, thêm hoặc quên facts, sửa `MEMORY.md` và ghi chú của từng agent, tìm trên mọi
phạm vi, và duyệt hoặc từ chối điều một job đã đề xuất — đề xuất `agent_memory` hiện những
dòng nó sẽ thêm, và một bản viết lại được hiện đối chiếu với văn bản nó thay thế kèm nút
hoàn tác trong lịch sử. Có thể kích hoạt cô đọng ngay không cần chờ cron.

## So với openclaw

Tên tệp và vai trò khớp với workspace memory của openclaw (`MEMORY.md`,
`memory/YYYY-MM-DD.md`) nên workspace có sẵn dùng lại được. openclaw thêm một chỉ mục vector
và một `memory_search` xếp hạng theo ngữ nghĩa; ở đây tìm kiếm là grep thuần, sắp theo độ
mới của tệp, đủ cho ghi chú của một người dùng và giữ kết quả giải thích được. Việc tỉa bớt
ở đây là job cô đọng ở trên, thứ openclaw không có tương đương: nó đề xuất một bản viết lại
theo lịch và giữ lại cái nó thay thế. Phạm vi người dùng dùng chung cũng không có tương
đương ở openclaw: openclaw giữ một workspace cho mỗi agent, nên một fact về người dùng do
một agent học được ở lại đó.

Wiki lấy hình dạng từ memory-wiki của openclaw — trang dưới `entities`, `concepts` và
`syntheses`, `[[links]]`, một lần compile từ ghi chú ngày — và dừng ở đó. Ba khác biệt là có
chủ đích:

- **Không Obsidian CLI và không cầu nối.** openclaw điều khiển một vault bên ngoài qua
  Obsidian; ở đây vault là tệp thường trong thư mục agent mà cùng `memory_search` và
  `workspace_read` đã chạm tới được. Không phải cài gì, và một vault không có trình đọc nào
  gắn vào vẫn mở được trong bất kỳ editor nào.
- **Không có lớp claim.** openclaw trích từng claim riêng lẻ và theo dõi chúng tách biệt. Ở
  đây trang là đơn vị và `sources` là toàn bộ câu chuyện về nguồn gốc. Một đồ thị claim
  chính xác hơn và cũng nhiều máy móc hơn mức ghi chú của một người đáng để đánh đổi; lint
  bắt được lỗi thực sự xảy ra, tức là một trang mất bằng chứng của nó.
- **Lint và hai bảng tổng hợp của nó** không có tương đương ở openclaw. Chúng tồn tại vì
  vault xuống cấp âm thầm và hư hại chỉ nhìn thấy được khi xem cả vault một lượt.
