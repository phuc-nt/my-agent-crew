# Tool

**Phiên bản**: 0.11.0 · **Cập nhật**: 2026-10-05

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
cha, nên trần vẫn đúng nghĩa của nó. Lượt bị ngắt giữa chừng khi đang giao việc tìm lại
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
thay vì ảnh nhúng.

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
  ghi lại. Lượt đang chạy giữ nguyên mọi chữ đến hết lượt, kể cả sau khi người chen tin hay sau
  một lần chờ duyệt; kho vẫn giữ lời gọi đúng như đã gọi.

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
GET /api/agents/{id}/prompt → assembled system prompt this turn (includes persona, memory, skills, roster)
```

Hợp của các tool là registry của mọi agent, không phải bộ riêng của master — profile có danh sách
cho phép `tools` giữ ít tool hơn master, và đọc registry của một agent sẽ giấu
những tool phần còn lại của đội vẫn dùng. `agents` là ai giữ nó, tức câu trả lời cho
"cố vấn có thực sự sửa được tệp không"; `optional` đánh dấu tool chỉ tồn tại khi
khoá hoặc tuyến của nó được cấu hình (`image_read`).

Endpoint `/prompt` trả về system prompt đầy đủ như đã lắp cho agent (hữu ích để
debug agent thấy gì, hoặc cho người dùng xem agent biết gì).

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
một hàm run, và hai cờ: có cần duyệt không và hai lời gọi trong cùng một
message có được chồng lên nhau an toàn không (đọc thì được, ghi vào cùng tệp thì không). Nó được nối
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
