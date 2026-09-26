# Kênh

**Phiên bản**: 0.8.0 · **Cập nhật**: 2026-09-26

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
→ 200 {"conversation_id": "…", "agent_id": "default", "text": "…", "status": "done", "steps": 2}
```

`channel` chọn cuộc trò chuyện theo ngày (`api:<something>` tách một relay khỏi
relay khác), `conversation_id` thì tiếp tục một cuộc cụ thể thay vào đó, và `source` là thứ run
hiển thị trong view hoạt động. 404 khi agent hoặc cuộc trò chuyện không tồn tại, 409 khi
cuộc trò chuyện đang chờ duyệt. `status` là `done`, `halted`, `error` hoặc
`approval_required`, và khi đó text kết thúc bằng thông báo tương ứng. Đây cũng là cách
test một tính năng đầu-cuối: một request, một câu trả lời, không cần trình duyệt.

## Cấu hình

Khối này đặt trên profile của **master**, `MY_AGENT_HOME/agent.yaml`:

```yaml
telegram:
  token_env: TELEGRAM_BOT_TOKEN   # NAME of the env var holding the bot token
  chat_id: 123456789                           # the only chat the bot answers
```

Cả hai key đều bắt buộc; `chat_id` là int. Bản thân token nằm trong môi trường của
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
agent có cuộc trò chuyện đang được gửi.

Ảnh hoặc tài liệu người dùng gửi được tải về (cỡ ảnh lớn nhất, hoặc tài liệu
dưới tên của nó rút gọn thành tên tệp thường) vào `<master workspace>/inbox/` dưới dạng
`<YYYYMMDD-HHMMSS>-<name>`, và text của lượt là `[Tệp đính kèm đã lưu: <path>]` với
caption đi sau. Model không thấy ảnh; persona của master
nói phải làm gì với đường dẫn, chẳng hạn đưa nó cho agent đọc bài báo.
Tải về thất bại được báo vào chat mà không có lượt model. Lệnh slash không được
đọc từ caption.

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

## Lệnh

Được kênh trả lời không cần gọi model, và đăng ký bằng `setMyCommands` một lần mỗi
tiến trình để client hiển thị chúng.

| Lệnh | Tác dụng |
|---|---|
| `/new`, `/reset`, `/start` | mở cuộc trò chuyện khác |
| `/help` | danh sách lệnh |
| `/status` | số lượt, chi tiêu so với trần, tuyến, duyệt đang chờ, run gần nhất (giờ bắt đầu theo múi giờ của người dùng, xem `timezone` trong [agents.md](agents.md#agentyaml); run được lưu theo UTC) |
| `/tools` | tên các tool của master |
| `/approve`, `/deny` | giải quyết duyệt đang chờ và stream phần còn lại của lượt về |

`/status@botname` dùng được; `/usr/bin` hoặc câu bắt đầu bằng `/` không phải lệnh và
đi tới model. Tin nhắn trong lúc một tool đang chờ duyệt nhận được lời nhắc thay vì một
lượt.

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
`max_steps`, lỗi provider, một duyệt còn treo) kênh gửi
thông báo "run chưa xong" kèm tóm tắt của run thay vì im lặng, nên
job theo lịch không bao giờ biến mất không dấu vết. Khi một duyệt trong lượt đó hết hạn
(`approval_ttl_seconds`), phần giao nói trước tool nào bị từ chối vì quá hạn,
để câu trả lời theo sau được đọc là do hàng rào tạo hình, không phải do người.

Run dừng sớm nhưng *có* để lại text là trường hợp khó hơn: câu trả lời
nửa chừng đọc như một câu trả lời hoàn chỉnh. Nên sau khi gửi text, run có status `halted`
hoặc `error` nhận thêm tin nhắn thứ hai "bị cắt ngắn" nêu lý do và run đã tiêu bao nhiêu. Dù thế nào scheduler cũng ghi một dòng log cho mỗi prompt job —
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
tin nhắn đang xử lý chạy xong, tối đa 30 s, để các tin nhắn xếp sau nó chưa xác nhận cho
bot tiếp theo, và chỉ trả về khi vòng poll đã kết thúc, nên
bot mới không bao giờ poll song song với bot cũ. Long poll đang rảnh bị cắt ngay. Lượt
vẫn chạy sau 30 s bị huỷ, và chat được báo ("…có thể chưa được trả
lời trọn vẹn… gửi lại giúp mình nhé") để người dùng gửi lại thay vì chờ câu trả lời
sẽ không tới. Nó nói "có thể": nhát cắt có thể rơi sau khi text của câu trả lời đã đi, trong lúc
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
