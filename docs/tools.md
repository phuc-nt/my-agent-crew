# Tool

**Phiên bản**: 0.11.1 · **Cập nhật**: 2026-10-05

Tool là một hàm mà model có thể gọi trong một lượt. Bộ tool của mỗi agent
được lắp lúc khởi động từ đường dẫn workspace và memory của agent, rồi được định hình bởi
profile của nó: `mode: work` thêm bốn tool, một vision route thêm `image_read`, và danh sách
cho phép `tools` giới hạn kết quả.
System prompt liệt kê tên các tool có sẵn; model thấy JSON schema của từng tool.

## Quy tắc chung

- **Tham số được kiểm tra** theo schema trước khi tool chạy; một lời gọi sai được
  trả về cho model dưới dạng lỗi, không raise.
- **Đầu ra bị giới hạn** trước khi đi vào ngữ cảnh; cách nó được đưa xuống dưới trần được
  đánh dấu. Mặc định là 8 000 ký tự (`tool_output_chars` trong `config.yaml` hoặc
  `MY_AGENT_TOOL_OUTPUT_CHARS`); agent có script in nhiều hơn tự nâng trần của mình bằng
  `tool_output_chars` trong profile mà không bắt phần còn lại của đội trả giá.

  Đầu ra vượt trần được rút ngắn theo một trong ba cách, và thẻ run nói rõ cách nào:

  | Cách | Khi nào | Cái gì còn lại |
  | --- | --- | --- |
  | structure | đầu ra parse được thành JSON | mọi key; mảng mất phần đuôi, chuỗi dài mất phần giữa, và kết quả vẫn parse được |
  | summary | mọi thứ khác đủ dài để tách | phần mở đầu và phần kết giữ nguyên từng chữ, cùng bản tóm tắt phần giữa do model làm, kẹp giữa hai nhãn nói rõ điều đó |
  | cut | mọi thứ còn lại, và bất cứ khi nào tóm tắt thất bại | phần mở đầu, cùng số ký tự đã bỏ |

  Đường structure không bao giờ viết lại con số: số liệu sổ cái và chỉ số sức khoẻ
  đi qua đường này, và một bản tóm tắt làm tròn con số thì tệ hơn một bản bỏ sót một dòng.
  Đường summary hỏi chính các tuyến của agent và được tính vào run và cuộc trò chuyện như mọi
  lời gọi model khác, kể cả khi provider không báo giá (khi đó là một lần gọi giá không rõ);
  sổ cái sử dụng ghi nó dưới mục đích `tool_summary`. Nó là một cải tiến so với cut, không bao giờ là điều kiện tiên quyết cho cut — không có tuyến, tuyến
  hỏng, tuyến chậm hay câu trả lời rỗng đều rơi về cut thuần, và tool
  vẫn trả lời dù thế nào.

  Đây là lý do nâng trần vẫn là câu trả lời đúng cho một loại tệp: một tài liệu dài
  mà agent phải chép ra từ đó, chẳng hạn một ghi chú schema chứa tên cột chính xác và
  câu SQL mà một job lịch chạy. Rút ngắn nó đi theo đường summary, và tóm tắt viết lại
  phần giữa — là chỗ câu query thường nằm. Một tên cột bị diễn giải lại là một query
  thất bại. Giữ trần cao hơn kích thước của tài liệu như vậy thay vì tin vào bản tóm tắt
  của nó. JSON không gặp vấn đề này, vì đường structure không bao giờ hỏi model điều gì.
- **Lỗi được báo thật.** Lỗi của chính tool được trả về cho model dưới dạng "Công cụ lỗi: …";
  mọi exception khác được ghi log kèm traceback và trả về theo tên kiểu. Khung prompt
  bảo model báo cáo tool thất bại thay vì giả vờ.
- **Duyệt.** Tool cần duyệt sẽ tạm dừng lượt bằng một sự kiện `approval_required`
  và một `Approval` được lưu. Web UI hiện một thanh, Telegram hiện `/approve` /
  `/deny`; quyết định tiếp tục đúng lượt đó. Cuộc trò chuyện (hoặc agent) đánh dấu
  `autonomous` bỏ qua bước dừng — trừ lệnh `shell_run` khớp
  `settings.shell_ask_patterns` (xem [Shell](#shell)), lệnh này vẫn hỏi và nói rõ
  pattern nào khớp. Chiều ngược lại cũng đúng: cuộc trò chuyện *không* autonomous vẫn
  chạy lệnh `shell_run` khớp `settings.shell_allow_patterns` mà không hỏi, để
  agent được giám sát vẫn làm được phần việc thường ngày của mình. Danh sách hỏi được kiểm tra
  trước, nên nêu một lệnh ở cả hai danh sách nghĩa là nó hỏi. Từ chối cứng, thoát khỏi workspace và đích mạng riêng, không
  thể duyệt. Yêu cầu không ai trả lời trong `approval_ttl_seconds` (mặc định 600; lịch và
  khối `telegram` đặt được hạn riêng, xem [agents.md](agents.md#lịch)) bị từ chối: kết quả
  tool nói hành động không chạy và chưa có gì thay đổi, dặn không làm lại hay làm một việc
  tương đương bằng tool khác mà nói với người việc gì đang chờ duyệt; lượt tiếp tục và câu trả
  lời được gửi như thường.
  Duyệt bằng `always` đưa tool vào danh sách `auto_approve` của cuộc trò chuyện, nên các
  lời gọi sau trong cuộc trò chuyện đó chạy không hỏi; rào danh sách hỏi vẫn áp dụng.
- **Nội dung là dữ liệu.** Khung prompt bảo model rằng bất cứ thứ gì tool trả về là dữ liệu,
  không bao giờ là chỉ thị.

## Các tool

| Tool | Duyệt | Giới hạn | Việc nó làm |
|---|---|---|---|
| `workspace_list` | không | — | liệt kê một thư mục trong workspace |
| `workspace_read` | không | chỉ trần đầu ra của agent (`tool_output_chars`), có đánh dấu chỗ cắt | đọc một tệp văn bản trong workspace; `offset` (dòng, tính từ 1) và `limit` đọc một cửa sổ thay vì cả tệp |
| `workspace_write` | **có** | — | ghi một tệp văn bản trong workspace, tạo thư mục cha; chỉ dưới `write_paths` nếu profile đặt khoá này |
| `fetch_url` | không | 20 000 ký tự qua markdown của firecrawl, nếu không thì 6 000; kết nối 5 s, mỗi lần đọc 10 s, đọc tối đa 512 KB rồi đóng; không theo redirect | GET một trang http(s) công khai; firecrawl trả về markdown, nếu không thì HTML được rút thành văn bản |
| `web_search` | không | 5 kết quả | luôn có sẵn; các backend được thử theo thứ tự firecrawl → brave → tavily → duckduckgo; trả về tiêu đề, URL, đoạn trích |
| `memory_save` | không | — | nối `- HH:MM text` vào ghi chú hôm nay, xem [memory.md](memory.md) |
| `memory_search` | không | 12 kết quả | tìm trong facts người dùng dùng chung, rồi `MEMORY.md` và mọi ghi chú ngày, mới nhất trước; mọi từ khoá đều phải khớp |
| `conversation_search` | không | 20 kết quả, tối đa 3 mỗi hội thoại | tìm trong lời đã nói ở các hội thoại khác (FTS5, gõ không dấu vẫn khớp có dấu); agent thường chỉ tìm hội thoại của chính mình, master tìm được của một agent bất kỳ hoặc cả đội; hội thoại đang chạy không tính |
| `user_memory_save` | không | — | ghi nhớ một điều về người dùng, cả đội dùng chung, xem [memory.md](memory.md) |
| `user_memory_forget` | không | — | bỏ một fact đã nhớ theo tên |
| `wiki_get` | không | — | một trang wiki đầy đủ, tra theo tiêu đề, xem [memory.md](memory.md#vault-wiki) |
| `wiki_search` | không | 8 kết quả | tìm trong tiêu đề và nội dung của vault, khớp nhất trước, dạng `[slug] text` |
| `wiki_apply` | không | — | ghi hoặc cập nhật một trang; từ chối trang không có `sources`, và không bao giờ chạm vào khối link do compile sở hữu |
| `shell_run` | **có** | mặc định 120 s, tối đa 900 s | chạy một lệnh trong workspace, trả về stdout+stderr |
| `schedule_create` | **có, luôn luôn** | tối đa 20 lịch mỗi agent, prompt ≤ 2000 ký tự | đề xuất một lịch chạy lặp lại; luôn dừng chờ người duyệt, xem [Đề xuất lịch chạy](#đề-xuất-lịch-chạy) |
| `skill_read` | không | — | trả về toàn văn một skill theo tên, mở đầu bằng cảnh báo khi skill cần một lệnh máy này không có, xem [agents.md](agents.md#skill) |
| `image_read` | không | 8 MB; jpg, png, webp, gif | gửi một ảnh từ workspace hoặc home của đội (nơi `inbox/` giữ những gì Telegram chuyển tới) vào chuỗi `vision_routes` kèm một `question` và trả về câu trả lời, xem [Ảnh](#ảnh); chỉ có khi đã cấu hình vision route |
| `pdf_read` | không | 50 trang, `pages` chọn một cửa sổ; áp dụng trần đầu ra của agent | đọc một PDF từ workspace hoặc home của đội; trang có chữ sắp sẵn trả về dạng văn bản, trang scan đi qua chuỗi vision, xem [PDF](#pdf) |
| `ask_user` | **có, luôn luôn** | một câu hỏi mở mỗi cuộc trò chuyện | hỏi người dùng một điều và tạm dừng lượt cho tới khi họ trả lời, xem [Hỏi người dùng](#hỏi-người-dùng) |
| `tool_output_read` | không | mỗi lần đọc vừa trần đầu ra của agent, `offset` và `limit` tính bằng ký tự | đọc lại toàn văn một kết quả tool đã bị rút ngắn theo id lời gọi, xem [Đọc lại đầu ra dài](#đọc-lại-đầu-ra-dài) |
| `progress_note` | không | 200 ký tự | nói trong một dòng agent sắp làm gì; trở thành một step `note` trên run, xem [Nói mình đang làm gì](#nói-mình-đang-làm-gì) |
| `artifact_create` | không | năm loại chữ (`markdown`, `code`, `html`, `svg`, `mermaid`), trần theo loại; 30 canvas mới mỗi lượt | tạo một canvas cạnh khung chat từ `title`, `kind`, `content` và `language` tuỳ chọn; kết quả mở đầu bằng thẻ `[artifact <id> v1]` và không trả lại nội dung, xem [Canvas](#canvas) |
| `artifact_list` | không | 30 canvas | liệt kê các canvas agent với tới, mới sửa trước, đánh dấu canvas chưa đọc hay có bản mới; `query` lọc theo tiêu đề, không phân biệt hoa thường và dấu |
| `artifact_read` | không | mỗi trang vừa trần đầu ra của agent | đọc một canvas theo trang, chữ nguyên văn; chân trang là lệnh đọc tiếp đúng bản đó |
| `artifact_edit` | không | 30 bản mỗi canvas mỗi lượt; diff 1 500 ký tự | thay một đoạn `old` chép nguyên văn bằng `new`; kết quả có diff của phần đã đổi và cỡ mới của canvas |
| `artifact_rewrite` | không | như `artifact_edit`; diff xung đột 4 000 ký tự | viết lại cả canvas khi bản mới nhất là bản agent đã thấy trọn; nếu không thì từ chối kèm diff của phần người khác đã đổi |
| `artifact_import` | không | tệp thường trong workspace, vừa trần của loại; tính chung ngân sách ghi của lượt | đưa một tệp trong workspace vào canvas mới, hoặc vào canvas đã có khi nêu `id`; loại đoán theo đuôi tệp, đuôi lạ thì phải nêu `kind`; tệp không đổi thì không thêm phiên bản. Là đường duy nhất tạo canvas ảnh |
| `artifact_export` | **có** | chỉ dưới `write_paths` nếu profile đặt khoá này | ghi một phiên bản của canvas ra một tệp trong workspace; ghi đè tệp đã có và nói rõ điều đó, từ chối thư mục và symlink |

Bốn tool nữa chỉ đi kèm `mode: work`, vì trợ lý chỉ trò chuyện không cần
chúng và mỗi spec tool thêm vào đều tốn token prompt:

| Tool | Duyệt | Giới hạn | Việc nó làm |
|---|---|---|---|
| `workspace_edit` | **có** | hiện 40 dòng diff | thay một đoạn chính xác trong một tệp; từ chối khi đoạn không có hoặc khớp nhiều hơn một lần, trừ khi `replace_all` |
| `workspace_grep` | không | 200 kết quả, 30 s | tìm regex trên workspace; dùng `rg` khi đã cài, nếu không tự duyệt cây. Bỏ qua `.git`, `.venv`, `node_modules`, `__pycache__`, `dist`, `build` và tệp nhị phân |
| `workspace_glob` | không | 500 đường dẫn | liệt kê tệp khớp một glob, cùng danh sách bỏ qua |
| `delegate` | không | 8 mỗi cuộc trò chuyện, 8 cùng lúc | giao trọn một việc cho agent khác và chờ câu trả lời, xem bên dưới |

### Đọc lại đầu ra dài

Đầu ra vượt trần bị rút ngắn trước khi vào ngữ cảnh, nhưng bản gốc không mất: registry ghi nó
vào `<home>/spill/<conversation>/<sha256(call id)[:32]>.txt` (tối đa 5 MB) rồi nối vào cuối
bản rút ngắn một dòng nêu số ký tự và id lời gọi. `tool_output_read` (`id`, `offset`, `limit`,
đều tính bằng ký tự) trả bản gốc theo từng đoạn; mỗi đoạn có dòng đầu ghi nguồn và khoảng đã
đọc, và dòng cuối nêu `offset` tiếp theo hoặc báo đã hết. Đoạn luôn vừa trần đầu ra, vì chính
đầu ra của tool này không bao giờ bị ghi ra tệp.

- **Chỉ trong cuộc trò chuyện hiện tại**, kể cả với master: id do model gõ nên không được
  quyết định đọc dữ liệu của ai. Id không có, hoặc trùng giữa hai kết quả, bị từ chối thay vì
  đoán. Tệp còn thì đọc tệp; hết tệp thì đọc bản đã lưu trong DB và gắn nhãn "có thể đã rút
  ngắn".
- **Agent nào có.** Tool nằm trong mọi agent không có danh sách `tools:`; agent có danh sách
  phải ghi `tool_output_read` thì mới có tool, tệp spill và dòng trỏ. Agent không ghi thì hành
  xử y như trước. Template kongming và researcher đã ghi sẵn. Với agent đang chạy thật, thêm
  tên này vào `tools:` là việc của người giữ home của agent đó.
- **Dọn dẹp.** Xoá cuộc trò chuyện xoá luôn thư mục spill của nó; fork sao chép thư mục sang
  id của fork để fork vẫn đọc được bản gốc khi nguồn đã bị xoá; một vòng quét mỗi ngày (chạy
  khi khởi động rồi mỗi 24 giờ, cùng lúc scheduler) xoá tệp cũ hơn 7 ngày và không theo symlink.
- **Khi prompt bị lược.** Kết quả cũ bị thay bằng một dòng stub; với agent có tool này, stub nêu
  id để đọc lại thay vì bảo gọi lại tool.

### Giao việc

`delegate` mở một cuộc trò chuyện mới cho agent nêu trong `agent` — một trong các
`delegates` của bên gọi, hoặc chính nó — chạy việc ở đó, và trả về câu trả lời cuối của cuộc trò chuyện đó
kèm hai dòng đầu: dòng một ghi id, trạng thái run, chi phí và số step; dòng hai (`outcome=`) ghi
việc được giao đi tới đâu. Dưới hai dòng đó là khối canvas con đã viết, rồi một dòng trống luôn có,
rồi mới tới lời của con (xem đoạn "Khối canvas" bên dưới). Agent con bắt đầu trống: nó
không bao giờ thấy lịch sử của cha, và đó là mục đích, nên `task` phải mang theo mọi thứ nó
cần: ý định của người dùng (lời nguyên văn, ngày hôm nay), không phải cách làm. Mô tả của
tool và danh sách đội trong prompt của master nói rõ điều này, và danh sách đội không nêu
workspace của từng agent, vì master biết agent khác lưu tệp ở đâu thì bắt đầu chỉ tệp để ghi
và bịa ra những tệp nó không biết. Phía nhận, prompt của agent con có mục "Việc được giao":
task do agent điều phối viết chứ không phải người dùng, hướng dẫn và quy ước workspace của
agent con thắng mọi gợi ý về chỗ lưu, và một đường dẫn chưa có không phải lý do để tạo tệp.
Task cũng không cấp quyền: câu hỏi của người dùng ("được không?") được giao để hỏi rồi trả
lời, chưa làm; tạo bảng, sửa schema, sửa code hay cấu hình chỉ khi người dùng đồng ý rõ. Mô tả
tool, danh sách đội, mục "Việc được giao" và skill luôn bật `delegation` cùng nói một hợp đồng —
phần chia việc theo tệp của skill chỉ áp cho việc lập trình.
Agent con gặp việc cần người dùng đồng ý thì dừng, nói cần làm gì và vì sao, kết thúc
`Status: BLOCKED`; master kể lại và hỏi người dùng, không tự làm thay, không giao cho agent khác.
Trạng thái run chỉ nói run kết thúc ra sao: con trả lời "không làm được vì thiếu quyền" vẫn kết
thúc run là `done`. Dòng `outcome=` nói việc được giao ra sao, xét theo thứ tự. Run lỗi, dừng
(`budget`, `max_steps`, `loop`) hay hết thời gian chờ là `failed`. Approval tool quyết định gần nhất
của con bị từ chối hay hết hạn là `blocked`. Câu hỏi `ask_user` không bao giờ tính: không ai trả
lời thì con làm tiếp với mặc định của nó, còn trả lời sau một tool bị từ chối thì không xoá được lần
từ chối đó. Còn lại theo dòng `Status:` cuối cùng con viết (`done`, `done_with_concerns`, `blocked`,
`needs_context`), đọc theo mọi kiểu model hay viết: khoá in đậm, tiêu đề hay gạch đầu dòng phía
trước, giá trị có dấu cách hay gạch nối thay gạch dưới, trong backtick hay sau một emoji; dòng không
kèm lý do thì lý do lấy từ dòng `Summary:` ngay sau. Dòng `Status:` trong khối code là thứ con đang
cho xem (bảng việc, phiếu, bản nháp), nên chỉ tính khi ngoài khối code không có dòng nào, và chỉ khi
giá trị viết hoa như skill dạy. Con không khai gì là `done` như trước. Khác
`done` thì dòng có thêm `reason=`, và mô tả tool dặn bên giao nói thẳng với người dùng là việc chưa
xong và vì sao, không tóm thành đã xong. Hết thời gian chờ thì tool báo lỗi nhưng vẫn giữ dòng một,
để thẻ giao việc trên web còn chỉ được tới cuộc trò chuyện của con; thẻ hiện outcome bằng chữ, và
lý do ngay bên cạnh, cũng bằng chữ: `loop`, `timeout` hay `workspace_write denied` là mã cho model
của bên giao đọc, trên thẻ thành câu. Thời gian chờ là hạn duyệt của chính cuộc trò chuyện con cộng năm phút: con
chép hạn của cha lúc mở, không có thì theo `approval_ttl_seconds` của agent con, nên bên giao
không bỏ cuộc trong khi yêu cầu duyệt của con còn đang chờ người.
Người dùng kể một dữ kiện thuộc lĩnh vực của agent nào (ăn uống, bia rượu, chi tiêu, giấy tờ)
hay bảo lưu lại thì master giao agent đó ghi vào sổ của nó, không ghi vào memory thay; hỏi vì
sao trong lĩnh vực đó thì giao lại kèm dữ kiện mới, không tự suy luận.
Con dừng giữa chừng (`halted`, `error`, bị ngắt) thì kết quả ghi rõ là chưa xong và liệt kê
các tool call đã thành công của nó, để bên giao không làm lại hay giao lại với quyền rộng hơn.
Khối canvas đứng ngay dưới dòng `outcome=`: mỗi canvas agent con đã viết trong cuộc trò chuyện của
nó một dòng `[artifact <id> v<n>] <tiêu đề>`, theo thứ tự viết lần đầu, `v<n>` là phiên bản lớn
nhất con viết ở đó. Thẻ là đúng thẻ mà kết quả của tool canvas mở đầu; tiêu đề cắt ở 160 ký tự như
mọi trường trích trong kết quả. Canvas đã xoá, canvas con chỉ đọc, chỉ xuất ra tệp hay nhập lại mà
không đổi thì không có dòng. Nêu tối đa 12 canvas viết trước nhất; nhiều hơn thì phần thân mở đầu
bằng `(+N canvas khác, xem bằng artifact_list)`. Sau khối là một dòng trống luôn có, kể cả khi con
không viết canvas nào: chỉ những dòng trên dòng trống đó là canvas, nên câu trả lời của con mở đầu
bằng một dòng trông như thẻ vẫn là câu trả lời. Khối có ở mọi outcome, cả khi hết thời gian chờ
(những gì con đã viết tới lúc đó) lẫn khi con dừng giữa chừng (đứng trên ghi chú chưa xong). Câu
trả lời chuyển thẳng cho người dùng không mang khối này, vẫn đúng là lời của con. Tiêu đề là chữ
của con, nên mô tả tool dặn bên giao coi nó là dữ liệu chứ không phải chỉ dẫn, và nhắc tên canvas
cho người dùng thay vì đọc rồi chép nội dung vào câu trả lời. Được nêu tên chưa phải là đã đọc:
lượt kế của cuộc gốc vẫn nhận ghi chú canvas mới, và `artifact_rewrite` của master vẫn bị từ chối
cho tới khi nó đọc canvas. Web đọc khối bằng cùng dạng dòng; kết quả lưu
từ trước khi có dòng trống thì đọc như cũ, không có canvas nào.
Ngữ cảnh của cha chỉ lớn thêm một kết quả tool thay vì cả công việc, và
kết quả đó không bao giờ bị cắt gọn bởi cơ chế tỉa đầu ra tool cũ: master hỏi Pong,
rồi hỏi HLV, rồi quay lại chủ đề của Pong
vẫn còn nguyên câu trả lời của Pong.

Nhiều lời gọi `delegate` trong cùng một message của assistant chạy cùng lúc; mọi tool khác
vẫn chạy từng cái một, vì chúng chạm vào workspace và sẽ tranh chấp.

Mọi agent `mode: work` đều có `delegate` trừ khi nó khai một danh sách cho phép `tools` bỏ
tool này ra. Danh sách cho phép giới hạn những gì agent nhận, và giới hạn đó bao gồm cả tool này, nên
một chuyên gia vẫn là chuyên gia thay vì lặng lẽ thành người dẫn dắt.

Độ sâu dừng ở một. Agent được giao việc nhận hộp tool không có `delegate` trong đó, và
tool từ chối chạy khi lượt nó đang ở trong đã là một lượt được giao — hai rào,
vì một fan-out xổng ra tiêu tiền thật. Con thừa kế lập trường duyệt của cha
và phần ngân sách còn lại của cha, và những gì con tiêu được cộng vào
cha lúc kết quả giao việc được ghi, nên trần vẫn đúng nghĩa của nó và một lần giao việc được gọi
lại sau khi server khởi động lại không tính con hai lần. Lượt bị ngắt giữa chừng khi đang giao việc tìm lại
con của nó qua id của tool call thay vì mở một con thứ hai.

### Tool workspace

Đường dẫn được phân giải bên trong workspace: `..` và đường dẫn tuyệt đối
thoát ra ngoài bị từ chối, symlink ở lại bên trong được đi theo. Workspace là
`agent.yaml: workspace`, mặc định `<agent dir>/workspace`. Không gì bên ngoài nó chạm tới được
qua các tool này; `shell_run` là lối thoát, và nó cần duyệt.

`write_paths` thu hẹp thêm chỗ `workspace_write`, `workspace_edit` và `artifact_export` được ghi. Cuộc trò
chuyện autonomous (và mọi cuộc được giao việc từ một master autonomous) không dừng để duyệt,
nên với một workspace là repo git, đây là rào duy nhất giữa một đường dẫn đoán sai và một
thư mục dữ liệu cá nhân mới nằm ngoài `.gitignore`. Đường dẫn so theo dạng chữ, nên
`data/../x` là `x` và bị từ chối.

### Trí nhớ người dùng dùng chung

`user_memory_save` và `user_memory_forget` ghi vào `<home>/users/owner/`, mỗi fact một tệp
dưới `facts/` cùng một `INDEX.md` được tạo lại. Thư mục đó giống nhau cho mọi
agent, nên điều một agent học được về người dùng, cả đội thấy ở lượt kế tiếp.

Ghi có được thực hiện ngay hay không tuỳ ai yêu cầu. Trong lượt chat hoặc Telegram
người dùng đang ở đó và có thể phản đối, nên fact được ghi ngay. Trong job lịch
không ai theo dõi, nên cùng lời gọi đó trở thành một dòng trong `memory_proposals` với trạng thái
`pending`, và không gì được ghi cho tới khi có người duyệt — agent chạy không người trông không thể
tự viết lại hồ sơ của người dùng. Lượt tiếp tục sau khi duyệt giữ nguyên
nguồn của lượt đã dừng, nên duyệt một tool trên web không biến job thành
chat.

Tên là slug (`a-z`, `0-9`, `-`, tối đa 60 ký tự); lưu lại cùng tên
sẽ cập nhật fact đó thay vì thêm cái thứ hai. `type` là một trong `profile`,
`preference`, `feedback`, `project`, `reference`.

Phía per-agent không có tool quên tương ứng: `MEMORY.md` được viết lại có chủ đích, bởi
người dùng hoặc bởi job consolidate trong [memory.md](memory.md), không bao giờ bị bỏ từng dòng
bởi một tool call.

### Tool web

`fetch_url` phân giải host trước và từ chối địa chỉ riêng, loopback, link-local, dành riêng
và multicast; nó không theo redirect, nên URL công khai nảy sang một
địa chỉ nội bộ sẽ thất bại an toàn. Chỉ `http` và `https`. Rào địa chỉ chạy trước mọi
request, kể cả request tới firecrawl, nên URL riêng không bao giờ tới được scraper.

Khi đặt `FIRECRAWL_BASE_URL`, `fetch_url` nhờ firecrawl lấy nội dung chính dạng markdown
và giữ 20 000 ký tự của nó; tiêu đề và danh sách còn nguyên, điều mà văn bản thô đã lột mất.
Firecrawl bị sập, chậm hay trả markdown rỗng không phải lỗi — tool rơi về văn bản thuần.

Tool không trả kết quả rỗng. Máy chủ trả 202 (đã nhận, chưa có kết quả) là lỗi "chưa có kết quả để
đọc", vì thân đi kèm không phải trang. Trang không còn chữ nào sau khi rút (thân rỗng, hoặc chỉ
dựng bằng JavaScript) cũng là lỗi nói đúng điều đó: một chuỗi rỗng model đọc thành "trang không
nói gì" và kể lại như một dữ kiện. `shell_run` cũng vậy: lệnh xong mà không in gì trả về một ghi
chú nói thế, lệnh hỏng mà không in gì vẫn có dòng mã thoát.

`web_search` thử các backend theo thứ tự và dừng ở cái đầu tiên có kết quả:
firecrawl, rồi Brave, rồi Tavily, rồi DuckDuckGo. DuckDuckGo không cần khoá và đóng
danh sách, nên tool tồn tại trên mọi máy và agent liệt kê nó trong `tools:` luôn
dùng được. Backend thất bại được ghi log và bỏ qua; chỉ khi mọi backend đều thất bại
tool mới báo dịch vụ tìm kiếm không tới được, nhờ đó "không có kết quả" và
"tìm kiếm hỏng" là hai câu trả lời tách biệt. `FIRECRAWL_API_KEY` là tuỳ chọn và chỉ gửi khi
được đặt, nên host tự dựng không cần khoá và một base url gõ sai không thể làm lộ khoá.

### Shell

`shell_run` chạy trong workspace của agent với môi trường tối thiểu (`PATH`, `HOME`,
`LANG`, `LC_ALL`, `TERM`, `TMPDIR`, `USER`, `SHELL`), nên model không bao giờ thấy khoá
API của server. Timeout lấy từ tham số `timeout_s`, trần 900 s. Exit khác không là
lỗi tool mang theo 4 000 ký tự đầu ra cuối cùng. Job lịch dạng `command` dùng
cùng tool này và ghi một step duy nhất.

Danh sách cho phép là lý do một script chạy được trong terminal của bạn vẫn có thể thất bại ở đây:
bất cứ thứ gì bạn export, hoặc đặt trong tệp env của server, đã mất khi lệnh
chạy. Script cần một giá trị không bí mật nên tự đọc nó từ tệp thay vì
trông đợi nó trong môi trường, và script cần bí mật thật nên đọc nó từ
tệp chỉ mình nó đọc được. Nới rộng danh sách cho phép là cách sửa sai — nó sẽ trao khoá API của server
cho mọi lệnh do model viết.

`autonomous` nếu không sẽ để mọi lệnh chạy không ai trông, quá nhiều với
những dạng lệnh không thể hoàn tác. Nên `shell_ask_patterns` liệt kê các mảnh lệnh luôn phải
duyệt bất kể — mặc định là `rm -rf`, `rm -r `, `sudo `, `| sh`, `| bash`, `mkfs`,
`git push --force`, `git reset --hard`, `> /dev/`, `chmod -R` và `launchctl`. So khớp là
kiểm tra chuỗi con không phân biệt hoa thường và yêu cầu duyệt nêu tên pattern đã khớp, ở
thanh web, thông báo Telegram và thẻ run. Đặt danh sách trong `config.yaml`, theo từng agent trong
`agent.yaml`, hoặc qua `MY_AGENT_SHELL_ASK_PATTERNS` (phân cách bằng `;`); khai báo nó
thay thế mặc định và danh sách rỗng tắt rào.

`shell_deny_patterns` (chỉ theo từng agent) so khớp cùng kiểu nhưng từ chối thẳng, không hỏi
duyệt — cuộc được giao hay job lịch có thể không có ai để duyệt. Lời từ chối dặn model dừng lại,
nói cần làm gì và vì sao để người dùng quyết, thay vì tìm đường khác.

Đây là rào mềm thứ hai, không phải sandbox: `rm  -rf` với hai dấu cách, hoặc cùng lệnh
đó dựng bên trong `$(…)`, đi thẳng qua nó. Nó bắt lỗi hiển nhiên, không bắt
kẻ cố tình.

Ranh giới thật là sandbox, bật khi profile đặt `shell_network: false` hoặc `shell_write_paths`.
Mọi lệnh `shell_run` của agent đó khi ấy chạy dưới `sandbox-exec` của macOS với một profile do
harness dựng. Chỉ có `shell_write_paths` thì còn mạng, còn lại như dưới: agent lấy và ghi dữ
liệu được nhưng không sửa được code, script hay cấu hình quanh nó; lần ghi bị chặn trả kèm lời
dặn báo lại như trên. Với `shell_network: false`, chỉ chặn socket thì không giữ được dữ liệu ở
lại máy, nên profile đóng từng đường mà một lệnh có thể dùng thay thế:

- **Mạng, cả hai chiều.** Không kết nối ra ngoài: không ra internet, không tới `127.0.0.1`
  (API của chính đội ở đó), và không tới resolver, vì tra một tên host
  bịa ra cũng mang dữ liệu ra ngoài như một request. Cũng không lắng nghe, vì một
  server để lại sẽ trao tệp cho bất kỳ ai kết nối.
- **Trợ thủ làm thay lệnh.** `open`, `launchctl`, `osascript`, `shortcuts` và
  `pbcopy` bị cấm, cùng các dịch vụ LaunchServices và pasteboard đằng sau chúng.
  `open <url>` nếu không sẽ để trình duyệt, vốn không bị sandbox, thực hiện request.
- **Ghi, trừ nơi profile cho phép.** Một lần ghi tệp là một lệnh bị trì hoãn: một dòng thêm vào
  script mà job lịch chạy, một git hook, `~/.zshrc` hay một LaunchAgent sẽ chạy sau,
  ngoài sandbox và có mạng. Lệnh chỉ được ghi dưới
  `shell_write_paths` (đường dẫn trong workspace) và các thư mục tạm. Danh sách rỗng
  làm workspace chỉ đọc đối với shell.

Đọc tệp và chạy chương trình cục bộ vẫn hoạt động, nên script của chính agent vẫn chạy. Hệ điều hành
thực thi toàn bộ điều này, nên `$(…)` hay script model vừa viết cũng không đi xa hơn
một lệnh `curl` thường. Nó dành cho agent mà dữ liệu không được rời khỏi máy, chẳng hạn agent
giữ tài chính cá nhân. Nó không bao phủ những gì agent tự nói ra: câu trả lời của nó đi tới
provider model và tới bất kỳ ai nó trả lời, nên agent giao việc có mạng vẫn
thấy chúng. Nơi `/usr/bin/sandbox-exec` không tồn tại (mọi thứ ngoài macOS) lệnh
bị từ chối thay vì chạy không sandbox. Job lịch dạng `command` gọi shell
trực tiếp và giữ mạng: những dòng đó do người viết, và lấy giá cần mạng. Đó
là lý do quy tắc ghi quan trọng. `sandbox-exec` được đánh dấu deprecated trong man page nhưng
vẫn đi kèm macOS; các test chứng minh việc chặn chạy ở bất cứ đâu nó tồn tại.
Chương trình giữ cache trong thư mục nhà (matplotlib ở `~/.matplotlib`) không ghi được cache
đó trong sandbox và dựng lại mỗi lần chạy (matplotlib mất ~9 giây); trỏ biến cache của nó vào
thư mục tạm trong lệnh, ví dụ `MPLCONFIGDIR=/tmp/<agent>-mpl`.

`shell_allow_patterns` là hình ảnh phản chiếu, và mặc định rỗng. Nó nêu các
dạng lệnh đủ thường ngày để chạy không hỏi *ngay cả khi cuộc trò chuyện không
autonomous*, chính là thứ cho phép agent được giám sát chạy test của mình hay đọc git
status của mình mà không phải dừng cho từng lệnh. So khớp là cùng kiểm tra chuỗi con không phân biệt hoa thường,
và nó được đặt theo cùng ba cách, với `MY_AGENT_SHELL_ALLOW_PATTERNS` là biến môi trường.

Thứ tự giữa hai danh sách là cố định: câu hỏi luôn hỏi, rồi danh sách hỏi, rồi
danh sách cho phép, rồi autonomy. Nêu một lệnh ở cả hai nghĩa là nó hỏi, vì người
gọi `rm -rf` là nguy hiểm và `git` là thường ngày muốn `git reset --hard` phải dừng.

Pattern dưới hai ký tự bị bỏ, cũng như những cái trông giống wildcard mà
không phải (`*`, `.*`, `.`, `-`, `--`, `/`, `&&`, `||`, `;`, `|`). So khớp chuỗi con khiến `.*`
chỉ cho phép đúng chuỗi `.*` trong khi người viết nó đọc thành "cho phép tất cả", và
hiểu lầm đó là mối nguy. Mục sai bị bỏ thay vì từ chối cả danh sách,
nên một lỗi gõ không thể đánh bật agent khỏi hoạt động; bỏ đi là thất bại an toàn, vì khi đó lệnh
sẽ hỏi.

Vì phép kiểm tra là chuỗi con chứ không phải parse, một pattern hữu ích nêu *dạng của
thao tác*, không bao giờ nêu chương trình. Một công cụ dòng lệnh vừa đọc vừa ghi — một mail
client, một spreadsheet client, bất cứ thứ gì có subcommand — là một binary làm hai việc rất
khác nhau, và đặt tên binary vào `shell_ask_patterns` chặn cả các lần đọc.
Agent có job lịch chỉ đọc khi ấy dừng mỗi sáng chờ một
lượt duyệt không ai định yêu cầu. Thay vào đó liệt kê các subcommand hoặc cờ thực hiện ghi, mỗi
mục một dòng, và kiểm tra kết quả theo cách duy nhất chứng minh được điều gì: chạy các lệnh đọc
thật và các lệnh ghi thật qua `ask_reason` rồi đếm.

### Media và tệp

Dòng `MEDIA:<path relative to the workspace>` của assistant không phải tool; nó là
quy ước mà khung prompt dạy. Web UI hiển thị nó qua
`GET /api/agents/{id}/files?path=`, chỉ phục vụ tệp bên trong workspace và phục vụ như nội dung
không tin cậy ([design.md](design.md#tool-shell-và-tệp-của-agent)); Telegram biến nó thành
`sendPhoto`.

`FILE:<path>` là anh em của nó dành cho tài liệu, vì Telegram xử lý hai loại khác nhau: ảnh
được mã hoá lại, đúng với biểu đồ nhưng phá hỏng CSV. Dòng `FILE:` tới
dưới dạng `sendDocument`, giữ nguyên byte và tên tệp; web hiện link tải xuống
thay vì ảnh nhúng. Ngoại lệ trên Telegram: dòng `FILE:` trỏ vào một ảnh (`png`, `jpg`, `jpeg`,
`webp`) đi bằng `sendPhoto` như một dòng `MEDIA:`, vì từ chối nó chỉ vì sai tiền tố để người
nhận không có gì. `svg` không thuộc nhóm này: nó là mã đánh dấu, không phải ảnh.

Tài liệu bị giới hạn 20 MB và phải là một trong `pdf`, `csv`, `md`, `txt`, `xlsx`, `json`
hoặc `zip`. Danh sách là rào trên câu trả lời, không phải trên workspace: agent có thể ghi
bất cứ thứ gì vào thư mục của mình, nên chỉ nhốt trong workspace vẫn để một câu gửi đi
một tệp khoá hay một `.env` mà bước trước đã chép vào. Đường dẫn ngoài workspace, tệp không
có, sai định dạng hay quá cỡ được báo vào chat thay vì raise — phần
văn bản đã được gửi đi rồi, nên một exception sẽ để lại câu trả lời hứa có tệp
mà không một lời về lý do không có tệp nào tới.

### Ảnh

Model chat trên `routes` của agent không được kỳ vọng nhìn thấy ảnh, nên `image_read`
gửi tệp xuống một chuỗi riêng: `vision_routes` trong `config.yaml` hoặc
`MY_AGENT_VISION_ROUTES`, mặc định là hai model vision rẻ của OpenRouter
(`google/gemini-2.5-flash-lite`, rồi `qwen/qwen3-vl-8b-instruct`). Giá trị rỗng tắt
tool cho mọi agent; tuyến mà provider không có khoá bị bỏ qua kèm cảnh báo.

Đường dẫn được phân giải theo workspace của agent trước, rồi tới home của đội, nên
`workspace/inbox/<file>` của master nơi ảnh Telegram rơi vào đọc được bởi master
và bởi agent mà nó giao việc. `question` là điều model vision được hỏi;
không có thì nó mô tả ảnh. Mọi agent đều có tool này ở mọi mode, và
danh sách cho phép `tools` của agent có thể nêu nó mà không bị cảnh báo khi không có vision route.
Chi phí của lời gọi được cộng vào run và cuộc trò chuyện như một completion, và sổ cái sử
dụng ghi nó dưới mục đích `image`; dòng của tool trên dòng thời gian run hiện giá đó.

Master đọc một lần để quyết định ảnh dành cho ai và chuyển đường dẫn tuyệt đối
trong task; chuyên gia đọc lại với câu hỏi của riêng mình. Cách đó rẻ hơn một
mô tả dài đi qua ngữ cảnh của master, và chuyên gia được hỏi
đúng các trường nó cần thay vì những gì master đoán.

### PDF

`pdf_read` phân giải đường dẫn giống `image_read`: workspace của agent trước,
rồi home của đội, nên tài liệu Telegram thả vào `workspace/inbox/` đọc được bởi
master và bởi bất kỳ ai nó giao việc.

Một PDF chứa hai loại trang khác nhau và tool xử lý chúng khác nhau. Trang có chữ sắp sẵn
đã chứa văn bản, và pypdf trao nó miễn phí. Trang chụp ảnh
chỉ chứa một bức hình, nên trang đó được render bằng pypdfium2 và gửi xuống cùng
chuỗi `vision_routes` mà `image_read` dùng, từng trang một và chỉ với những trang
cần. Nên tài liệu trộn tốn một lời gọi model mỗi trang scan và không tốn gì cho phần còn lại.
Các lời gọi đó được cộng vào run và cuộc trò chuyện, và sổ cái sử dụng ghi chúng dưới mục đích
`pdf`.

Các trang trả về dưới tiêu đề `--- Trang N ---`. Trang không đọc được nhận một
dòng trong ngoặc vuông thay cho văn bản chứ không phải lỗi, nên một trang không đọc được không bao giờ
làm bạn mất những trang đã đọc được. Khi không cấu hình vision route, tool vẫn
được đăng ký và PDF chữ sắp sẵn vẫn đọc được; mỗi trang scan thay vào đó nói nó cần `vision_routes`.

`pages` nhận `"1-5"` hoặc `"3"`. Bỏ trống thì đọc từ đầu, tối đa 50 trang.
Văn bản sau đó đi qua trần đầu ra của agent như mọi kết quả tool khác.

### Hỏi người dùng

`ask_user` là cách agent gặp ngã rẽ thật sự lấy được câu trả lời thay vì đoán.
Nó nhận một `question`, `options` tuỳ chọn để chọn, và một `default` để rơi về.

Nó dùng lại bộ máy duyệt cho việc dừng và tiếp tục, nhưng nó không phải một lượt duyệt
và khác ở ba điểm quan trọng:

- **Cuộc trò chuyện autonomous vẫn dừng.** Autonomy nghĩa là "đừng hỏi tôi cho phép
  tool của bạn", không phải "đừng bao giờ nói với tôi". Một câu hỏi tự duyệt chính nó sẽ
  không ai trả lời và vô nghĩa.
- **Nó đóng theo đường riêng.** Câu hỏi được *trả lời*, không phải được duyệt hay từ chối, và
  server từ chối các dòng của bên kia trên mỗi đường. Trên web đó là thẻ câu hỏi
  với các lựa chọn và ô nhập; trên Telegram đó là reply vào tin nhắn câu hỏi,
  bằng số hoặc bằng chữ.
- **Hết giờ không phải từ chối.** Tool không ai cho phép thì không được chạy, nhưng
  câu hỏi không ai trả lời vẫn có `default`: agent được trao nó, đi tiếp, và
  được bảo nói trong câu trả lời rằng nó đã tự quyết. Hạn là
  `approval_ttl_seconds` của cuộc trò chuyện (lịch đã mở nó có thể đặt dài hơn), không có thì
  của `config.yaml` (mặc định 600), nên job có thể hỏi khi không ai theo dõi nên luôn truyền
  `default`.

Vì nó tạm dừng lượt, mỗi cuộc trò chuyện chỉ có thể mở một câu hỏi tại một thời điểm, và
ô soạn tin đóng khi đang có một câu: server từ chối tin mới khi bất kỳ
lượt duyệt nào đang chờ. Timeline của run hiện chỗ dừng như một step chờ riêng thay vì
để một khoảng trống đọc như agent đang nghĩ suốt một giờ.

### Nói mình đang làm gì

`progress_note` là đối lập của `ask_user`: nó không bao giờ dừng gì cả. Agent gọi nó
với một dòng ngắn trước một đoạn việc dài, và dòng đó hiện trên timeline của run
trong khi việc còn đang diễn ra, nên người theo dõi thấy "đang đọc lịch" thay vì
một spinner và một phỏng đoán.

Nó khác mọi tool khác ở ba điểm:

- **Nó không bao giờ hỏi.** Không cần duyệt và không gì tra danh sách hỏi. Một ghi chú
  cần xin phép sẽ tới sau cái việc nó đang báo.
- **Step của nó có kiểu riêng.** Step được ghi là `note`, không phải `tool`, vì ghi chú
  không có thời lượng và không thể thất bại — hiển thị nó như tool call sẽ cho timeline một
  dòng mãi mãi đang chạy dở.
- **Chữ quá dài bị cắt ngắn, không bị từ chối.** Trần là 200 ký tự và phần vượt
  bị cắt. Agent viết cả đoạn nhận được ghi chú ngắn hơn; nó không nhận lỗi
  giữa lượt.

Ghi chú không phải trí nhớ. Nó sống trên run và chết cùng run, nên không gì viết ở đây tới được
cuộc trò chuyện kế tiếp — đó là việc của `memory_save`.

### Đề xuất lịch chạy

`schedule_create` là cách agent tự đề xuất một việc lặp lại thay vì chờ người sửa
`agent.yaml` bằng tay. Nó nhận `name`, `prompt`, đúng một trong `cron` hoặc `every`, và
`skills` tuỳ chọn. Không có tham số `agent`: lịch luôn thuộc agent gọi tool, kể cả master —
lập lịch cho agent khác vẫn phải qua `agent.yaml`. Tool chỉ dùng khi người muốn việc lặp lại;
một việc chạy một lần không cần lịch nào cả.

Nó khác mọi tool khác ở một điểm duy nhất nhưng tuyệt đối: **nó luôn dừng chờ người duyệt,
kể cả trong cuộc trò chuyện `autonomous`, kể cả khi tool nằm trong `auto_approve`, kể cả khi
nó nằm trong allow-list của agent.** Luật này nằm trong code (`Tool.ask_reason`, xem
[design.md](design.md#scheduler)), không phải cấu hình, và không công tắc
nào trong `agent.yaml` hay `config.yaml` tắt được nó — tạo một lượt chạy không người trông
trong tương lai là đúng loại việc mà duyệt tồn tại để chặn. Thẻ duyệt mang nguyên văn prompt
sẽ chạy, lịch viết ra lời (ví dụ "Mỗi ngày 07:00"), ba lần chạy kế tiếp (với `every` chỉ là giờ
ước chừng, vì khoảng lặp tính từ lúc duyệt), skill đi kèm và một câu nói rõ: sau khi duyệt, mỗi
lần chạy là một lượt agent tự dùng tool mà không hỏi từng bước. Nút "Luôn cho phép" bị ẩn trên
mọi thẻ có reason, thẻ này cũng như thẻ lệnh shell khớp mẫu hỏi: bấm nó không bỏ được lần hỏi
ấy — luật hỏi luôn đứng trên `auto_approve` — mà chỉ lặng lẽ miễn duyệt các lời gọi khác của
cùng tool. Nếu tool không dựng nổi reason (rỗng, hoặc lỗi giữa chừng) thì cổng vẫn dừng chờ
người, thẻ khi đó chỉ ghi tên tool, và lượt không bị đổ.

Giới hạn kiểm trước khi ra thẻ và kiểm lại lúc chạy: `every` từ 15 phút tới 366 ngày, hai lần
chạy liền nhau của `cron` cũng phải cách nhau ít nhất 15 phút, cron dài tối đa 100 ký tự và
phải có lần chạy trong vòng 366 ngày, tên (tối đa 60 ký tự) và prompt (tối đa 2000 ký tự) không
được rỗng, `skills` là danh sách tên skill có thật (một tên đứng riêng được hiểu là một skill,
tên lặp chỉ tính một lần), và tối đa 20 lịch tạo từ chat cho mỗi agent. Đề xuất sai, hay agent
đã có đủ 20 lịch, vẫn ra một thẻ duyệt trung thực: reason của thẻ khi đó là chính lời báo lỗi.
Trần được kiểm lại một lần nữa lúc chạy, vì giữa lúc ra thẻ và lúc duyệt có thể có một lịch
khác vừa được duyệt.

Lịch được duyệt lưu trong DB, không phải `agent.yaml`, nên chạy ngay không cần khởi động lại
và sống qua lần khởi động lại kế tiếp; xem [Lịch](agents.md#lịch) để biết nó đứng cạnh lịch
YAML thế nào và xoá ra sao. Agent có allow-list `tools:` riêng cần được thêm `schedule_create`
vào danh sách đó mới dùng được; master không có allow-list nên có tool này ngay.

### Canvas

Canvas là tài liệu có phiên bản đi cạnh cuộc trò chuyện, người và agent cùng sửa. Mục này là
tham chiếu cho bảy tool `artifact_*`; canvas là gì, người dùng nó trên web ra sao và vì sao nó
được thiết kế như vậy nằm ở [canvas.md](canvas.md). Sáu tool không hỏi duyệt: mỗi lần ghi thêm
một phiên bản và bản cũ vẫn khôi phục được, nên không lần ghi nào của agent làm mất chữ của
người. Chỉ `artifact_export` cần duyệt, như `workspace_write` và ở kênh nào cũng vậy, vì nó ghi đè
một tệp trong workspace, thứ không có lịch sử phiên bản. Agent không có allow-list `tools:` có đủ bảy tool; agent có allow-list
chỉ có những tool canvas nó liệt kê, nên một danh sách viết trước khi có canvas không tự nhận
thêm quyền ghi.

- **Loại và trần.** `artifact_create` tạo được năm loại chữ: `markdown`, `code` (kèm `language`,
  ví dụ `python`), `html`, `svg` và `mermaid`. Loại thứ sáu, `image` (PNG, JPEG, GIF, WebP), chỉ
  vào canvas qua `artifact_import`. Trần tính cho mỗi phiên bản và theo loại: 512 KB cho
  `markdown`, `code` và `mermaid`, 2 MB cho `svg` và `image`, 4 MB cho `html`. Tiêu đề tối đa
  200 ký tự. Mọi phiên bản của mọi canvas cộng lại có trần 1 GiB; agent dừng ở chín phần mười
  trần đó để người vẫn còn chỗ lưu. Trần nằm trong code, không có khoá cấu hình.
- **Kênh.** Lượt từ web chat, từ Telegram và job ghi được canvas, cùng agent được giao việc
  trong chuỗi bắt đầu từ một lượt như vậy: canvas mở cạnh web chat, còn chat Telegram nhận nó
  thành tệp và được báo lượt đã ghi gì. Lượt Telegram và job có người đọc không ngồi ở web
  chat lúc agent viết, nên system prompt của chúng kết thúc bằng mục **Canvas** dặn chỉ tạo
  canvas khi được dặn hoặc khi tài liệu dài và sẽ còn sửa, và cho biết một dòng riêng
  `FILE: artifact:<id>` gửi canvas kèm tin nhắn khi lượt được gửi qua Telegram. Lượt qua
  `/api/inbound` chưa có đường mang canvas về cho người: nó vẫn có các tool canvas để phần đầu
  prompt giống lượt web, nhưng lời gọi tạo, sửa, viết lại hay nhập tệp bị từ chối và không gì
  được ghi; system prompt của lượt đó kết thúc bằng mục **Canvas** dặn trả lời thẳng trong tin
  nhắn, nêu tên những tool ghi agent đang có. Đọc, liệt kê và xuất ra tệp (`artifact_export`,
  vẫn cần duyệt) chạy ở mọi kênh. Agent được giao việc theo kênh của lượt mở đầu chuỗi giao việc
  chứ không theo cuộc trò chuyện của riêng nó; chuỗi không ghi nhận được lượt mở đầu, như cuộc
  trò chuyện con mở trước khi nâng cấp, thì không ghi được. Xem
  [channels.md](channels.md#cuộc-trò-chuyện).
- **Tầm với.** Master với tới mọi canvas. Agent khác với tới canvas gắn với cuộc trò chuyện của
  nó, canvas chuỗi giao việc của nó đã chia sẻ, và canvas nó tự tạo. Canvas do người tạo chỉ vào
  tầm của agent khi đã gắn vào cuộc trò chuyện. Đọc và xuất ra tệp chỉ gắn canvas vào cuộc trò chuyện
  đang gọi, không chia sẻ; tạo, sửa, viết lại và nhập tệp có thay đổi chia sẻ nó với cả chuỗi,
  nên agent được giao việc sau trong chuỗi mở được.
  Canvas ngoài tầm nhận đúng câu trả lời của canvas không tồn tại, nên agent không dò được canvas
  nằm ngoài tầm.
- **Ngân sách của một lượt.** Tối đa 30 bản cho mỗi canvas và 30 canvas mới, lần nhập tệp tính
  chung với lần tạo và lần ghi; lần ghi không đổi gì và lần xuất ra tệp không tính. Chạm trần
  thì tool bảo agent dừng và báo người những gì đã làm.
- **Nhập và xuất tệp.** `artifact_import` chỉ đọc tệp thường nằm trong workspace, vừa trần của
  loại, và chữ phải là UTF-8. Nhập vào canvas đã có mà canvas đó có bản agent chưa thấy thì bị
  từ chối, trừ khi lời gọi nêu `replace`. Canvas nhớ tệp nó được nhập từ, nên web hiện nguồn và
  cho người nhập lại. `artifact_export` ghi trọn tệp hoặc không ghi gì, và tuân `write_paths`
  như các tool ghi tệp; xem [Tool workspace](#tool-workspace).
- **Đọc theo trang.** Mỗi trang là chữ nguyên văn, không đánh số dòng, vừa trần đầu ra của agent
  kể cả khi hook nối thêm ghi chú. Đầu trang ghi bản và khoảng dòng; chân trang là lệnh đọc tiếp
  với đúng bản đó, để mọi trang thuộc cùng một bản. Chỉ một lần đọc liền từ dòng đầu tới dòng cuối
  mới tính là đã thấy bản đó.
- **Sửa một đoạn.** `old` phải khớp đúng một chỗ, trừ khi `replace_all`. Không khớp chính xác thì
  thử lại với nháy cong coi như nháy thẳng và dấu cách đặc biệt coi như dấu cách. Vẫn không khớp
  thì lời từ chối trích nguyên văn chỗ giống nhất, khi có một chỗ đủ giống mà không chỗ nào khác
  giống ngang nó. Sửa xong, kết quả nêu cỡ mới của canvas, số byte và số dòng đếm như trang
  đọc, để agent đang nới một tài liệu tới độ dài được yêu cầu không phải đọc lại hay đo bằng
  shell sau mỗi lần sửa. Kết quả cũng trích diff của chỗ vừa đổi; phần giữa hai bản đổi quá 600
  dòng thì diff không được vẽ, thay bằng một câu bảo đọc lại bằng `artifact_read`, vì so từng
  dòng tốn thời gian theo bình phương số dòng đó. Diff vẽ ra được tính trong một luồng riêng để
  không chiếm vòng lặp mà mọi cuộc trò chuyện của máy chủ dùng chung.
- **Viết lại cả canvas** chỉ chạy khi bản mới nhất là bản cuộc trò chuyện đã thấy trọn, qua một
  lần đọc hết hay vì chính nó vừa ghi bản đó. Có người hay agent khác lưu từ đó thì lần ghi bị từ
  chối kèm diff của phần họ đổi (khi phần đó đổi quá 600 dòng thì thay diff bằng câu bảo đọc bản
  mới nhất bằng `artifact_read`), và lời từ chối dặn sửa bằng `artifact_edit`. Mô tả của tool
  nói rõ bản agent vừa tạo hay viết lại trong lượt thì không cần đọc lại, còn mô tả của
  `artifact_create` dặn sửa chính canvas đã có thay vì tạo canvas thứ hai cho cùng tài liệu: khi
  đo, model thấy bản nháp đầu ngắn hơn yêu cầu thì có lúc đọc lại từng trang vừa gửi, có lúc tạo
  luôn một canvas trùng.
- **Tác giả.** Khi canvas có bản agent chưa thấy, trang đọc và kết quả sửa nêu ai viết các bản đó
  (ví dụ "v3–v5 người, v6 agent:coach"). Bản do agent viết không bao giờ được gọi là của người, để
  chữ chèn qua prompt không mượn được lời người. Dòng này nêu tối đa sáu nhóm mới nhất, vì đó là
  những bản agent sắp gặp, và đặt "…" ở đầu khi còn nhóm cũ hơn. Bản khôi phục luôn là một nhóm
  riêng nêu bản nó đưa về (ví dụ "v7 người khôi phục v2"): nó mang lại chữ agent có thể đã biết,
  nên không được lẫn vào một loạt lưu thường của cùng người.
- **Ghi chú canvas.** Người sửa canvas thì agent biết ở tin kế tiếp mà không cần gọi tool:
  tin được lưu kèm một ghi chú nêu canvas nào đã đổi từ lần agent nghe gần nhất, diff của chỗ
  người tự sửa, và với tin từ web chat, canvas đang mở cùng đoạn người đang chọn. Diff đi từ
  bản agent đã thấy trọn và cho thấy mọi chỗ đổi thì tính như agent đã thấy bản mới; ngoài
  trường hợp đó agent vẫn phải đọc lại trước khi viết lại cả canvas. Xem
  [system-architecture.md](system-architecture.md#6-ngữ-cảnh-đi-vào-trí-nhớ-đi-ra).
- **Thẻ.** Kết quả của mọi lần ghi thành công mở đầu bằng `[artifact <id> v<n>]`, thêm
  ` unchanged` khi nội dung không đổi và không có bản mới; trang đọc và danh sách không bao giờ
  mở đầu như vậy.
- **Lượt sau không mang lại tài liệu.** Khi lượt đã xong, chữ một lần ghi gửi đi (`content` của
  tạo và viết lại, `old` và `new` của sửa) được thay trong prompt bằng một ghi chú: đã vào canvas
  nào bản mấy, thất bại nên chưa lưu gì, hoặc bị ngắt giữa chừng nên phải xem danh sách trước khi
  ghi lại. Lần ghi bị một lần khởi động lại cắt cũng để lại ghi chú bị ngắt ấy chứ không phải ghi
  chú thất bại, vì nó có thể đã chạy. Lượt đang chạy giữ nguyên mọi chữ đến hết lượt, kể cả sau khi người chen tin hay sau
  một lần chờ duyệt; kho vẫn giữ lời gọi đúng như đã gọi.

## Máy chủ MCP

Ngoài các tool có sẵn, agent dùng được tool của một máy chủ MCP (Model Context Protocol) ở xa:
Notion, một wiki nội bộ, bất cứ dịch vụ nào nói giao thức này qua HTTP. Client viết tay trên
`httpx` (`my_agent_crew/mcp/`), không kéo thêm SDK nào. Chỉ hỗ trợ kiểu truyền **streamable
HTTP**; máy chủ kiểu stdio không dùng được, vì chạy nó nghĩa là chạy chương trình của người khác
trên máy này với quyền của crew.

### Khai máy chủ trong config.yaml

```yaml
mcp_servers:
  notion:
    url: https://mcp.notion.com/mcp
    description: Ghi chú và cơ sở dữ liệu của nhà
    exposure: deferred            # direct | deferred | codemode | hidden
    tool_exposure:                # theo tên tool của máy chủ, * là một đoạn bất kỳ
      notion-search: direct
      notion-fetch: codemode      # gọi được từ script, vì cũng nằm trong read_only
      "notion-delete-*": hidden
    read_only:                    # những tool chạy không hỏi
      - notion-search
      - notion-fetch
    timeout: 60                   # giây cho một request, tối đa 600
  wiki:
    url: https://wiki.example.com/mcp
    headers:
      Authorization: "Bearer ${WIKI_TOKEN}"
```

| Khoá | Ý nghĩa |
| --- | --- |
| tên máy chủ | chữ và số, có thể ngăn bằng **một** dấu `-` hoặc `_` mỗi chỗ (`my-notes`, `team_wiki`); không có dấu ở đầu, ở cuối hay hai dấu liền nhau; tối đa 32 ký tự. Một tên như `work__crm` hay `work_` bị từ chối vì nó làm tool của hai máy chủ ra cùng một tên (xem [Tên, duyệt và gọi lại](#tên-duyệt-và-gọi-lại)). Hai tên chỉ khác nhau ở hoa/thường hay `-`/`_` cũng bị từ chối, vì dùng chung tên biến môi trường |
| `url` | bắt buộc, `https`. `http` chỉ cho máy chủ trên chính máy này (`localhost`, `127.0.0.1`, `::1`). Không user, mật khẩu hay `#fragment`. Địa chỉ được dùng và được hiện đúng như đã viết: nó **không** đọc `${TÊN_BIẾN}` (viết vậy bị từ chối, vì máy chủ sẽ nhận nguyên mấy chữ đó thay cho khoá), nên đừng đặt khoá vào địa chỉ. Máy chủ chỉ nhận khoá qua địa chỉ thì chưa dùng được |
| `description` | một dòng cho người đọc, hiện ở Kết nối và ở ô chọn của agent |
| `headers` | header gửi kèm mỗi request. Giá trị **phải** lấy từ môi trường, viết `${TÊN_BIẾN}`: giá trị viết thẳng bị từ chối, vì tệp này không bao giờ giữ khoá. Biến được đọc lại ở mỗi request, nên đổi khoá là có hiệu lực ngay |
| `exposure` | mức mở mặc định cho tool của máy chủ, xem bảng dưới; mặc định `deferred` |
| `tool_exposure` | mức mở riêng cho từng tool: tên đúng thắng, rồi tới pattern đầu tiên khớp, rồi mới tới `exposure` |
| `read_only` | tên hoặc pattern những tool **chủ** khẳng định chỉ đọc: chạy không hỏi, và được gọi lại sau khi server khởi động lại giữa lượt |
| `timeout` | số giây cho một request, tính cả lúc chờ lẫn lúc đọc câu trả lời; mặc định 60, tối đa 600. Cũng là hạn cho cả một lần kết nối (mở phiên rồi đọc hết danh sách tool) |

Một lỗi trong mục này làm crew không khởi động và nói rõ khoá nào sai, như mọi lỗi khác của
`config.yaml`. Thêm, bớt hay sửa máy chủ cần khởi động lại; đăng nhập, đổi khoá và bật máy chủ
cho agent thì không.

### Bật cho từng agent

Khai máy chủ chưa giao tool cho ai. Agent nhận tool của một máy chủ khi `agent.yaml` của nó nêu
tên máy chủ đó:

```yaml
mcp: [notion]
```

hoặc khi bạn tích máy chủ ở Quản lý → Đội → agent → Công cụ → **Máy chủ MCP**. Thay đổi có hiệu
lực ngay, không cần khởi động lại. Tool MCP **không** theo danh sách cho phép `tools` và không
theo `mode`: chúng đến cùng máy chủ hoặc không đến. Sửa `mcp` mà còn để lại một tên `config.yaml`
không khai thì bị từ chối (422, "Không có máy chủ MCP tên … trong config.yaml."); ô chọn giữ một
dòng cho tên ấy để bỏ tích. Một tên như thế viết tay trong `agent.yaml` chỉ là một cảnh báo trong
log lúc khởi động và không chặn những sửa đổi khác của agent.

### Tên, duyệt và gọi lại

- **Tên.** Tool của máy chủ mang tên `mcp__<máy chủ>__<tool>`; ký tự ngoài chữ, số và `_` thành
  `_`. Tên dài quá 64 ký tự (giới hạn của provider) bị cắt và đóng bằng tám ký tự băm của tên gốc.
  Hai tool của cùng máy chủ ra cùng một tên thì cái sau bị bỏ, và Kết nối nêu tên nó. Hai máy
  chủ thì không bao giờ ra cùng một tên: quy tắc đặt tên máy chủ bảo đảm `mcp__<máy chủ>__<tool>`
  chỉ đọc ngược lại được theo một cách. Điều đó quan trọng vì "luôn cho phép" được nhớ theo
  tên này: nếu hai máy chủ chung một tên, lời cho phép dành cho tool của máy chủ này sẽ áp sang
  tool của máy chủ kia.
- **Giới hạn.** Crew chỉ nhận của một máy chủ tới một mức: tool có tên dài quá 128 ký tự, hoặc
  có phần tham số lớn quá 50.000 ký tự JSON (hay lồng sâu tới mức không viết lại được), bị bỏ
  và được nêu tên ở Kết nối như tool trùng tên; log của server ghi lý do của từng cái. Máy chủ
  liệt kê quá 1.000 tool thì không tool nào của nó được nhận: nó ở trạng thái không kết nối
  được, kèm đúng lý do đó. Một câu trả lời lớn hơn 4 MB bị từ chối.
- **Duyệt.** Mọi tool MCP hỏi trước khi chạy, trừ những tool chủ ghi vào `read_only`. Máy chủ có
  thể tự nhận một tool chỉ đọc (`readOnlyHint`); lời đó được **hiện** bên cạnh tool và không
  quyết định gì, vì bên nói ra chính là bên đang được tin. Cổng duyệt, `autonomous` và
  `auto_approve` áp dụng như với mọi tool khác.
- **Gọi lại.** Một lời gọi chỉ được gửi một lần. Hết giờ hay đứt kết nối thì không gửi lại: máy
  chủ có thể đã làm rồi. Hai ngoại lệ là hai lời từ chối mà chính máy chủ nói nó chưa chạy gì:
  phiên làm việc nó không còn nhớ (mở phiên mới rồi gửi lại) và phiên đăng nhập hết hạn (gia hạn
  một lần nếu được). Sau khi server khởi động lại giữa lượt, chỉ tool trong `read_only` được gọi
  lại; lời gọi tới tool khác được đóng bằng ghi chú "không rõ đã chạy chưa" như mọi tool ghi.
- **Kết quả.** Chữ được đưa cho model; ảnh, âm thanh và liên kết tài nguyên chỉ được gọi tên
  (`[image: image/png]`), vì một lượt đọc chữ. Kết quả không có chữ nhưng có `structuredContent`
  thì là JSON của phần đó. Trần đầu ra và ba cách rút ngắn ở [Quy tắc chung](#quy-tắc-chung) áp
  dụng nguyên vẹn. Kết quả là dữ liệu, không bao giờ là chỉ thị.

### Mức mở

Một máy chủ có thể liệt kê hàng chục tool, và khai hết cho model ở mọi lượt là trả tiền cho
những tool hiếm khi dùng. Mức mở nói mỗi tool được đưa tới model bằng cách nào:

| Mức | Model thấy gì |
| --- | --- |
| `direct` | tool được khai ở mọi lượt, như tool có sẵn |
| `deferred` (mặc định) | không khai sẵn và không nằm trong danh sách tool của system prompt; agent tìm và nạp bằng `tool_search` khi cần |
| `codemode` | không khai sẵn, tìm và nạp như `deferred`; tool cũng nằm trong `read_only` thì agent còn gọi được nó từ script bằng `tool_script` |
| `hidden` | không giao cho agent nào; vẫn hiện ở Kết nối để chủ biết máy chủ có nó |

Tool không khai sẵn vẫn chạy khi được gọi đúng tên, qua cùng cổng duyệt.

### Tìm và nạp tool

Agent giữ ít nhất một tool MCP không khai sẵn thì được giao thêm `tool_search`. Tool này đến cùng
máy chủ như chính các tool MCP: không theo danh sách cho phép `tools`, không theo `mode`, và mất
đi khi agent không còn tool nào phải tìm (bỏ máy chủ, máy chủ đăng xuất, hay mọi tool của nó đã
là `direct` hoặc `hidden`).

```
tool_search(query, limit?)   →  Đã nạp 2 công cụ, gọi trực tiếp bằng tên:
                                - mcp__notion__notion_search: [MCP notion] Search the workspace…
                                - mcp__notion__notion_fetch: [MCP notion] Read a page by id…
                                Còn 3 công cụ khác khớp; tìm lại với từ khoá hẹp hơn nếu chưa thấy cái cần.
```

- **Tìm ở đâu.** Chỉ trong những tool không khai sẵn mà **chính agent đó** đang giữ; không hỏi
  máy chủ, nên không chờ ai và không bao giờ hỏi duyệt. Mô tả của tool nói với model nó tìm được
  ở máy chủ nào, kèm dòng `description` chủ viết cho máy chủ đó trong `config.yaml`: dòng này là
  thứ duy nhất model biết về máy chủ trước khi tìm, nên đáng viết cho rõ.
- **Khớp thế nào.** BM25 trên tên tool (nặng gấp ba), tên máy chủ, mô tả, và tên cùng mô tả của
  các tham số (đọc sâu tối đa 8 tầng schema). Chữ được so không phân biệt hoa thường và dấu,
  `createPage` và `create_page` đều là hai từ, `pages` khớp `page`. Từ khoá viết đúng tên tool
  (tên đầy đủ hoặc tên của máy chủ) đưa tool đó lên đầu. Máy chủ mô tả tool bằng tiếng Anh thì
  từ khoá tiếng Anh mới khớp.
- **Nạp bao nhiêu.** Mặc định 5 tool khớp nhất, `limit` từ 1 tới 10. Câu trả lời nói còn bao
  nhiêu tool khớp chưa nạp; không khớp gì thì nói mỗi máy chủ đang có bao nhiêu tool.
- **Nạp nghĩa là gì.** Từ lời gọi model kế tiếp, tool được khai kèm schema đầy đủ, **nối vào
  cuối** danh sách đã khai, nên phần đầu request mà provider đã cache vẫn nguyên; system prompt
  không đổi. Mỗi lần nạp vì thế tốn một lần ghi lại cache của phần đuôi, không hơn.
- **Nhớ ở đâu.** Trong chính cuộc trò chuyện: danh sách đã nạp được đọc lại từ những câu trả lời
  của `tool_search` đã lưu, theo đúng thứ tự nạp. Vì vậy nó sống qua một lần khởi động lại giữa
  lượt, kéo dài hết cuộc trò chuyện, và không lan sang cuộc khác. Tool đã nạp mà agent không còn
  giữ (máy chủ bỏ nó, chủ ẩn nó) thì thôi được khai.
- **Duyệt.** Nạp không đổi gì về duyệt: tool đã nạp vẫn hỏi trước khi chạy như cũ, trừ khi chủ
  ghi nó vào `read_only`.

### Gọi tool từ script

Một lượt cần cùng một tool hai chục lần, hoặc chỉ cần ba dòng trong một câu trả lời dài, phải trả
tiền cho từng lời gọi và cho từng câu trả lời nằm lại trong ngữ cảnh. `tool_script` cho model viết
việc đó thành một đoạn script ngắn: script tự gọi tool, tự lọc và gộp, và **chỉ những gì nó in ra**
mới quay về cho model.

```
tool_script(script)   →   những gì script in ra bằng print
```

Ví dụ dưới đây chỉ để minh hoạ cách viết; tên tool và hình dạng câu trả lời là của máy chủ. Nó đi
với cấu hình mẫu ở trên: `notion-search` được khai sẵn nên model gọi nó trực tiếp để lấy danh sách
trang, còn script đọc từng trang bằng `notion-fetch`, tool duy nhất được mở cho script:

```python
pages = ["trang-a", "trang-b", "trang-c"]  # id các trang, lấy từ lời gọi notion_search trước đó
late = []
for page in pages:
    body = tools.mcp__notion__notion_fetch(id=page)
    if "quá hạn" in body:
        late.append(body.split("\n")[0])
print(len(pages), "trang,", len(late), "quá hạn:", ", ".join(late))
```

- **Ai được giao.** Agent giữ ít nhất một tool MCP **vừa nằm trong `read_only` vừa ở mức
  `codemode`** thì được giao `tool_script`, đứng ngay sau `tool_search`. Như `tool_search`, nó đến
  cùng máy chủ: không theo danh sách cho phép `tools`, không theo `mode`, và mất đi khi agent không
  còn tool nào như thế. Crew không mở `codemode` cho tool nào thì không agent nào có nó.
- **Script gọi được gì.** Chỉ những tool chỉ đọc và không hỏi ai, trong số tool agent đang giữ:
  - tool có sẵn tự khai là gọi lại được sau restart: `workspace_read`, `workspace_list`,
    `workspace_grep`, `workspace_glob`, `fetch_url`, `web_search`, `memory_search`,
    `conversation_search`, `wiki_get`, `wiki_search`, `artifact_read`, `artifact_list`,
    `skill_read`, `pdf_read`, `image_read`, `tool_output_read`. Bốn tool cũng chỉ đọc nhưng không
    gọi được từ script là `progress_note`, `delegate`, `tool_search` và chính `tool_script`: chúng
    nói thay agent hoặc làm việc qua cuộc trò chuyện, thứ mà lời gọi của script không thuộc về;
  - tool MCP mà chủ vừa ghi vào `read_only` vừa mở `codemode`. Chỉ `read_only` thôi chưa đủ: mở
    một tool cho script là một quyết định riêng của chủ.

  Lời mô tả của `tool_script` nêu tên cả hai nhóm. Mỗi tool MCP là một dòng gồm tên, các tham số
  theo tên và kiểu (`query: string, limit?: integer`) và một câu mô tả, tối đa 30 tool và 12 tham
  số mỗi tool; cần schema đầy đủ thì model nạp tool đó bằng `tool_search`.
- **Lời gọi bị từ chối.** Gọi một tool phải hỏi trước hoặc có ghi dữ liệu, một tool MCP chưa được
  mở cho script, hay một tên không có, thì script **dừng ngay tại đó**: không `try/except` nào bắt
  được, và câu trả lời nói phải làm gì thay ("gọi trực tiếp", hoặc "nạp bằng tool_search rồi gọi
  trực tiếp"). Vì vậy script không bao giờ chờ người duyệt, và mọi lời gọi có ghi vẫn đi qua cổng
  duyệt như cũ.
- **Ngôn ngữ.** Một phần của Python: biến, `if`/`for`/`while`, hàm và `lambda`, list, dict, set,
  tuple, f-string, comprehension (kể cả dạng `(x for x in ...)`, được dựng thành list),
  `try`/`except`/`finally`, `raise`, `assert`, `json.loads` và `json.dumps`, cùng `len`, `str`,
  `int`, `float`, `bool`, `list`, `dict`, `set`, `tuple`, `repr`, `range`, `enumerate`, `zip`,
  `sorted`, `reversed`, `min`, `max`, `sum`, `any`, `all`, `abs`, `round`, `isinstance`, `print`.
  Phương thức gọi được là một danh sách cố định cho từng kiểu str, list, dict, set và tuple.
  Không có `import` (riêng `import json` được bỏ qua), class, luỹ thừa `**`, `del`, `with`,
  `global`, `yield`, hay đọc thuộc tính (`x.y` không kèm lời gọi). Script được xét cả đoạn trước
  khi chạy: dùng thứ không có thì bị từ chối kèm số dòng, không chạy nửa chừng. Giá trị của biểu
  thức ở dòng cuối cũng được in, như ở dấu nhắc Python.
- **Kết quả của tool trong script.** `tools.TÊN(tham_số=giá_trị)` hoặc `tools.TÊN({...})` trả về
  chữ của kết quả (là JSON thì `json.loads`). Script nhận tới 200.000 ký tự của mỗi câu trả lời,
  nhiều hơn hẳn trần của một lượt, vì nó có mặt là để cắt câu trả lời xuống; dài hơn nữa thì bị
  cắt. Tool lỗi thì ném lỗi, bắt được bằng `try/except`. Hook của agent vẫn được hỏi trước và sau
  từng lời gọi, và một lời gọi bị hook chặn là một lỗi bắt được.
- **Chạy ở đâu.** Trong một tiến trình con riêng (`python -I -S -B`) với **môi trường rỗng**: không
  biến môi trường nào, nên không khoá nào. Nó chỉ nói chuyện với server qua stdin/stdout, mỗi dòng
  một JSON, và chính server là bên chạy tool. Trên macOS tiến trình đó nằm trong một sandbox riêng
  của hệ điều hành: không mạng, không ghi được tệp nào, không sinh được tiến trình thứ hai.
  Sandbox đó không chặn việc đọc tệp, và Linux không có sandbox của hệ điều hành; ở cả hai chỗ
  hàng rào là chính trình thông dịch: script chỉ cầm dữ liệu thường, không import và không đọc
  thuộc tính, nên không có đường nào dẫn tới tệp hay mạng.
- **Tiền và thẻ run.** Một lời gọi có trả tiền cho model (`image_read`, hay `pdf_read` trên trang
  scan) được tính riêng vào cuộc trò chuyện và vào run, như khi gọi trực tiếp. Model không đọc
  các lời gọi của script, nên thẻ run liệt kê chúng dưới bước của script cho người xem: tên tool,
  tham số rút gọn, thời gian, có lỗi không, giá nếu có, và phần đầu câu trả lời. Danh sách gấp
  lại cho tới khi bấm mở, dưới một dòng như "Script đã gọi công cụ 12 lần · 1 lần lỗi". Một lời
  gọi bị từ chối không nằm trong danh sách vì nó chưa chạy gì. Trên API đó là `calls` của step
  tool trong `/api/activity/runs` và của sự kiện `tool_result`.
- **Sau restart.** `tool_script` tự khai là gọi lại được: mọi thứ một script làm đều là lời gọi
  vốn đã gọi lại được, nên script bị cắt giữa chừng được chạy lại từ đầu.

Giới hạn nằm trong code, không cấu hình nào nới được:

| Giới hạn | Mức |
| --- | --- |
| lời gọi tool trong một script | 25 |
| độ dài mã script | 20.000 ký tự |
| số bước tính toán | 2.000.000 |
| CPU | 20 giây |
| script tự chạy một mạch, không gọi tool và không kết thúc | 60 giây |
| tổng thời gian, kể cả lúc chờ tool | 300 giây |
| bộ nhớ đang giữ | 256 MB |
| một giá trị | 8.000.000 phần tử hoặc ký tự |
| đầu ra in ra | 60.000 ký tự |
| tham số của một lời gọi tool | 100.000 ký tự |
| hàm gọi lồng nhau | 40 tầng |
| số nguyên | 256 bit |

Chạm một giới hạn thì script dừng và không bắt được; câu trả lời gồm phần đã in kèm lý do, viết
cho model biết phải làm khác đi thế nào ("Xử lý ít dữ liệu hơn hoặc bỏ vòng lặp thừa."). Riêng khi
tiến trình con bị dừng từ bên ngoài (hết CPU, chạy một mạch quá 60 giây, hết tổng thời gian) hoặc
tự chết thì phần đã in mất theo nó và chỉ còn lý do; các lời gọi đã chạy vẫn được ghi trên thẻ
run.

Vài điều chưa làm, nêu ra để không ai phải đoán:

- Lời gọi trong script không đi qua bộ đếm bước và bộ phát hiện lặp của lượt; trần của chúng là 25
  lời gọi mỗi script. Ngân sách của cuộc trò chuyện chỉ được xét giữa các lời gọi của chính lượt,
  nên một script có thể tiêu quá ngân sách tối đa bằng 25 lời gọi của nó.
- Câu trả lời dài của một tool trong script chỉ bị cắt, không được tóm tắt và không được giữ bản
  gốc để đọc lại bằng `tool_output_read`.
- Thẻ tool trong khung chat và bản xuất Markdown của một run không liệt kê lời gọi của script; thẻ
  run và bản xuất JSON thì có. Thẻ run đang chạy chỉ cộng giá của các lời gọi đó khi lượt xong.

### Xác thực

Hai cách, tuỳ máy chủ:

- **Khoá trong header.** Khai `headers` như trên rồi đặt biến ở Quản lý → Kết nối: thẻ **Máy
  chủ MCP** liệt kê những biến mà header của các máy chủ đọc, kèm tên máy chủ dùng chúng. Lưu
  biến là crew thử lại ngay những máy chủ đang hỏng. Máy chủ từ chối khoá thì hiện "Máy chủ từ
  chối khoá trong header Authorization.", kể cả khi khoá bị từ chối giữa một lời gọi. Một khoá
  có dấu xuống dòng ở giữa không gửi được trong header: lỗi nói đúng điều đó và không chép lại
  giá trị của khoá.
- **Đăng nhập OAuth.** Máy chủ trả lời 401 mà không có khoá riêng thì hiện "cần đăng nhập" và nút
  **Đăng nhập**. Bấm nút, crew tự đăng ký làm một ứng dụng công khai với máy chủ đăng nhập
  (RFC 7591), mở trang đồng ý của máy chủ, rồi đổi mã lấy token (OAuth 2.1, PKCE S256). Đây là
  cách Notion (`https://mcp.notion.com/mcp`) dùng. Máy chủ đăng nhập không cho tự đăng ký thì
  đặt `MCP_<MÁY_CHỦ>_CLIENT_ID` bằng client id bạn đã đăng ký tay.

Một lần đăng nhập chỉ đổi điều gì đó khi bạn quay về với mã hợp lệ: bấm **Đăng nhập** rồi bỏ
dở không đụng tới phiên đang dùng. Lúc quay về, token, client id và tên nơi đã cấp chúng được
ghi cùng một lần, hoặc không ghi gì.

Token hết hạn được gia hạn tự động bằng token làm mới, một lần cho mọi lời gọi bị từ chối
cùng lúc. Ba điều quyết định một phiên đăng nhập còn hay mất:

- **Chỉ nơi đã cấp mới nhận token làm mới.** Crew nhớ máy chủ đăng nhập nào đã cấp phiên đang
  giữ. Nếu máy chủ MCP về sau chỉ sang một nơi đăng nhập khác, token làm mới không được gửi
  tới đó: phiên bị bỏ, dòng của máy chủ nói nơi mới và nơi cũ, và bạn bấm Đăng nhập lại nếu
  máy chủ thật sự đã đổi.
- **Chỉ một lời từ chối rõ ràng mới kết thúc phiên.** Đó là khi máy chủ đăng nhập trả lời
  `invalid_grant` hoặc `invalid_client`. Mọi trục trặc khác (mất mạng, hết giờ, lỗi 5xx, một
  lời từ chối kiểu khác) giữ nguyên phiên; lý do hiện trên dòng của máy chủ và lần gọi sau thử
  lại. Lúc khởi động cũng vậy: lần gia hạn hỏng tạm thời để máy chủ ở trạng thái không kết nối
  được kèm lý do, và các vòng thử lại tự làm tiếp.
- **Mỗi bước có hạn.** Một request của việc đăng nhập có 15 giây, cả việc tìm máy chủ đăng
  nhập có 30 giây, tính từ lúc bắt đầu chứ không phải từ byte gần nhất.

Vài ràng buộc nằm trong code và không tắt được:

- Chỉ đăng nhập được khi trang mở bằng `localhost` hoặc `127.0.0.1` trên chính máy chạy crew:
  địa chỉ quay về sau khi đồng ý là địa chỉ đó, và một máy khác không nên khởi động được việc
  đăng nhập thay chủ. Mở từ nơi khác, nút trả lời 409 kèm đúng câu giải thích.
- Mọi địa chỉ của việc đăng nhập phải là `https` và không trỏ vào mạng nội bộ; không đi theo
  chuyển hướng; máy chủ đăng nhập phải hỗ trợ PKCE S256 và tự nhận đúng tên đã khai. Máy chủ MCP
  trên mạng nội bộ hay trên chính máy này vì thế chỉ dùng khoá trong header.
- Mã chỉ được đổi ở nơi đã phát nó. Máy chủ đăng nhập có nêu tên mình khi trả bạn về (`iss`,
  RFC 9207) thì tên đó phải đúng là nơi bạn được gửi tới; nơi đã hứa nêu tên mà không nêu thì
  mã bị từ chối. Lớp chắn này chỉ có tác dụng với máy chủ đăng nhập có gửi `iss`.
- Token được giữ ở cùng chỗ với khoá của provider: tệp env trong home (chỉ chủ đọc được) và môi
  trường của tiến trình, dưới tên `MCP_<MÁY_CHỦ>_ACCESS_TOKEN`, `MCP_<MÁY_CHỦ>_REFRESH_TOKEN`
  và `MCP_<MÁY_CHỦ>_ISSUER` (tên nơi đã cấp). Ba biến này không hiện trong danh sách khoá và
  không API nào trả giá trị của chúng: về một máy chủ, crew chỉ nói đã đăng nhập hay chưa.
  **Đăng xuất** xoá cả ba và giữ lại client id, vì đó là tên của crew ở máy chủ ấy.

### Trạng thái và thử lại

| Trạng thái | Trên web | Nghĩa là |
| --- | --- | --- |
| `idle` | đang kết nối | chưa có câu trả lời của lần thử này |
| `connected` | đã kết nối | đã mở phiên và đọc được danh sách tool. Dòng vẫn có thể mang một lý do: lần gia hạn đăng nhập gần nhất hỏng mà chưa bị từ chối hẳn |
| `signed_out` | cần đăng nhập | máy chủ đòi đăng nhập, phiên đã bị từ chối hẳn, hoặc máy chủ chỉ sang một nơi đăng nhập khác; chỉ chủ làm được, nên crew không tự thử lại |
| `failed` | không kết nối được | kèm lý do: thiếu biến, khoá bị từ chối, hết giờ (một request hoặc cả lần kết nối), HTTP lỗi, trả lời sai giao thức, liệt kê quá nhiều tool, gia hạn đăng nhập hỏng tạm thời |

Một máy chủ hỏng là một dòng nói vì sao, không bao giờ là một crew không khởi động được. Lúc khởi
động crew chờ các máy chủ tối đa 10 giây; cái nào chưa xong được thử tiếp ở nền, lần đầu sau 30
giây rồi thưa dần tới 10 phút một lần, và thử ngay khi một khoá được lưu hay xoá. Nút **Kết nối
lại** thử ngay một máy chủ. Mỗi máy chủ chỉ có một lần thử mỗi lúc: vòng thử ở nền bỏ qua máy chủ
đang có người kết nối, còn lần kết nối được yêu cầu khi một lần khác đang chạy thì chờ lần ấy xong
rồi thử lại từ đầu, vì khoá hay phiên đăng nhập có thể vừa đổi. Mỗi lần một máy chủ lên, xuống hay đổi danh sách tool, từng agent
được giao lại đúng những tool các máy chủ đang có. Máy chủ bỏ phiên làm việc giữa chừng (nó
khởi động lại, hay phiên hết hạn) thì lời gọi kế tiếp tự mở phiên mới; không cần bấm gì.

### API và màn hình

```
GET    /api/mcp                    → {"servers": [{"name", "url", "description", "status", "error",
                                       "exposure", "signed_in", "uses_key", "env", "agents",
                                       "skipped", "tools": [{"name", "remote", "description",
                                       "exposure", "requires_approval", "read_only_hint"}]}]}
POST   /api/mcp/{name}/reconnect   → cùng danh sách, sau khi thử lại máy chủ đó
POST   /api/mcp/{name}/login       → {"authorize_url"}; 409 kèm lý do khi không đăng nhập được
DELETE /api/mcp/{name}/login       → cùng danh sách, sau khi đăng xuất
GET    /api/mcp/oauth/callback     → máy chủ đăng nhập trả người dùng về đây; chuyển tới #/manage/connections
```

Tên không có trong `config.yaml` là 404. Danh sách không bao giờ mang giá trị header hay token;
`env` chỉ là **tên** các biến mà header đọc. `url` là địa chỉ đúng như `config.yaml` viết.
`skipped` là tên những tool máy chủ có liệt kê mà crew không nhận (trùng tên, tên quá dài, tham
số quá lớn); tên quá dài được cắt bớt khi hiện.

- **Kết nối.** Thẻ **Máy chủ MCP** có một dòng cho mỗi máy chủ: trạng thái, địa chỉ, lý do hỏng,
  agent nào đang bật nó, các tool (mức mở, có hỏi trước không, máy chủ có tự nhận chỉ đọc không)
  và các nút Đăng nhập, Kết nối lại, Đăng xuất. Máy chủ đang được thử thì trang tự đọc lại mỗi 2
  giây cho tới khi có câu trả lời; sau khi lưu một khoá, những máy chủ đang hỏng cũng được theo
  dõi như vậy trong chốc lát.
- **Công cụ.** Tool MCP nằm trong bảng cùng các tool khác, kèm nhãn `MCP <máy chủ>` và mức mở.
  Ô của agent chưa bật máy chủ mang dấu `◇` ("agent chưa bật máy chủ MCP này"), không bao giờ
  được giải thích bằng danh sách cho phép, khoá hay chế độ. `tool_search` và `tool_script` có
  nhãn "đi kèm MCP"; ô của agent không giữ tool đó mang dấu `·` ("agent không có công cụ MCP
  nào cần tới công cụ này"). Bảng được
  đọc lại mỗi lần mở mục này, và ngay khi danh sách tool của một máy chủ đổi trong lúc đang mở,
  nên nó luôn cho thấy ai đang giữ gì sau khi sửa một agent hay đăng xuất một máy chủ.
- **Trình sửa agent.** Mục Công cụ có ô chọn máy chủ; danh sách cho phép ở trên nó không liệt kê
  tool MCP và cũng không liệt kê `tool_search` hay `tool_script`.

## Provider không cần khoá

Hai trong số các provider không cần thông tin xác thực, và cả hai tồn tại để vẫn có thứ hữu ích
chạy được khi không có khoá và không có mạng.

`ollama` nói chuyện với server tương thích OpenAI cục bộ tại `OLLAMA_BASE_URL`, mặc định
`http://127.0.0.1:11434/v1`. Vì không cần khoá nên nó luôn được dựng, nên tuyến như
`ollama:qwen3:8b` có sẵn bất cứ khi nào ollama thực sự đang chạy; không có gì lắng nghe thì chỉ
rơi về như mọi tuyến hỏng khác. Nó là nhà tự nhiên cho việc rẻ, khối lượng lớn —
chẳng hạn tóm tắt đầu ra tool dài, việc nếu không sẽ thêm một lời gọi trả phí vào
mỗi kết quả lớn. Model cục bộ không báo giá, nên thẻ run hiện chi phí là
không rõ thay vì bằng không, vì đó là hai khẳng định khác nhau.

Với `MY_AGENT_ROUTES=fake:echo` không model nào được gọi và một tin nhắn `/tool <name>
{json}` chạy tool đó qua registry thật và đường duyệt thật. Đây là cách live
smoke và test trình duyệt điều khiển tool mà không cần khoá.

## Ai đang dùng tool nào

```
GET /api/tools → [{"name": "workspace_read", …, "agents": ["fullstack-developer", "default"], "optional": false}]
GET /api/agents/{id}/prompt → assembled system prompt this turn (includes persona, memory, skills, roster), plus `opening`
```

Hợp của các tool là registry của mọi agent, không phải bộ riêng của master — profile có danh sách
cho phép `tools` giữ ít tool hơn master, và đọc registry của một agent sẽ giấu
những tool phần còn lại của đội vẫn dùng. `agents` là ai giữ nó, tức câu trả lời cho
"cố vấn có thực sự sửa được tệp không"; `optional` đánh dấu tool chỉ tồn tại khi
khoá hoặc tuyến của nó được cấu hình (`image_read`). Tool của một máy chủ MCP có thêm `server` và
`exposure`, chỉ được liệt kê khi có agent bật máy chủ đó, và tool `hidden` không bao giờ có mặt
(xem [Máy chủ MCP](#máy-chủ-mcp)). Dòng của `tool_search` và của `tool_script` mang
`with_mcp: true`: agent giữ chúng nhờ các tool MCP của nó, không nhờ danh sách cho phép (xem
[Tìm và nạp tool](#tìm-và-nạp-tool) và [Gọi tool từ script](#gọi-tool-từ-script)).

Endpoint `/prompt` trả về system prompt đầy đủ như đã lắp cho agent (hữu ích để
debug agent thấy gì, hoặc cho người dùng xem agent biết gì). Trường `opening` (kèm
`opening_chars`) là khối ghi chú ngày mà tin đầu của một cuộc mới sẽ được đọc sau; chuỗi rỗng
khi agent chưa có ghi chú. Ghi chú ngày không nằm trong `prompt`.

```
GET /api/connections → {"providers": […], "routes": […], "vision_routes": […],
                        "audio_routes": […],
                        "keys": [{"name": "OPENROUTER_API_KEY", "present": true}],
                        "telegram": [{"agent_id": "…", "token_env": "…",
                                      "configured": false, "ignored": false}]}
```

Không giá trị bí mật nào xuất hiện trong cả hai phản hồi. Khoá là có hoặc không; kênh
Telegram được nêu bằng *biến môi trường* giữ token của nó, và chat id không được
báo cáo chút nào — đủ để phân biệt khoá thiếu với khoá sai mà không đưa cái nào
vào tab trình duyệt hay ảnh chụp màn hình. Một test khẳng định toàn bộ body đã serialize không chứa
bí mật nào đã cấu hình, nên tính chất này vẫn giữ khi thêm trường mới. (Trình sửa agent có
trả về `chat_id`, vì trường không ai thấy là trường không ai sửa được; view này là
view người ta chụp màn hình, nên nó chỉ giữ những gì chẩn đoán được kết nối.)

`configured` là biến môi trường của chính dòng đó, không phải đội có kênh hay
không — nếu không agent có token chưa bao giờ đặt sẽ đọc như đang chạy. `ignored` đánh dấu
khối `telegram` trên profile không phải master: chỉ khối của master dựng kênh, nên trang
nói vậy thay vì hiện một kênh không bao giờ chạy.

## Thêm tool

Tool nằm dưới `tools/` và gồm tên, mô tả và JSON schema cho model,
một hàm run, và ba cờ: có cần duyệt không, hai lời gọi trong cùng một
message có được chồng lên nhau an toàn không (đọc thì được, ghi vào cùng tệp thì không), và gọi
lại lần nữa có an toàn không (`replay_safe`, mặc định là không). Chỉ tool chỉ đọc mới khai cờ thứ
ba: lượt bị server khởi động lại cắt chỉ gọi lại những tool khai nó, và script của `tool_script`
chỉ gọi được những tool khai nó mà không cần duyệt. Nó được nối
vào bộ tool của từng agent ở chỗ server lắp tool. Chữ mô tả và tham số
được đưa cho model, nên chúng nằm cùng các chuỗi prompt khác, không nằm trong code. Đánh dấu
tool cần duyệt bất cứ khi nào nó thay đổi trạng thái bên ngoài cuộc trò chuyện, thêm một dòng
vào [Các tool](#các-tool) ở trên, và test nó ở tầng thấy được nó
([testing.md](testing.md)).

## So với openclaw

openclaw đi kèm nhiều tool hơn (browser, canvas, nhắn tin phong phú hơn). Ở đây danh mục cố định
và nhỏ có chủ đích: tệp, web, memory, shell. Bộ riêng của agent hẹp hơn
danh mục theo ba cách — `tools` trong profile là danh sách cho phép, `workspace_edit` và các
tool tìm kiếm chỉ tồn tại dưới `mode: work`, và `image_read` chỉ khi chuỗi vision đã
được dựng. `delegate` cũng có điều kiện: master có, agent work có, profile nào
nêu `delegates` có, và agent con được giao việc không bao giờ có.

Vậy danh sách cho phép theo từng agent trên tên tool cũng tồn tại ở đây. Khác biệt thật là thứ
gánh trọng lượng an toàn. openclaw dựa vào tính hiển thị của tool; ở đây điều đó chủ yếu tách
vai trò — cố vấn không ghi được, nghiên cứu không chạy được shell — còn rào
chống lời gọi nguy hiểm là duyệt, và hai danh sách pattern định hình nó từ hai phía.
`shell_ask_patterns` kéo một lệnh về lại chỗ hỏi ngay cả trong cuộc trò chuyện autonomous;
`shell_allow_patterns` cho một lệnh thường ngày đi qua ngay cả trong cuộc trò chuyện được giám sát. Cả hai khớp
dạng lệnh thay vì tên tool, và đó là khác biệt quan trọng: một
`shell_run` có thể là bất cứ gì từ `ls` tới `rm -rf`, nên không danh sách nào trên tên tool có thể
diễn đạt "được chạy test, không được xoá".

Skill lo phần còn lại: skill có thể mô tả một script trong thư mục của nó và model chạy nó
bằng `shell_run`.
