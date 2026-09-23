# Channels

A channel lets the person talk to the crew somewhere other than the web UI. Today that is
Telegram (`channels/`). Every platform hands a message to the same gate, `Inbound`
(`inbound.py`): it finds the agent, opens or reuses today's conversation on that channel,
runs the turn under activity tracking and returns the reply. Turns from Telegram therefore
run through the same loop as the web UI, with source `telegram`, so the rail shows them.

Telegram works the way the web UI does: **the person talks to the master** and the master
delegates to the crew (`delegate` tool, see [agents.md](agents.md#the-master-agent)).
There is no agent picker on the phone either, no `@id` mention and no per-agent bot.

A platform without an adapter of its own talks to the gate over HTTP:

```
POST /api/inbound {"text": "…", "agent_id"?: "default", "channel"?: "api", "conversation_id"?: "…", "source"?: "api"}
→ 200 {"conversation_id": "…", "agent_id": "default", "text": "…", "status": "done", "steps": 2}
```

`channel` picks the per-day conversation (`api:<something>` keeps one relay apart from
another), `conversation_id` continues a given one instead, and `source` is what the run
shows in the activity view. 404 for an unknown agent or conversation, 409 while the
conversation waits on an approval. `status` is `done`, `halted`, `error` or
`approval_required`, and the text then ends with the matching notice. This is also the way
to test a feature end to end: one request, one reply, no browser.

## Configuration

The block goes on the **master's** profile, `MY_AGENT_HOME/agent.yaml`:

```yaml
telegram:
  token_env: TELEGRAM_BOT_TOKEN   # NAME of the env var holding the bot token
  chat_id: 123456789                           # the only chat the bot answers
```

Both keys are required; `chat_id` is an int. The token itself lives in the server's
environment — `<home>/env`, which the server loads at startup and the web UI's **Kết nối**
page writes. Setting the block from the agent editor, or saving its token on Kết nối, rebuilds
the channel in place (`server/runtime_connections.py`); a hand edit of `agent.yaml` still
needs a restart. Only a change to the master, its token's value or its `chat_id` rebuilds
the bot; any other edit (a search key, a member's profile) hands the running bot the new
agents without stopping it. When the env var is unset the
server logs `agent default: env var <NAME> is not set; telegram channel disabled` and
starts without the channel; otherwise `telegram channel enabled for default`. A
`telegram:` block on a crew member's `agents/<id>/agent.yaml` is ignored with the warning
`agent <id>: telegram belongs to the master; its block is ignored` — the person has one
door to the crew, and a second bot would be a second door. Updates from any other chat are
ignored and logged.

## One bot, the master, the crew

`build_channel` builds one `TelegramChannel` for the master. Everything typed in the chat
is a turn of the master's conversation; when the answer belongs to Pong or the coach the
master delegates and relays, exactly as in the web UI, and the delegate's run shows up in
the manage screen's activity section under its own name.

The crew still reaches the chat in two ways:

- **Scheduled briefs.** After a prompt job of any agent the scheduler calls
  `Runtime.deliver`, and the channel sends that agent's reply under a first line
  `[Agent name]` (`texts.TELEGRAM_AGENT_PREFIX`), with `MEDIA:` paths resolved in *that*
  agent's workspace, so a coach's morning chart still arrives as a photo. The master's own
  replies carry no prefix.
- **Attachments.** A photo or document lands in the **master's** inbox; the master passes
  the saved path along in the delegate task when a crew member should read it.

Each turn's messages live in the master's conversation only: there is no per-agent
history on the chat to keep apart and nothing to share between agents beyond what the
master tells them in the task.

## Conversations

Each text message becomes a turn of the master's conversation for today on the channel
`telegram:<chat_id>` (title `Telegram · YYYY-MM-DD`, opened on first use each day, or with
`/new`). While the turn runs the chat shows "typing…" (`sendChatAction` every 4 s). The
reply is every assistant text of the turn joined in order, including text written next to
a tool call, plus halt, error and approval notices. A turn that ends without a single word
says so with the step count instead of sending nothing: silence is indistinguishable from
a dead bot, and the same holds for a delivered brief whose run finished empty. Replies go
out as plain text in
4 096-char chunks; a `MEDIA:<path>` line becomes `sendPhoto` from the workspace of the
agent whose conversation is being sent.

A photo or a document the person sends is downloaded (largest photo size, or the document
under its own name reduced to a plain file name) into `<master workspace>/inbox/` as
`<YYYYMMDD-HHMMSS>-<name>`, and the turn's text is `[Tệp đính kèm đã lưu: <path>]` with the
caption after it (`telegram_inbound`). The model does not see the image; the master's
persona says what to do with the path, such as handing it to the agent that reads papers.
A download that fails is reported to the chat without a model turn. Slash commands are not
read from captions.

Several photos sent at once arrive as one update per photo sharing a `media_group_id`, the
caption on the first only. `telegram_albums` gathers consecutive updates of one album into
one turn whose text lists every saved path, then the caption; a poll that ends inside an
album asks Telegram again up to three times, one second apart, before handing the agent a
half album. The offset moves past the whole group at once, so a crash mid-album repeats
the album rather than splitting it.

A new conversation does not start blank: the summary of the previous conversation on the
same channel is carried into the prompt as a **Cuộc trước** section
(`previous_for_channel`), so `/new` and the first message of a new day pick up where the
last one left off without replaying its messages.

## Commands

Answered by the channel without a model call, and registered with `setMyCommands` once per
process so the client shows them.

| Command | Effect |
|---|---|
| `/new`, `/reset`, `/start` | open another conversation |
| `/help` | the command list |
| `/status` | turns, spend vs cap, routes, pending approval, last run (start time in the person's zone, see `timezone` in [agents.md](agents.md#agentyaml); runs are stored in UTC) |
| `/tools` | the master's tool names |
| `/approve`, `/deny` | resolve the pending approval and stream the rest of the turn back |

`/status@botname` works; `/usr/bin` or a sentence starting with `/` is not a command and
goes to the model. A message while a tool waits for approval gets a reminder instead of a
turn.

A question the agent asked with `ask_user` is the one pause that does not work this way.
`/approve` and `/deny` are refused on it, because there is nothing to authorise: what is
missing is a sentence only the person can write. So while a question is open the next
ordinary message from the owner is read as the answer rather than as a new request. A bare
number picks that choice out of the numbered list the question was sent with — `2` on a
`1. có / 2. không` question answers `không` — and anything else is passed through as words,
including a number the list has no entry for and a sentence that merely begins with one.
This is how a chat stands in for the web's question card; see
[Asking the person](tools.md#asking-the-person).

## Scheduled delivery

After every prompt job the scheduler calls `Runtime.deliver(agent_id, conv_id)`, which
forwards the assistant text of that conversation's last turn to the chat when the master
has a channel. A crew member's brief carries the `[Name]` prefix; a conversation of an
agent the runtime does not know is logged and not sent. When the last turn ended without any assistant text (a run halted at
`max_steps`, a provider error, an approval left pending) the channel sends
`texts.TELEGRAM_RUN_UNFINISHED` with the run's summary instead of staying silent, so a
scheduled job never disappears without a trace. When an approval in that turn timed out
(`approval_ttl_seconds`), the delivery first sends `texts.TELEGRAM_APPROVAL_EXPIRED` naming
the refused tool, so the reply that follows is read as one shaped by a guard, not by the
person.

A run that stopped early but *did* leave text behind is the trickier case: the half-finished
answer reads like a complete one. So after sending the text, a run whose status is `halted`
or `error` gets a second message, `texts.TELEGRAM_RUN_CUT_SHORT`, naming the reason and what
the run spent. Either way the scheduler logs one line per prompt job —
`job <id>: delivered=<bool> conv=<id> status=<status>` — so the log distinguishes a job that
answered from one that stayed quiet. A failed delivery is logged, not retried.

## Offsets and restarts

The `getUpdates` offset is written to `MY_AGENT_HOME/telegram.offset` before each update is
handled, so a message that crashes the handler is not replayed forever. A `409` from Telegram means another process still polls the bot (an old server, another
tool); the channel logs `another poller holds this bot` and retries every 5 s.

Stopping the bot while the server runs (a rebuild after its token or chat changed) lets the
message in hand finish, for up to 30 s, and returns only once the poll loop has ended, so the
new bot never polls alongside the old one. An idle long poll is cut off at once. The loop and
its stop live in `channels/telegram_polling.py`.

## Secrets

The token never reaches logs: API errors are redacted to `<token>` before they are raised
(the file-download URL included), and one logging filter scrubs every token the process has used — the bot's, a replaced one,
one only checked from Kết nối — from `httpx` request lines. Profiles hold env-var names
only, the settings drawer shows key presence only, and `agents/` is personal data outside
this repo.

## Adding a channel

A channel is a class with `start()`, `stop()` and `deliver(conv_id) -> bool`, built in
`channels/build_channel` from the master's profile block and held as `Runtime.channel`.
Inside, hand every message to `Inbound.conversation_for` + `Inbound.reply` (or `stream`
when the platform can show events) rather than calling the loop: that is what keeps the
agents unaware of platforms. Keep secrets as env-var names in the profile and add rows to
[testing.md](testing.md). Tests: `test_channels_telegram.py`, `test_app_wiring.py`,
`test_api_inbound.py`.

## Compared with openclaw

openclaw's gateway supports many channels (Telegram, Discord, WhatsApp, …) with
per-channel routing rules, group handling and mention gating. Here there is one channel
type, one chat, one user and one agent at the door; routing between agents is the master's
delegation, not the channel's. That is enough for the case at hand (one person, a few
agents, one phone) and keeps the channel code to a handful of short modules.
