# Kênh

**Phiên bản**: 0.41.0 · **Cập nhật**: 2026-11-16

Kênh cho phép người dùng nói chuyện với đội ở nơi khác ngoài web UI. Hiện nay đó là
Telegram. Mọi nền tảng đều đưa tin nhắn tới cùng một cổng inbound: cổng tìm agent,
mở hoặc dùng lại cuộc trò chuyện hôm nay trên kênh đó,
chạy lượt dưới theo dõi hoạt động và trả lời. Vì vậy lượt từ Telegram
chạy qua cùng vòng lặp với web UI, với nguồn `telegram`, nên rail hiển thị chúng.

Telegram hoạt động như web UI: **người dùng nói chuyện với master** và master
giao việc cho đội (tool `delegate`, xem [agents.md](agents.md#agent-master)).
Trên điện thoại cũng không có bộ chọn agent, không có nhắc `@id` và không có bot riêng cho từng agent.

Nền tảng chưa có adapter riêng nói chuyện với cổng qua HTTP:

```
POST /api/inbound {"text": "…", "agent_id"?: "default", "channel"?: "api", "conversation_id"?: "…", "source"?: "api"}
→ 200 {"conversation_id": "…", "agent_id": "default", "text": "…", "status": "done", "steps": 2, "queued": false}
```

`channel` chọn cuộc trò chuyện theo ngày (`api:<something>` tách một relay khỏi
relay khác), `conversation_id` thì tiếp tục một cuộc cụ thể thay vào đó, và `source` là thứ run
hiển thị trong view hoạt động. `source` không được mượn tên kênh của chính server (`chat`,
`telegram`, `web`, `job` hay `job:<id>`, `delegate:<…>`, `memory:<…>`): lượt `chat` được ghi
canvas, còn run `job:<id>` hiện thành lần chạy gần nhất và nằm trong lịch sử của job đó. 404 khi
agent hoặc cuộc trò chuyện không tồn tại, 409 khi cuộc trò chuyện đang chờ duyệt, 422 khi tin chỉ
là `/steer` không kèm chữ hoặc `source` là tên kênh nội bộ, 429 khi hàng của cuộc trò chuyện đã
đủ 20 tin; `detail` của 422 vì `/steer` và của 429 là câu nói cho người đọc. `status` là `done`,
`halted`, `error` hoặc `approval_required`, và khi đó text kết thúc bằng thông báo tương ứng. Đây
cũng là cách test một tính năng đầu-cuối: một request, một câu trả lời, không cần trình duyệt.

Cuộc trò chuyện đang chạy một lượt thì tin không bị từ chối mà vào hàng của nó: `status` là
`queued`, `queued` là `true`, `steps` là 0 và text là câu báo đã xếp hàng. Tin thường được trả
lời bằng một lượt riêng sau khi lượt đang chạy xong, cùng mọi tin chờ với nó; tin bắt đầu bằng
`/steer <chữ>` hay một lệnh trong kit của agent được chèn vào chính lượt đang chạy ở ranh giới
tool kế tiếp (xem [design.md](design.md#hình-dạng-runtime)). Câu trả lời cho tin đã xếp hàng
không quay về request này: relay cần nó thì đọc lại cuộc trò chuyện
(`GET /api/conversations/{id}`).

## Cấu hình

Khối này đặt trên profile của **master**, `MY_AGENT_HOME/agent.yaml`:

```yaml
telegram:
  token_env: TELEGRAM_BOT_TOKEN   # NAME of the env var holding the bot token
  chat_id: 123456789                           # the only chat the bot answers
```

Cả hai key đều bắt buộc; `chat_id` là int. Key thứ ba, `approval_ttl_seconds` (số giây
nguyên từ 60 đến 43200), tuỳ chọn: yêu cầu duyệt trong cuộc trò chuyện mở từ chat này chờ lâu
chừng đó thay vì theo `approval_ttl_seconds` của `config.yaml`, hợp với một chat chỉ được đọc
vài lần mỗi ngày. Trình sửa agent trên web giữ key này khi đổi hai key kia, kể cả khi tắt rồi
bật lại kênh, nhưng không có ô nhập cho nó. Bản thân token nằm trong môi trường của
server — `<home>/env`, được server nạp lúc khởi động và trang **Kết nối** của web UI
ghi vào. Đặt khối này từ trình sửa agent, hoặc lưu token của nó ở Kết nối, sẽ dựng lại
kênh tại chỗ; sửa tay `agent.yaml` vẫn
cần restart. Chỉ thay đổi ở master, giá trị token của nó hoặc `chat_id` mới dựng lại
bot; mọi sửa đổi khác (khoá tìm kiếm, profile của một thành viên) đưa danh sách agent mới cho
bot đang chạy mà không dừng nó. Khi env var chưa đặt,
server ghi log `agent default: env var <NAME> is not set; telegram channel disabled` và
khởi động không có kênh; ngược lại thì `telegram channel enabled for default`. Khối
`telegram:` trên `agents/<id>/agent.yaml` của một thành viên đội bị bỏ qua kèm cảnh báo
`agent <id>: telegram belongs to the master; its block is ignored` — người dùng có một
cửa vào đội, và bot thứ hai sẽ là cửa thứ hai. Update từ bất kỳ chat nào khác bị
bỏ qua và ghi log.

## Một bot, master, đội

Chỉ một bot được dựng, cho master. Mọi thứ gõ trong chat
là một lượt của cuộc trò chuyện với master; khi câu trả lời thuộc về Pong hay HLV thì
master giao việc và chuyển tiếp, đúng như trong web UI, và run của agent được giao xuất hiện
trong phần hoạt động của màn hình quản lý dưới tên riêng của nó.

Đội không tới chat theo đường nào khác: bản tin và lỗi của job theo lịch, của bất kỳ agent nào,
được đọc trên web ([Job theo lịch](#job-theo-lịch)). Ảnh hoặc tài liệu chủ gửi vào chat rơi vào
inbox của **master**; master chuyển đường dẫn đã lưu vào task giao việc khi một thành viên đội cần
đọc nó.

Message của mỗi lượt chỉ nằm trong cuộc trò chuyện của master: không có lịch sử
riêng theo agent trên chat cần tách bạch và không có gì cần chia sẻ giữa các agent ngoài những gì
master nói với chúng trong task.

## Cuộc trò chuyện

Mỗi tin nhắn văn bản trở thành một lượt của cuộc trò chuyện với master cho hôm nay trên kênh
`telegram:<chat_id>` (tiêu đề `Telegram · YYYY-MM-DD`, mở khi dùng lần đầu mỗi ngày, hoặc bằng
`/new`). Trong lúc lượt chạy, chat hiện "đang gõ…" (`sendChatAction` mỗi 4 s). Câu
trả lời là mọi text của assistant trong lượt ghép theo thứ tự, gồm cả text viết cạnh
một tool call, cộng các thông báo dừng, lỗi và duyệt. Lượt kết thúc mà không có một chữ nào
sẽ nói vậy kèm số bước thay vì không gửi gì: im lặng không phân biệt được với
bot chết. Câu trả lời gửi
đi dưới dạng plain text theo
khúc 4 096 ký tự, sau khi bỏ dấu markdown mà Telegram sẽ hiện nguyên: `**đậm**`, `*nghiêng*`,
`#` tiêu đề, đường kẻ `---` (thành một dòng trống), và bảng (mỗi hàng một dòng, các ô nối
bằng ` · `, bỏ dòng `|---|`); dòng `MEDIA:<path>` trở thành `sendPhoto` từ workspace của
agent có cuộc trò chuyện đang được gửi. Dòng `FILE:<path>` gửi một tài liệu (csv, json,
md, pdf, txt, xlsx, zip); nếu nó trỏ vào một ảnh (png, jpg, jpeg, webp) thì ảnh đi bằng
`sendPhoto` như một dòng `MEDIA:`, không bị từ chối vì sai tiền tố.

Ảnh hoặc tài liệu người dùng gửi được tải về (cỡ ảnh lớn nhất, hoặc tài liệu
dưới tên của nó rút gọn thành tên tệp thường) vào `<master workspace>/inbox/` dưới dạng
`<YYYYMMDD-HHMMSS>-<name>`, và text của lượt là `[Tệp đính kèm đã lưu: <path>]` với
caption đi sau. Model không thấy ảnh; persona của master
nói phải làm gì với đường dẫn, chẳng hạn đưa nó cho agent đọc bài báo.
Tải về thất bại được báo vào chat mà không có lượt model. Lệnh slash không được
đọc từ caption.

Voice note (hoặc file audio) được chép lời bằng một tuyến riêng (`audio_routes`, cấu
hình như `vision_routes`) trước khi tới master — model chat không nghe được audio. Note
dài quá 300 giây hoặc nặng quá 10 MB bị từ chối ngay từ metadata, không tải về; định
dạng không nhận ra (không phải mp3/m4a/ogg/wav/flac/aac) cũng vậy. Note hợp lệ được tải
vào `inbox/` như một tệp đính kèm, gửi cho tuyến chép lời, rồi kênh trả lời "Đã nghe: …"
để người gửi tự kiểm tra trước khi lượt của master chạy — bản chép không bao giờ được đọc
như lệnh slash hay `/steer`, dù nó bắt đầu bằng `/`. Chép lời hết giờ (25 giây), tuyến lỗi,
hoặc model nói không nghe rõ đều báo lại lý do bằng tiếng Việt, không lộ nguyên văn lỗi của
provider, và không mở lượt nào cho master. Chưa cấu hình tuyến nào thì kênh báo cách bật
thay vì tải về. Chi phí mỗi lần chép lời ghi vào sổ chi phí dưới purpose `transcribe`.

Nhiều ảnh gửi cùng lúc tới dưới dạng mỗi ảnh một update cùng chung `media_group_id`,
caption chỉ ở ảnh đầu. Kênh gom các update liên tiếp của một album thành
một lượt mà text liệt kê mọi đường dẫn đã lưu, rồi tới caption; một poll kết thúc giữa
album sẽ hỏi lại Telegram tối đa ba lần, cách nhau một giây, trước khi đưa cho agent
nửa album. Offset nhảy qua cả nhóm một lần, nên crash giữa album sẽ lặp lại
album thay vì tách nó.

Cuộc trò chuyện mới không bắt đầu trống: tóm tắt của cuộc trò chuyện trước trên
cùng kênh được đưa vào prompt dưới mục **Cuộc trước**, nên `/new` và
tin nhắn đầu tiên của ngày mới tiếp nối chỗ
cuộc trước dừng lại mà không phát lại các message của nó.

Lượt từ Telegram, lượt job, và agent được giao việc trong các lượt đó, tạo, sửa và viết lại
được canvas như lượt web. Người nhận các lượt này không ngồi ở web chat lúc agent viết (họ đọc
qua Telegram, Hộp thư hoặc xem lại sau) nên không thấy canvas mở ra bên cạnh; vì vậy system prompt của
lượt kết thúc bằng mục **Canvas** dặn chỉ tạo canvas khi được dặn hoặc khi tài liệu dài và sẽ
còn sửa, còn lại trả lời thẳng trong tin nhắn. Mục đó không nói người đọc đang ở kênh nào: job
trên máy không có bot cũng nghe đúng lời ấy. Lượt qua `/api/inbound` không tạo, sửa, viết lại
hay nhập tệp vào canvas được, vì chưa có đường mang canvas về cho người gọi; nó vẫn liệt kê,
đọc và xuất canvas ra tệp (có duyệt), và system prompt của nó dặn trả lời thẳng trong tin nhắn.
Tool và giới hạn ở [tools.md](tools.md#canvas); canvas nói chung ở [canvas.md](canvas.md).

Canvas tới chat theo hai đường.

- **Gửi thành tệp.** Một dòng riêng `FILE: artifact:<id>` hay `MEDIA: artifact:<id>` trong câu
  trả lời gửi bản mới nhất của canvas đó, và caption ghi tiêu đề cùng số phiên bản. Đường dẫn mở
  đầu bằng `artifact:` luôn được hiểu là canvas, không bao giờ là tệp trong workspace: mã viết
  sai thì chat nhận một câu báo, không tệp nào được tìm theo tên đó. Tên tệp là tên canvas tải
  về trên web; canvas `markdown` giữ đuôi `.md`, ảnh giữ đuôi thật và hiện thành ảnh, mọi loại
  khác thêm `.txt` để mở ra là thấy chữ chứ không chạy gì. Ảnh Telegram không nhận làm ảnh thì
  tới dưới dạng tài liệu. Mỗi canvas chỉ gửi một lần trong một câu trả lời. Canvas ngoài tầm
  của agent và canvas không có nhận cùng một câu báo. Tệp quá 20 MB, hay Telegram từ chối, thì
  chat được bảo mở web để xem.
- **Tin "Canvas vừa ghi:".** Sau câu trả lời, chat nhận một tin liệt kê những canvas lượt đã
  ghi, kể cả do agent được giao việc ghi: mỗi canvas một dòng tiêu đề kèm số phiên bản. Tin nêu
  tối đa 10 canvas, phần còn lại gom vào một dòng đếm. Lần ghi không đổi gì không có trong tin.
  Lượt xong mà không có chữ nào nhưng có ghi canvas thì tin này là câu trả lời. Canvas do một
  script ghi (`tool_script` của agent `script_calls: gated`, xem
  [tools.md](tools.md#gọi-tool-từ-script)) cũng có trong tin, đọc từ danh sách lời gọi của
  script chứ không từ cái script in ra. **Giới hạn đã biết:** canvas do agent được giao việc
  ghi chỉ có trong tin khi việc được giao bằng một lời gọi `delegate` trực tiếp. Việc do script
  giao (`tools.delegate`) thì không: trong danh sách lời gọi của script, tin chỉ đọc những lời
  gọi ghi canvas, còn câu trả lời của một việc được giao chỉ được giữ 160 ký tự đầu, gộp thành
  một dòng, nên khối canvas của con không còn ở đó để đọc. Canvas ấy vẫn ở trong kho và mở
  được trên web, từ cuộc trò chuyện của agent con.

Link về web chỉ có khi `web_url` được đặt (xem
[deployment-guide.md](deployment-guide.md#4-biến-môi-trường-và-bí-mật)): mỗi canvas trong tin
thêm một dòng link tới trang riêng của nó, và caption của tệp cũng mang link ấy khi còn chỗ. Để
trống thì tin kết thúc bằng lời bảo mở web UI.

Canvas của một job không tới chat theo đường nào, vì job không gửi gì vào chat: canvas nó ghi nằm
trong kho và mở được trên web, từ cuộc trò chuyện của job.

Chữ rời máy qua đường này được che như log: tiêu đề và nội dung canvas chữ bị che giá trị của
biến môi trường có tên mang `KEY`, `TOKEN`, `SECRET`, `PASSWORD` hay `CREDENTIAL`, cùng chuỗi
có dạng `Bearer …`, khoá `sk-…` và JWT. Đó là giới hạn của nó: bí mật không khớp các dạng này
không bị che, ảnh không được lọc, và người nhận không được báo chỗ nào đã che. Canvas chữ nhập
từ một tệp workspace thuộc loại không gửi qua chat được thì không gửi. Chat nhóm thì mọi thành
viên cùng nhận tệp.

## Lệnh

Được kênh trả lời không cần gọi model, và đăng ký bằng `setMyCommands` một lần mỗi
tiến trình để client hiển thị chúng.

| Lệnh | Tác dụng |
|---|---|
| `/new`, `/reset`, `/start` | mở cuộc trò chuyện khác (bị từ chối khi lượt còn chạy hoặc còn tin xếp hàng) |
| `/help` | danh sách lệnh |
| `/status` | số lượt, chi tiêu so với trần, tuyến, duyệt đang chờ, run gần nhất (giờ bắt đầu theo múi giờ của người dùng, xem `timezone` trong [agents.md](agents.md#agentyaml); run được lưu theo UTC) |
| `/tools` | tên các tool của master |
| `/steer <nội dung>` | chèn ý vào lượt đang chạy; lúc rảnh thì là tin thường |
| `/approve`, `/deny` | giải quyết duyệt đang chờ (của chat hoặc của cuộc con nó giao việc) và stream phần còn lại của lượt về |
| `/pending` | gửi lại mọi yêu cầu chat được quyết (của chat và của cuộc con nó giao việc), cũ trước, tối đa 10, mỗi cái kèm nút |

`/status@botname` dùng được; `/usr/bin` hoặc câu bắt đầu bằng `/` không phải lệnh và
đi tới model. Tin nhắn trong lúc một tool đang chờ duyệt nhận được lời nhắc thay vì một
lượt.

Lượt chạy nền: vòng poll không chờ lượt xong mới đọc tin kế. Trong lúc một lượt chạy, `/status`
trả lời ngay ("đang chạy · N tin xếp hàng"), tin thường vào hàng của cuộc trò chuyện và chat nhận
ngay câu báo đã xếp hàng, không kèm "đang gõ…"; khi lượt xong, tin chờ được trả lời bằng một lượt
riêng như mọi lượt khác. `/steer <nội dung>` hay một lệnh trong kit của agent được chèn vào chính
lượt đang chạy ở ranh giới tool kế tiếp; `/steer` trơn bị từ chối. Tin gửi cùng một poll với tin
đang mở lượt cũng vào hàng. Khi lượt còn chạy hoặc còn tin chờ, chat ở lại cuộc trò chuyện đó, kể
cả qua nửa đêm, và `/new` bị từ chối tới khi xong; `/approve` tìm cả cuộc chờ duyệt không phải cuộc
mới nhất. "Đang gõ…" chờ Telegram tối đa 3 s cho lần hiện đầu, quá hạn thì lượt vẫn chạy và log ghi
cảnh báo. Lượt hỏng giữa chừng được ghi log, còn chat chỉ nghe tên loại lỗi, không nghe nội dung.
Nút Stop trên web chỉ dừng được lượt do hàng của web chạy; lượt Telegram trả lời tin chờ thì chưa.

Câu hỏi agent đặt bằng `ask_user` là chỗ dừng duy nhất không hoạt động theo cách này.
`/approve` và `/deny` bị từ chối ở đó, vì không có gì để cho phép: thứ còn
thiếu là một câu chỉ người dùng mới viết được. Nên khi một câu hỏi đang mở, tin nhắn
thường tiếp theo từ chủ được đọc là câu trả lời chứ không phải yêu cầu mới. Một
số trơn chọn lựa chọn đó trong danh sách đánh số mà câu hỏi gửi kèm — `2` trên câu hỏi
`1. có / 2. không` trả lời `không` — còn mọi thứ khác được chuyển nguyên dạng chữ,
kể cả số mà danh sách không có mục tương ứng và câu chỉ mới bắt đầu bằng một số.
Đây là cách chat thay cho thẻ câu hỏi của web; xem
[Hỏi người dùng](tools.md#hỏi-người-dùng).

### Nút duyệt

Yêu cầu duyệt một tool gửi vào chat kèm hai nút inline **✅ Duyệt** và **❌ Từ chối**, cùng một dòng
cho biết lệnh sẽ chạy (tên tool và tham số JSON, cắt ở 400 ký tự), nên người dùng quyết định trên
lệnh chứ không chỉ trên tên tool. Câu hỏi `ask_user` có lựa chọn mang một nút cho mỗi lựa chọn (tối
đa 8; số trơn vẫn dùng được); câu hỏi không có lựa chọn thì không có nút. Mỗi nút mang id của yêu
cầu, nên bấm nút ở một tin cũ vẫn chỉ giải quyết đúng yêu cầu đó. Bấm xong, tin được viết lại kèm
kết quả ("✅ Đã duyệt.") và mất nút; yêu cầu đã được giải quyết trước đó (bằng nút, `/approve`, web
hay hết hạn) chỉ nhận câu "đã được xử lý rồi". Nút bấm ở chat khác bị bỏ qua.

Cuộc con mà master giao việc (một agent khác của đội làm thay) dừng trong cuộc trò chuyện riêng của
nó. Yêu cầu duyệt của cuộc con thuộc chat được báo ngay vào chat, dưới tên agent đang hỏi, kèm nút;
`/approve`, `/deny` và câu trả lời gõ tay cũng tới được cuộc con. Phần còn lại của lượt cuộc con
được đọc thầm: kết quả trả về tool call của cuộc cha, và lượt của cuộc cha nói tiếp trong chat.
Chat chỉ được báo và chỉ giải quyết yêu cầu của chính nó và của cuộc con nó giao việc, ở mọi đường:
nút, `/pending`, `/approve`, `/deny` và câu trả lời gõ tay. Yêu cầu của một job, của một cuộc gốc
trên web và của cuộc con mà job hay web giao thì không được báo, `/pending` không liệt kê, và bấm
một nút cũ của chúng chỉ nhận câu "đã được xử lý rồi" trong khi yêu cầu vẫn chờ: chúng được quyết
trên web, nơi Hộp thư và thông báo đẩy báo chúng ([design.md](design.md#web-ui)).

Mỗi yêu cầu kèm dòng "⏳ Tự hết hạn lúc HH:MM" theo múi giờ của người dùng. Tin mang nút được nhớ
theo id yêu cầu, ghi ở bảng `telegram_told` nên còn sau khi server khởi động lại; cứ 15 s một vòng
quét xem lại: yêu cầu đã
được giải quyết ở nơi khác thì tin được viết lại kèm kết quả và nơi quyết ("✅ Đã duyệt trên web.",
"⌛ Đã hết hạn, không ai trả lời.") và mất nút; yêu cầu vẫn chờ sau 3 phút thì được nhắc một lần,
trả lời vào chính tin ấy, kèm giờ hết hạn.

Webhook và long polling phải xin `allowed_updates` gồm `callback_query`; polling của engine luôn xin
`["message", "callback_query"]`, còn webhook do bên đặt webhook xin.

## Job theo lịch

**Job theo lịch không gửi gì vào chat.** Telegram chỉ là kênh chat cho những cuộc trò chuyện
chủ mở ở đó. Mọi thứ một job làm ra được đọc trên web: cuộc trò chuyện của job, Hộp thư và
thông báo đẩy ([design.md](design.md#web-ui)). Không thứ nào sau đây tới chat:

- bản tin của prompt job và của lượt mà `then_prompt` của một script job mở ra, kể cả khi lượt
  dừng sớm, hỏng hay không có chữ nào;
- run hỏng của một job script, job lệnh hay lần cô đọng bộ nhớ, run đã chạy lại được, run mà lệnh
  kiểm (`check`) không xác nhận;
- run bị bỏ qua vì trần chi phí ngày ([agents.md](agents.md#trần-chi-phí-một-ngày-của-các-lịch));
- lần cô đọng bộ nhớ bị giữ lại chờ chủ duyệt ([memory.md](memory.md#ngày-trên-mỗi-dòng-và-cổng-tự-áp-dụng));
- yêu cầu duyệt hay câu hỏi của lượt job, và của cuộc con mà một job giao việc; lượt job chạy
  tiếp sau khi yêu cầu ấy hết hạn, được quyết trên web hay được nối lại sau khi server khởi động
  lại cũng không giao câu trả lời vào chat.

Scheduler ghi một dòng log cho mỗi job chạy xong, mọi loại: `job <id>: status=<status> conv=<id>`
(`conv=None` khi run không mở cuộc trò chuyện).

Câu trả lời chỉ gồm `OK` (không phân biệt hoa thường, bỏ qua dấu chấm/than cuối) của một job
kiểm tra không được Hộp thư liệt kê là báo cáo và không có thông báo đẩy; run vẫn nằm trong trang
Jobs và rail hoạt động. Câu trả lời dài hơn, kể cả bắt đầu bằng "OK, nhưng…", là một báo cáo.

### Chuỗi hỏng của job

Ba loại job có thể hỏng mà không mở lượt nào: lịch chạy thẳng một script (khoá `script`,
[agents.md](agents.md#job-chạy-script)), lịch chạy một lệnh (khoá `command`) và lần cô đọng bộ
nhớ theo lịch (`memory_consolidate`). Một run như vậy kết thúc `error` thì Hộp thư xếp nó vào phần
cần chú ý và thiết bị nhận thông báo đẩy; tóm tắt của run nói vì sao nó hỏng. Một job hỏng mỗi năm
phút thì trông như job vừa hỏng lần đầu, nên scheduler đếm cho từng job số lần hỏng liên tiếp:

- Lần hỏng của ba loại job trên được đếm. Job chạy xong mà lệnh kiểm
  ([agents.md](agents.md#lệnh-kiểm-sau-khi-chạy)) thoát mã khác 0 cũng được đếm, kể cả khi run là
  của một lượt: run thành `error`, tóm tắt nói job báo đã chạy xong nhưng lệnh kiểm không xác nhận,
  kèm lý do của lệnh kiểm. Chạy tay (`POST /api/jobs/{agent}/{id}/run`) được đếm như lần chạy của
  đồng hồ.
- Mọi kết cục khác đóng chuỗi: run `done`, run bị dừng `halted`, lượt mà script mở ra bị hỏng (lượt
  là một cuộc trò chuyện và được đọc ở đó). Job bị bỏ qua vì trần chi phí ngày không chạy, nên chuỗi
  giữ nguyên. Run bị cắt vì server dừng (`interrupted`) và job rời đồng hồ trong lúc đang chạy không
  được đếm.
- Chuỗi được ghi vào database (bảng `job_failure_streaks`: số lần hỏng và lúc bắt đầu), nên server
  khởi động lại vẫn đếm tiếp. Job rời đồng hồ (agent bị xoá, dòng lịch bị xoá, kể cả khi server
  đang tắt) thì chuỗi của nó cũng mất; job tạo lại dưới cùng id bắt đầu từ không. Database của một
  home cũ còn cột `told_at` ở bảng này; cột được để nguyên và không ai đọc.
- `GET /api/jobs` cho thấy chuỗi ấy ở khoá `failing` của từng dòng: `null` khi job không ở trong
  chuỗi hỏng nào, còn không thì `{"count": 3, "since": "…"}`. `since` là lúc chuỗi bắt đầu, viết
  theo giờ của chủ, tới phút, cùng dạng với `next_run`.
- Chuỗi được đếm sau khi run đã kết thúc, nên dòng job mà một trang đọc đúng lúc run kết thúc có thể
  chưa mang lần hỏng ấy. Vì vậy, khi việc đếm một run xong mà `failing` của job đã khác trước (thêm
  một lần hỏng, chuỗi đã đóng), luồng `GET /api/activity/stream` phát một sự kiện tên `jobs`,
  payload chỉ là `{"type": "jobs"}`. Nó không mang dòng nào: ai nghe thì đọc lại `GET /api/jobs`.
  Run kết thúc `done` của một job không ở trong chuỗi nào thì không có sự kiện này.
- Cùng sự kiện ấy được phát mỗi khi đồng hồ đọc lại lịch của đội (một agent được lưu, được tạo,
  được cài hay được `POST /api/agents/reload` đem vào, một khoá hay tuyến mô hình chung được lưu
  ở Quản lý → Kết nối) và khi một agent rời đội, dù lần ấy có đổi dòng nào hay không. Nhờ vậy
  trang đang mở ở một tab khác thấy dòng lịch vừa lưu mà không tải lại. Lần lưu bị từ chối không
  phát gì. Một thay đổi không được phát: công tắc tạm dừng của một job; tab khác thấy nó ở lần
  đọc lại kế tiếp (một run kết thúc, luồng được nối lại).
- Trên web, Quản lý → Lịch chạy nói chuỗi ấy thành một câu dưới lần chạy gần nhất của job, chừng
  nào job còn trong chuỗi: `Hỏng 3 lần liên tiếp từ Hôm qua 07:00.` Một lần hỏng thì câu là
  `Hỏng từ 07:00.` Mốc là giờ nếu trong hôm nay, `Hôm qua 07:00` nếu là hôm qua, còn không thì ngày
  kèm giờ (`09/10 22:05`). Trang đọc lại danh sách job khi một run kết thúc, khi luồng phát `jobs`,
  khi nối lại luồng và sau mỗi lần lưu hồ sơ agent, nên câu ấy đổi theo mà không cần tải lại trang.
  Hai lần đọc đang chờ cùng lúc thì trang giữ câu trả lời của lần hỏi sau. Công tắc tạm dừng vừa gạt
  hiện ngay theo câu trả lời của server, rồi trang đọc lại danh sách: một lần đọc đang chờ từ trước
  đó không đưa được dòng về như cũ.

Lý do trong tóm tắt của run hỏng:

- Job script: thứ đã làm script dừng, tức dòng lỗi (`Lỗi ở dòng N: …`, `Dừng ở dòng N: …`); thứ
  script in trước đó nằm ở step `tool_script` của run.
- Job lệnh: dòng cuối báo lỗi trong những gì lệnh in ra, không có thì dòng cuối có chữ; lệnh chạy
  quá 900 giây, hạn của một job lệnh, thì bị dừng. Toàn bộ output nằm ở step `shell_run`.
- Lần cô đọng bộ nhớ: câu báo lỗi của lần gọi model, hoặc dòng nói model không trả về gì. Lần cô
  đọng không có ghi chú mới nào để gộp kết thúc `done`; đó không phải một lần hỏng.

## Giao lại câu trả lời của chat

Một lượt của chính chat đôi khi chạy tiếp ở nơi khác: yêu cầu duyệt của nó hết hạn, được quyết trên
web, hay lượt bị cắt vì server khởi động lại và được nối lại. Khi lượt ấy xong, runtime giao câu trả
lời vào chat: mọi text của assistant ở lượt cuối, theo thứ tự, cùng canvas mà run đã ghi. Chỉ cuộc
gốc của chính chat được giao như vậy: cuộc của web, cuộc con (câu trả lời của nó là của cuộc cha)
và cuộc của job thì không (`Runtime.deliver`).

Khi lượt cuối kết thúc mà không có text nào của assistant (run dừng ở `max_steps` hay vì gọi lại y
hệt một lệnh, lỗi provider, một duyệt còn treo) kênh gửi thông báo "run chưa xong" kèm tóm tắt của
run thay vì im lặng. Khi một duyệt trong lượt đó hết hạn (`approval_ttl_seconds` của
`config.yaml`), phần giao nói trước tool nào bị từ chối vì quá hạn, để câu trả lời theo sau được
đọc là do hàng rào tạo hình, không phải do người.

Run dừng sớm nhưng *có* để lại text là trường hợp khó hơn: câu trả lời nửa chừng đọc như một câu trả
lời hoàn chỉnh. Nên sau khi gửi text, run có status `halted` hoặc `error` nhận thêm tin nhắn thứ hai
"bị cắt ngắn" nêu lý do và run đã tiêu bao nhiêu. Lý do của run `halted` là mã vòng lặp ghi
(`budget`, `max_steps`, `loop`), nên kênh đọc nó thành lời ("chạm trần chi phí", "hết số bước tối
đa", "gọi lại y hệt một lệnh nhiều lần liên tiếp"); lý do của run `error` đã là câu báo lỗi. Giao
thất bại được ghi log, không thử lại.

**Lời gọi nào tới Telegram cũng có hạn.** Lời gọi không tự nêu hạn (`sendMessage`, `sendChatAction`,
`setMyCommands`, `getFile`, ảnh hay tệp gửi từ đĩa) theo hạn của client HTTP mà cả server dùng
chung, 120 giây. Long poll tự nêu hạn 35 giây (25 giây chờ tin cộng 10), tệp gửi từ bộ nhớ 60 giây.
Lời gọi hết hạn kết thúc như mọi lời gọi hỏng khác, tức một lần giao thất bại như trên. Hạn ấy giữ
cho đồng hồ của scheduler chạy tiếp: nó đóng các yêu cầu quá hạn rồi chờ câu trả lời của lượt chat
được nối lại gửi xong, nên một lần gửi không có hạn, trên đường truyền đã im, sẽ giữ mọi job tới hạn
sau nó cho tới khi server khởi động lại.

## Offset và restart

Offset của `getUpdates` được ghi vào `MY_AGENT_HOME/telegram.offset` trước khi mỗi update được
xử lý, nên tin nhắn làm handler crash không bị phát lại mãi. Tệp ghi tên
bot mà nó thuộc về (`<bot id> <offset>`); sau khi token được đổi sang bot khác,
bot mới bắt đầu từ 0 thay vì bỏ qua tin nhắn của nó theo cách đánh số của bot cũ. `409` từ Telegram nghĩa là tiến trình khác vẫn đang poll bot (server cũ, tool
khác); kênh ghi log `another poller holds this bot` và thử lại mỗi 5 s.

Dừng bot (dựng lại sau khi token hoặc chat đổi, hoặc server tắt) để
mọi lượt đang chạy xong (bot thôi nhận tin chờ trước), tối đa 30 s, để các tin nhắn xếp sau nó chưa xác nhận cho
bot tiếp theo, và chỉ trả về khi vòng poll đã kết thúc, nên
bot mới không bao giờ poll song song với bot cũ. Long poll đang rảnh bị cắt ngay. Lượt
vẫn chạy sau 30 s bị huỷ, và chat được báo. Lời báo tuỳ vào cái gì đang dừng:

- **Server đang tắt** (`kickstart`, nâng cấp): "Server đang khởi động lại nên lượt vừa rồi bị
  ngắt giữa chừng. Khi server chạy lại, lượt này sẽ được làm tiếp một lần nếu còn làm tiếp
  được…". Server khởi động kế tiếp mở lại đúng run đó và bot trả lời vào cùng chat bằng trọn
  những gì lượt đã viết, cả phần trước lúc bị cắt lẫn canvas viết khi ấy, nên người dùng không
  phải gửi lại; phần đã gửi lúc lượt dừng để hỏi người thì không được nhắc lại. Lượt chỉ được làm tiếp một lần, và không được làm
  tiếp khi lúc server lên không có bot nào chạy (thiếu token, `--no-schedule`), khi cuộc trò
  chuyện đang chờ một quyết định, đã có lượt mới hơn hoặc đã hết ngân sách; lệnh gọi tool nào
  được chạy lại và lệnh nào không thì xem [design.md](design.md#hình-dạng-runtime). Server bị
  giết không kịp báo (`kill -9`, mất điện) thì chat không nhận lời nào, nhưng lượt vẫn được làm
  tiếp theo cùng luật.
- **Chỉ bot được dựng lại** dưới một server vẫn chạy (token hoặc chat đổi): "…có thể chưa được
  trả lời trọn vẹn… gửi lại giúp mình nhé", để người dùng gửi lại thay vì chờ câu trả lời sẽ
  không tới. Lượt này không được làm tiếp.

Cả hai lời đều nói dè dặt: nhát cắt có thể rơi sau khi text của câu trả lời đã đi, trong lúc
tệp đính kèm vẫn đang tải lên. Thông báo là best effort, giới hạn 5 s, và gửi thất bại được ghi log
không kèm token.

## Bí mật

Token không bao giờ tới log: lỗi API được redact thành `<token>` trước khi raise
(kể cả URL tải tệp), và một logging filter xoá mọi token tiến trình đã dùng — của bot, token đã thay,
token chỉ kiểm tra từ Kết nối — khỏi các dòng request của `httpx`. Profile chỉ giữ tên env var,
ngăn cài đặt chỉ hiện có khoá hay không, và `agents/` là dữ liệu cá nhân nằm ngoài
repo này.

## Thêm kênh

Kênh nằm dưới `channels/`, được dựng từ một khối trên profile của master, và làm
ba việc: start, stop, và giao câu trả lời cuối của một cuộc trò chuyện. Bên trong, đưa mọi
tin nhắn tới cổng inbound thay vì gọi vòng lặp: đó là điều giữ cho agent
không biết tới nền tảng. Giữ bí mật dưới dạng tên env var trong profile, và test kênh ở
tầng có thể thấy nó ([testing.md](testing.md)).

## So với openclaw

Gateway của openclaw hỗ trợ nhiều kênh (Telegram, Discord, WhatsApp, …) với
quy tắc tuyến theo từng kênh, xử lý group và chặn theo mention. Ở đây có một loại kênh,
một chat, một người dùng và một agent ở cửa; tuyến giữa các agent là việc master
giao việc, không phải của kênh. Vậy là đủ cho trường hợp đang có (một người, vài
agent, một điện thoại) và giữ code kênh trong vài module ngắn.
