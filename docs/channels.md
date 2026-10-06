# Kênh

**Phiên bản**: 0.11.1 · **Cập nhật**: 2026-10-05

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

Đội vẫn tới được chat theo hai cách:

- **Bản tin theo lịch.** Sau một prompt job của bất kỳ agent nào, scheduler đưa câu trả lời cho
  kênh, kênh gửi nó với dòng đầu
  `[Agent name]`, các đường dẫn `MEDIA:` được giải trong workspace của *chính*
  agent đó, nên biểu đồ buổi sáng của HLV vẫn tới dưới dạng ảnh. Câu trả lời của chính master
  không có tiền tố.
- **Tệp đính kèm.** Ảnh hoặc tài liệu rơi vào inbox của **master**; master chuyển
  đường dẫn đã lưu vào task giao việc khi một thành viên đội cần đọc nó.

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
bot chết, và bản tin được giao mà run kết thúc rỗng cũng vậy. Câu trả lời gửi
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
qua Telegram hoặc xem lại sau) nên không thấy canvas mở ra bên cạnh; vì vậy system prompt của
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
  Lượt xong mà không có chữ nào nhưng có ghi canvas thì tin này là câu trả lời.

Link về web chỉ có khi `web_url` được đặt (xem
[deployment-guide.md](deployment-guide.md#4-biến-môi-trường-và-bí-mật)): mỗi canvas trong tin
thêm một dòng link tới trang riêng của nó, và caption của tệp cũng mang link ấy khi còn chỗ. Để
trống thì tin kết thúc bằng lời bảo mở web UI.

Job trả lời `OK` thì không gửi gì, kể cả khi nó vừa tạo hay vừa sửa canvas: tin liệt kê cũng
không tới chat. Canvas nó ghi vẫn nằm trong kho và mở được trên web.

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
| `/approve`, `/deny` | giải quyết duyệt đang chờ và stream phần còn lại của lượt về |

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

## Giao theo lịch

Sau mỗi prompt job, scheduler yêu cầu runtime giao cuộc trò chuyện đó, tức là
chuyển tiếp text của assistant ở lượt cuối tới chat khi master
có kênh. Bản tin của thành viên đội mang tiền tố `[Name]`; cuộc trò chuyện của
agent mà runtime không biết được ghi log và không gửi. Khi lượt cuối kết thúc mà không có text nào của assistant (run dừng ở
`max_steps` hay vì gọi lại y hệt một lệnh, lỗi provider, một duyệt còn treo) kênh gửi
thông báo "run chưa xong" kèm tóm tắt của run thay vì im lặng, nên
job theo lịch không bao giờ biến mất không dấu vết. Khi một duyệt trong lượt đó hết hạn
(`approval_ttl_seconds` của lịch, không có thì của `config.yaml`), phần giao nói trước tool nào bị từ chối vì quá hạn,
để câu trả lời theo sau được đọc là do hàng rào tạo hình, không phải do người.

Run dừng sớm nhưng *có* để lại text là trường hợp khó hơn: câu trả lời
nửa chừng đọc như một câu trả lời hoàn chỉnh. Nên sau khi gửi text, run có status `halted`
hoặc `error` nhận thêm tin nhắn thứ hai "bị cắt ngắn" nêu lý do và run đã tiêu bao nhiêu. Lý do
của run `halted` là mã vòng lặp ghi (`budget`, `max_steps`, `loop`), nên kênh đọc nó thành lời
("chạm trần chi phí", "hết số bước tối đa", "gọi lại y hệt một lệnh nhiều lần liên tiếp"); lý do
của run `error` đã là câu báo lỗi. Dù thế nào scheduler cũng ghi một dòng log cho mỗi prompt job —
`job <id>: delivered=<bool> conv=<id> status=<status>` — để log phân biệt job đã
trả lời với job im lặng. Giao thất bại được ghi log, không thử lại.

**Job không có gì để báo thì không gửi.** Một job kiểm tra (nhắc hạn, soát lỗi) có thể dặn
model trả lời đúng `OK` khi mọi thứ ổn; câu trả lời chỉ gồm `OK` (không phân biệt hoa thường,
bỏ qua dấu chấm/than cuối) thì không được đẩy lên chat, log ghi
`job <id>: nothing to report, not delivered`. Run vẫn nằm trong trang Jobs và rail hoạt động,
nên vẫn thấy job đã chạy. Câu trả lời dài hơn, kể cả bắt đầu bằng "OK, nhưng…", vẫn được gửi.

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
  được…". Server khởi động kế tiếp mở lại đúng run đó và bot đọc phần còn lại của lượt vào cùng
  chat, nên người dùng không phải gửi lại. Lượt chỉ được làm tiếp một lần, và không được làm
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
