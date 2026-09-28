---
layout: default
title: Changelog
---

# Changelog

All notable changes to my-agent-crew. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [SemVer](https://semver.org/). One version number for both backend and web: within a
single release, `pyproject.toml` and `web/package.json` always carry the same number.

## [0.9.2] — 2026-09-28

A one-fix release: a delegated answer that ended on a bare chart line reached the person as the
chart alone. The advice it illustrated now arrives with it.

### Fixed

- A delegated agent that writes its answer next to a tool call and ends on a bare `MEDIA:` line no
  longer hands on only the chart. The child's answer is the last thing it said before the
  attachment lines, with them added, so a relayed reply carries the advice as well as the picture.

### Upgrade notes

- No migration and no new configuration. Restart the server to load the fix.

## [0.9.1] — 2026-09-28

A follow-up to 0.9.0 that closes what its reviews left open: the manage screen says when it lost
the server, images from other sites wait for a tap, failed requests read as sentences, every phone
control is big enough for a finger, and an autonomous wiki compile no longer races a decision made
on the web.

### Added

- **The manage screen says when it stopped following the server.** Its lists and counts come from
  the live stream, so a dropped stream now puts a notice at the top of every section with a retry,
  a browser gone offline says that instead, and the crew is read again once the stream is back.
- **An image from another site loads only when asked.** A reply or wiki page that links one shows
  a button naming the host in its place, so opening a conversation no longer tells a third party
  it was read.

### Fixed

- Every control on a phone has a touch area of at least 40px.
- A failed request is put in words (no network, a server error, gone, refused) instead of the
  server's validation dump or the browser's own error.
- A reconnect looks for a newer build only when no look since the drop has reached the server.
- A phone's activity strip stays up when a retry finds the conversation never ran, so the focus
  handed to its line does not vanish with it.
- Exporting a conversation closes raw HTML a reply was cut off in, so it cannot swallow the turns
  after it.
- An expired request still open on the server is read less often the longer the server's sweep
  keeps it.
- The restart reason for a schedule reads right for a removed schedule too, and each side keeps
  one copy of it.
- The approval history is read again when a decided request's run goes on to wait on its next
  tool, not only when a run settles.
- An autonomous agent's wiki compile writes under the same one-decision-at-a-time rule as the web,
  and leaves alone a proposal someone decided first; it and the memory rewrite wait for that rule
  off the event loop, so a decision still writing no longer stalls the server.

### Upgrade notes

- No migration and no new configuration. Restart the server to serve the new bundle; an open
  page offers the reload itself.

## [0.9.0] — 2026-09-28

This release is about acting where the person already is. A waiting request is approved, denied
or answered from the manage screen's Duyệt page, a spent cost cap is raised from the chat, the
agent editor saves schedules, and a tool call's arguments can be read whole before it is allowed.
The chat stops a turn honestly, follows runs other channels start in it and says when its live
stream is down; replies can be copied, shared and exported, and the conversation list groups by
day with unread dots and drafts. Run history, jobs, memory proposals and wiki pages read as
sentences, diffs and rendered pages instead of raw codes, an open page offers a reload once the
server runs a newer build, and a run paused for approval survives a server restart.

### Added

- **Raise or lift a conversation's cost cap from the chat.** The budget pill's card and both
  budget notices carry an editor for the cap: +$0.50 and +$1 steps, or a typed amount where 0
  lifts the cap. A spent budget now locks the composer and says so, since the server would halt
  the turn before it started; a raise unlocks it without a reload and puts the keyboard back on
  the composer. Only one notice offers the raise at a time, a halted turn's notice then says the
  new cap is saved and to send the message again, and a refused save says why.
- **Approve, deny or answer waiting requests from Duyệt (approvals).** Every request waiting on
  the person is listed above the approval history, with its approval bar or question card inline
  and a "còn m:ss" countdown, so it is decided without opening the chat. Deciding reads the resumed
  turn to its end; the row then leaves, or shows the next request when the turn pauses again, and
  the history below reads again whenever a request may have settled. At the deadline the row
  disables, says it expired and keeps reading the request until the scheduler's sweep closes it.
  The tab title carries the number of waiting requests as "(N)", the installed app's badge shows
  it where the browser allows, and the manage screen opens on Duyệt while one waits.
- **The agent editor saves schedules.** A row is one timing (a cron or an interval) and one action
  (a prompt or a command), and only the keys chosen are sent, so a new schedule is no longer
  refused for the derived `kind` and empty keys it carried. A cron, interval, prompt or Telegram
  chat id that cannot be sent is named beside its box and holds the save, a valid timing is read
  back in words, and a new row takes an id no kept row carries. Memory consolidation's cron is
  editable, and emptying it removes the key. The jobs list opens the editor on an agent's
  schedules, and the way back returns to that job's row. A save no longer breaks the form it came
  from, because the answer now carries `declared` (see Changed); against an older server that
  leaves it out, the editor reads the crew again instead.
- **A tool call's full arguments, before deciding it.** The one-line summary cuts every value at
  sixty characters. A closed "Xem đầy đủ" under the approval bar, each tool card and each approval
  history row now shows every argument whole: a command, file content, an edit's old and new text
  and any other value spanning lines as wrapped text, the rest as JSON. It is offered only when the
  summary hides something, and the chat's request card scrolls within 55% of the screen's height,
  so its buttons stay in view on a phone. The approval history also reads a question as what was
  asked, the options offered and the answer, and pages with "Xem thêm" from 50 to 200 to 500 rows.
- **Stop is honest, the thread stays fresh and a dropped stream says so.** Stop also cuts the
  stream of a decision or an answer, drops what the cut stream still delivers and says the turn
  stopped; a call left spinning when a turn ends, or when the live stream reports nothing running,
  reads as stopped. A run another channel such as Telegram starts in the open conversation,
  including one already going when this tab sends, shows its progress in the thread, which reloads
  once when that run ends or pauses; a message sent while the thread reloads is kept. The status
  line says when the live stream is connecting, lost or offline and offers a retry once the browser
  has given up, and runs that ended while the stream was down are caught up on when it returns.
- **Copy, share and export replies; see the files sent through Telegram.** Each agent reply has a
  copy button, and a share button where the platform has a share sheet, both taking its raw
  markdown; each fenced code block has a copy corner that takes only the code. Where the clipboard
  is missing or refuses, as on the LAN address over plain http, the text opens selected in a box to
  copy by hand, and the agent editor's prompt copy now falls back the same way. The conversation
  options export `<title>.md`: a heading per turn, times that name their time zone, and each
  message kept inside its own turn, down to the headings and code blocks in its lists and quotes.
  A file the person sent through Telegram shows in their bubble
  as a thumbnail or a named download chip served from the agent's files route, and a fence with no
  language renders as a code block.
- **The conversation list groups by day, marks unread and keeps drafts.** Rows fall under Hôm nay,
  Hôm qua and Cũ hơn on the viewer's calendar and say how long ago each changed, kept current while
  the tab idles. A row that changed since this browser last had it open gets an unread dot: a first
  visit counts everything as read, tabs merge what each has seen, and delegated conversations never
  get one. The status dot's tooltip is Vietnamese, and the dot pulses while a run is live. The
  composer keeps an unsent draft per conversation across switches and reloads; sending clears it
  and deleting the conversation drops it. Refused storage leaves both working for the page's life.
- **Slash commands from the composer.** A "/" at the start of the box lists the commands the
  agent's kits declare, narrowed by prefix and then by substring as the name is typed; arrows with
  Enter or Tab, or a tap, put "/name " in the box, and Esc closes the list. A "/" button beside Send
  opens it too. The list shows only while the composer has the focus, and an agent without
  commands shows neither.
- **Stored run history with filters.** An open conversation's activity loads its stored runs,
  delegated children included, under the live ones, so runs from before the page opened show, and
  each delegate sits under the turn that asked for it. The activity log loads its own history: the
  agent chip asks the server for that agent's runs, the status and source chips narrow what is
  loaded and are remembered by the browser, and "Xem thêm" reaches back 100, 200 and then 500
  runs. On a phone the chips fold behind one "Lọc" toggle. A history still loading, or one that
  failed to load, says so, with a retry.
- **Tokens, cache hits and time to first token.** A finished model step shows its route, the wait
  for its first token, its prompt tokens with the part the provider served from its cache, and
  whether it thought first. The costs page gains today and seven-day tiles on the viewer's calendar
  that flag unpriced calls, a cache column with its share per model, a cache-by-agent card counted
  over the same runs as the spend by agent, and a label on every card saying what it counts; it
  fits a phone at 390px.
- **Memory proposals are reviewed as diffs and exact facts.** A rewrite shows the lines it drops
  beside the ones it adds; a forget names the fact it removes and asks before approving; a fact
  that overwrites a saved one shows what it replaces, matched whatever case the agent wrote the name
  in, and saved facts that could not be read are said to be unknown rather than absent. A wiki
  compile shows one card per page, tagged new or updated. Both buttons disable while a decision is
  in flight, a proposal decided elsewhere says so in place and the list reloads, and a failed undo
  is reported.
- **Wiki pages read as pages.** A page opens as rendered markdown. Each [[link]] is slugged as the
  server slugs titles and opens its page at the title; a link to a page nobody has written is drawn
  as missing, and related pages are chips. "Đánh dấu ổn" marks a page fine with a status-only PUT.
  The vault header lists every page's open questions, each leading to the page that asked it, and
  today's note on the viewer's own date. Leaving an unsaved edit, or closing today's note over an
  unsaved line, asks first. Starting a compile or a consolidation shows a chip that follows its
  run, across a dropped stream too, then says how it ended and reloads what it may have changed.
- **Jobs read at a glance.** Common cron shapes (daily, weekdays, weekends, a set of weekdays,
  hourly, every N minutes or hours, a day of the month) and the `every` shorthand read in
  Vietnamese with the cron beside them. The next run counts down and the last run says how long
  ago, each followed by its clock time on the viewer's clock and kept current, also when the tab
  comes back; a paused or switched-off job says so where the next run goes. The last run shows its
  status and summary with a link to its replay, and the Lịch chạy (jobs) entry in the nav carries a
  red count, read out as a sentence, only while some job's last run failed.
- **A reload is offered when the server runs a newer build.** An open page, an installed app above
  all, compares the hashed entry script it runs with the one the server's index serves, on focus,
  when the tab comes back and after the live stream reconnects. When they differ, a floating
  "Có bản mới" bar offers a reload and can be put away until a later look still finds another
  build; a failed look shows nothing, and the dev server never shows it. Settings names the
  server's build and, once a look finds the server serving the page's own entry, the page's too,
  asking again each time it opens.
- **Why a run stopped reads as a sentence.** The server ends some runs with a code: `budget` or
  `max_steps` on a halt, `interrupted` on a turn nobody kept reading. The timeline and the
  attention center read each as a sentence, only under the status that writes it, so a reply that
  happens to be the word "budget" still reads as the reply.

### Changed

- **Duyệt and Hoạt động split what needs the person.** Duyệt's badge counts only the requests
  waiting on a decision. Hoạt động (activity) counts the failures and halts until each is marked
  "Đã xem", which the browser remembers, and its live count leaves out runs that only wait. Each
  page points to the other when that one has something for the person.
- **Saving an agent answers with the agent as the crew list shows it.** `POST /api/agents` and
  `PATCH /api/agents/{id}` return `profile` in the shape of a `GET /api/agents` entry: it gains
  `declared`, `editable`, `tools` and `skills`, and its `delegates` is who the agent can reach,
  with what its file names under `declared.delegates`.
- **A profile edit's new or changed schedules must be ones the clock can run.** The edit routes
  answer 422 when a schedule the edit adds or changes has a cron or interval the scheduler cannot
  read, or shares its id with another schedule, the consolidation job's included; before, the
  second job on an id silently replaced the first. Rows the agent already runs with are not checked
  again, so a hand-written profile holding such a row still takes unrelated edits, and boot still
  takes a file as it is.
- **`/api/stats` totals each agent's prompt cache.** `cache_by_agent` gives each agent's
  `prompt_tokens` and `cached_tokens` over the same runs as `by_agent`, from the calls that reported
  both, and `unknown_cache_calls` counts the calls that reported prompt tokens but no cache figure.
  The costs page's cache card reads them instead of fetching the 500 newest runs itself.
- **A pending request read back says why it paused.** `pending_approval` in
  `GET /api/conversations/{id}` carries `reason`, the line naming the ask pattern that stopped a
  shell command, worked out again from the stored call and the agent's ask list as for the live
  event; it is empty when no ask pattern played a part. The chat and the Duyệt row now show it for
  a run that paused while nobody was watching.
- **A memory proposal decision answers by what went wrong.** `POST /api/memory/proposals/{id}`
  answers 409 "proposal already decided" only for a proposal no longer pending,
  404 "proposal not found" for an unknown id, and 404 "agent not found" for a pending proposal
  whose agent has left the crew, which used to be a 409 although the proposal can still be
  rejected. Decisions are taken one at a time, so of two sent together the second gets the 409.

### Fixed

- **A run paused for approval survives a server restart.** Deciding its request after a restart
  continues that same run instead of opening a second one beside it, while the old paused row
  stayed waiting for good and every screen that counts runs kept counting it. A paused run nothing
  can continue any more, because its request was settled while no process held it or its
  conversation was deleted, is closed as interrupted, and a tool step resumed after a reboot never
  reports a negative duration.
- **Deleting a conversation paused on an approval ends its run at once.** Its request goes with it,
  so `DELETE /api/conversations/{id}` closes that run as interrupted instead of leaving it waiting.
  Naming a new conversation waits for its first turn to end, and one deleted or renamed by hand
  meanwhile is no longer named by a paid model call; a delegating agent waiting on a deleted child
  reads that the person deleted it, instead of a bare "KeyError".
- **The agent editor's pinned bar sits flush against the top of the page.** It stopped at the
  page's top padding, 32px down on a wide screen and 16px on a phone, and the form scrolled past
  visibly in the strip above it.
- **A run waiting for approval reads as waiting, not running.** The sidebar's status dot, the
  chat's manage button, the status line, the master's card and the crew page each took a paused
  run for a busy one, so the one state in which the person has to act read as the agent working.
  When a conversation holds two open runs, the one waiting on the person sets its dot.
- **A question that pauses while the page is open reads as a question.** The page's live copy of
  the run called it a permission request named ask_user until the list was read again; it now says
  the agent is asking, as the server does.
- **A decision someone already took elsewhere reads as handled.** In the chat, a decide or answer
  that meets a 409, because another tab, Telegram or the expiry sweep settled the request first,
  reads the conversation again and says the request was handled, not that the agent is busy, and
  no longer marks the resumed call as stopped. The note stays when the thread is read again for the
  run that decision resumed or for a live stream that reconnects; a new turn, a new request or
  opening another conversation clears it.
- **A slow load of the conversation just left no longer lands on the one opened.** Its messages,
  approval bar and spend showed under the other conversation's heading; each opening now takes only
  the loads, refused decisions and notes made for it.
- **A memory proposal is decided once.** An approval arriving after the proposal was decided, from
  a stale tab or a second click, wrote the memory before learning it was no longer pending, so a
  rejected fact was written or an agent memory line appended twice, and an approval and a rejection
  sent together from two devices could both find it pending. The status is now checked before
  anything is written, and one lock holds the check, the write and the resolve together.
- **An agent's runs are no longer crowded out by a busier agent's.** `GET /api/activity/runs` with
  `agent_id` cut the whole crew's newest runs to `limit` before narrowing, so a quiet agent showed
  few runs or none; the narrowing now happens in the query, and `limit` counts that agent's runs.
- **Background bookkeeping no longer dates a conversation as new.** The recap written when the
  next conversation opens, and the model's title with its cost, moved `updated_at`, so the old
  thread jumped above the new one; they now leave it alone, and every other write still moves it.
- **The agent editor shows the server's restart reasons as the sentences they are**, after the
  saved note, instead of setting each inside a sentence of its own as if it named a changed key.
- **On a phone, the current manage section's pill stays in view** when the badge counts arrive
  after the first paint and widen the row. A row the person has scrolled the pill out of stays
  where they left it, so a count arriving mid-swipe no longer slides another section under their
  finger.
- **Runs that started in the same second are listed the same way everywhere.** Start times are
  whole seconds, and each list put such runs in whatever order its sort happened to leave them,
  or in the order the store last saved them: the chat's activity line could name one run as the
  last while the card under it showed another, the chat's cards and line moved on to another run
  once the stored history arrived, and a request just decided on Duyệt dropped below another
  request from the same second while its turn resumed, sliding that request's buttons under the
  pointer. Of runs that share a second, one still going now comes first, then the one that ended
  later; the rest keep the order the page heard of them, newest first, and a decided request
  stays where it was listed.

### Upgrade notes

- **No migration needed.** The SQLite schema, `config.yaml` and `agent.yaml` keep their shape, and
  no API route is added or removed; upgrading is pulling the new code and restarting the process.
  The web bundle is committed, so running the server needs no npm step.
- **The first start closes the paused runs nothing can continue.** Rows an earlier version left on
  `awaiting_approval` across restarts are closed as failed with the summary `interrupted`, except
  the newest paused run of each conversation whose request still waits, which a decision now
  continues.
- **Reload pages opened before the upgrade once.** A page or installed app from an earlier version
  cannot notice a new build; after one reload it offers the next one itself.
- **Check clients other than the bundled web against Changed.** A saved agent's `delegates` now
  lists who it can reach, a proposal decision answers 404 "agent not found" where it answered 409,
  and a profile edit can be refused with 422 over a schedule it adds or changes.
- **Contributors running e2e from two checkouts** give each its own port with
  `E2E_PORT=<port> npm run e2e`; on one port the second run reuses the first one's dev server and
  quietly tests the other checkout's code. Vitest and Playwright both run in the Asia/Ho_Chi_Minh
  time zone, so a test about days is written in that zone and sets no `TZ` of its own.

## [0.8.0] — 2026-09-26

This release is about the interface. The web UI is redesigned end to end on one scale of tokens,
with bundled Inter, line icons and a brand mark that is also the installed app's icon; it installs
as an app, and on a phone the conversation takes the whole screen with the list in a modal drawer.
It also makes the activity view tell the truth about a run: a run that just started or resumed
after an approval no longer crashes the page, a route that fails over leaves no model step open,
and a run stopped for approval says it waits for the person.

### Added

- **The web UI installs as an app.** The page links a web manifest, an SVG favicon and PNG icons
  (192, 512, a maskable 512 and an apple-touch icon), all drawn from the one brand mark by
  `npm run icons`. The browser chrome takes the page's own background in light and in dark.
- **The README opens with a picture of the interface**, a desktop conversation beside a phone in
  dark mode (`docs/images/web-ui.png`).

### Changed

- **The web UI is redesigned end to end, keeping its blue and its layout.** One scale of type,
  spacing, radius and shadow tokens replaces ad-hoc values; Inter is bundled (no CDN) with its
  Vietnamese subset; one set of line icons replaces emoji, which drew differently on every
  platform. A brand mark heads the sidebar and the welcome screen, and each agent has an initial on
  a tile of its own stable hue in the sidebar's master card, the conversation header, the thread,
  delegate cards, the crew and jobs lists and the agent editor. Each reply in the thread is headed
  by the agent's name and avatar instead of "Agent", and your own messages no longer carry a
  visible "Bạn" label. Dark mode follows the operating system on every surface.
  Text on the primary button, filled badges, channel tags and sunken surfaces holds 4.5:1 in both
  modes, which is why the button and badges keep the brand blue as their fill in dark mode too;
  checkboxes, switches and fields keep a visible focus ring. A browser test measures both. Most
  fields, the composer and the memory editor included, stay at 16px so an iPhone does not zoom
  into them.
- **On a phone the conversation takes the whole screen.** The conversation list slides in over it
  from a menu button and closes on Escape, on a tap outside or once a conversation is picked,
  handing focus back to the button. While open it is modal: the chat under it is inert, and
  Escape closes the list without also collapsing the activity strip beneath. ⌘K opens it at the
  search box, and the menu button's name says how many runs are waiting, as its dot does. The
  manage screen's sections become a row of pills that brings the current one into view. On a
  touch screen, where nothing can hover, every conversation row shows its delete button.
- **Empty and quiet states say where the person is.** Empty activity, approvals, costs and jobs
  sections show their own icon; the "Cần bạn xử lý" card stays grey until something waits; an
  expired approval is grey rather than amber, which is kept for a refusal and for a request still
  waiting.
- **The agent editor's pinned bar now shows the agent's avatar** next to its name. The unsaved
  count and the save controls sit together as one group, with Save styled as the primary button,
  and the group moves onto a second line on a phone. The tools matrix is a card with two-line
  descriptions and a coloured legend.
- **A section that fails to render no longer takes the manage screen with it.** Each page has its
  own error boundary, so the navigation stays and moving to another page leaves the failure
  behind; the failure itself is a card with the error and a reload button. The chat screen has a
  boundary too, so a crash outside its thread and activity column shows that card instead of a
  blank page.
- **The composer names the agent it writes to and grows with the message.** Once the agent is
  known, the empty box reads "Nhắn cho <agent>…" and no longer spells out the Enter / Shift+Enter
  keys. It starts at one line and grows to about ten lines before it scrolls. Send and Stop are
  round icon buttons that keep their names for screen readers. An input method commits a word
  with Enter instead of sending half of it, including the Enter that Safari delivers just after
  the composition has ended.

### Fixed

- **A route that fails over no longer leaves a model step open on a run that recovered.** The
  step the request opened stayed ahead of the fallback, so a finished run showed a model that
  never answered. The failed attempt's wait is now the fallback's duration, the model step times
  the next route, and when every route fails no model step is left waiting. A run stored before
  this shows such a step as "Mô hình", where 0.7.0 labelled it "?". The live page keeps the same
  order.
- **The activity panel no longer crashes on a run that just started.** The "run started" payload
  shared the run's live step list, so by the time a watcher serialised it the model call that opened
  next was already in it: half-built, with an internal clock field and no cost. The page then added a
  second model step when the answer landed, and drawing the first one failed on its missing cost. A
  run is now sent as a copy without the builder's private keys. The page also completes a model call
  that a snapshot caught mid-answer rather than duplicating it, shows it as "Đang suy nghĩ" until the
  answer lands, and, like the server, adds no model step for a child's answer that was relayed whole.
- **Opening a run whose tool result arrived without its call no longer breaks the page.** A turn
  that resumes after an approval receives the result while the call was recorded on the run that
  paused, so the server opens that step with no arguments. Expanding such a run, on the activity
  list or its own page, read the missing arguments and took the screen down; the step now shows "—"
  where the arguments would be.
- **A run stopped for approval says so in its progress header.** The model step before the pause
  had answered, so the header fell through to "Đang suy nghĩ" and kept its shimmer while nothing
  was running; it now reads "Đang chờ bạn duyệt" and drops the shimmer. Its card no longer wears
  the "Đang chạy" pill beside its own "chờ duyệt" either.

### Upgrade notes

No migration needed. The SQLite schema, `config.yaml` and `agent.yaml` keep their shape, and no API
route changes: upgrading is pulling the new code and restarting the process, which picks up the
run-step fixes. Runs stored before the upgrade keep the steps they were recorded with (see Fixed).
The web bundle is committed, so running the server needs no npm step. A contributor who rebuilds it
runs `npm ci` in `web/` first, because the bundled Inter font comes from the new
`@fontsource-variable/inter` dependency.

## [0.7.0] — 2026-09-26

This release is about the time between a question and its answer. Model calls are timed from the
request and the prompt cache hit is visible per message and per day; the stable part of the system
prompt stays stable so that cache holds; a delegated answer reaches the person in the child's own
words without a model call to retell it, and a child is told to conclude before it runs out of
steps. A benchmark script measures candidate models on the real agent loop, on an isolated server.

### Added

- **Model calls are timed from the request, and the cache hit is visible.** A run's model step opens
  when the request leaves and records `first_token_ms` when the first chunk of any kind arrives, so a
  tool-only answer no longer shows as 0 ms. Each assistant message keeps the prompt tokens the provider
  served from its cache (`cached_tokens`, a new column), and `/api/stats` sums them per day and per model.
- **Pin the upstream behind OpenRouter.** `openrouter_providers` (or `MY_AGENT_OPENROUTER_PROVIDERS`)
  names the providers to try in order and `openrouter_provider_fallbacks: false` forbids any other, so a
  prompt cache built on one upstream is not lost to a silent switch.

- **`scripts/llm_bench.py`** benchmarks candidate models on the agent loop itself: each model gets a
  throwaway home, its own server and port, no Telegram token and no live routes; five tasks (a bare
  reply, write-then-read, a shell command, a delegation, a document summary) are scored and timed.
- **A delegated answer is handed on whole.** When a turn was one `delegate` call and nothing else and
  the child finished, the child's answer becomes the reply, with its charts and files, instead of
  costing one more model call to retell it. The relayed message carries no provider or model and adds
  no model step to the run. The delegator can keep the last word with `relay: false` on the call; a
  child that stopped short, answered nothing or reported `BLOCKED` still goes back through the
  delegator, as do turns with more than one tool call.
- **A delegated child is told to conclude before it runs out of steps.** From its 25th model call
  (or one before its own `max_steps`, whichever is lower) the child gets a wrap-up note and no tools,
  so what comes back is an answer rather than a halted fragment. The note is stored in the child's
  conversation. A turn the person started keeps its tools to the hard cap as before.
- **The frame asks for independent tool calls in one turn.** Two reads or two lookups that do not
  depend on each other cost one model round-trip when the model batches them; the system prompt now
  says so, in Vietnamese and English.

### Changed

- **The prompt prefix stays the same between turns.** Everything that changes from one turn to the
  next — the previous conversation's summary, the daily notes and the date — now closes the system
  prompt instead of sitting among the persona and memory sections, so a provider's prompt cache keeps
  the stable part. A delegated child is not told about its master's previous conversation, and stale
  tool outputs are stubbed a block of ten at a time rather than one per step, so the set of stubs
  changes once per block instead of on every step. A new web chat looks past delegated children when
  it picks the conversation to recap.
- **`fetch_url` gives up sooner.** The connection gets 5 seconds and each read 10, and the body is read
  only up to 512 KB before the socket closes, instead of one 20-second budget and a whole download.

- **Everything but the model call got faster.** SQLite runs in WAL mode with `synchronous=NORMAL`, the
  hot queries have indexes, and writes read their own row back in one statement, so appending a message
  costs one commit instead of five statements and an fsync. The activity hub no longer writes the run and
  wakes every watcher on each streamed token; runs are stored and broadcast at step boundaries, and a
  watcher that stops reading is cut off instead of growing without bound. Wiki pages are parsed once per
  change on disk rather than once per system prompt, `/api/stats` is recomputed only after a write, and
  the PDF libraries load on first use instead of at start-up. The web bundle is split into React, vendor
  and app chunks with content hashes, served gzipped with an immutable cache header, so a release that
  only touches app code leaves the other two cached.

### Upgrade notes

- **`messages` gains a `cached_tokens` column**, added automatically at start-up like every schema
  change so far. Back the database up before the restart that applies it, as usual.
- **A single delegation now answers in the child's words.** A master persona that told the model to
  "summarise what the specialist said" no longer gets that call; write the child's persona so its
  last answer reads well for the person (the delegated-turn frame already says so), and use
  `relay: false` on the call where the master must keep working after the child returns.
- **A delegated child stops taking tools at its 25th model call** (or one before its own `max_steps`).
  A child that legitimately needs more should get a higher cap only if its `max_steps` is above 26,
  since the soft cap is the lower of the two.

## [0.6.0] — 2026-09-25

This release lets an agent work unattended inside someone's repository without being able to change it, makes
the master hand work to the crew the way one would to a person — the question as asked, no invented paths, no
borrowed permissions, and the result (charts included) carried back whole — and moves connection keys and the
model route into the web UI.

### Added

- **Per-agent reasoning effort.** `reasoning: minimal | low | medium | high` in an agent profile goes to
  every route the agent may fall back to and reaches OpenRouter as `reasoning.effort`. While the model thinks,
  the web status says so, the run's model step counts the silent part, and messages keep the reasoning token
  count without the thoughts themselves.
- **Manage connections from the web.** Manage → Connections sets, replaces, tests and removes API keys, host
  addresses and the Telegram bot token; written to `<home>/env` and applied immediately, no restart.
  A change that would leave the crew unable to run is rejected before it is written.
- **Edit the shared model route on the Connections page**, saved to `config.yaml` with comments
  preserved. Read-only while `MY_AGENT_ROUTES` is set, because the variable wins over the file. `fake` is not
  added to a crew that does not already use it; a new row defaults to the first real provider.
- **Test Tavily and Brave keys.** Tavily asks `/usage` (free, and reports the number of calls used);
  Brave runs one search for 1 result, and the button says plainly that it costs one call. Quota exhausted (429) is
  reported differently from a wrong key.
- **`write_paths` in an agent profile** confines `workspace_write` and `workspace_edit` to the listed
  paths inside the workspace. A write elsewhere is refused with an error naming the allowed paths, and no
  directory is created. Meant for autonomous agents whose workspace is a git repo.
- **`shell_deny_patterns` in an agent profile**: commands containing one of the listed fragments (case-insensitive
  substring, like `shell_ask_patterns`) are refused outright, with no approval asked, since nobody may be there to
  grant one in a delegated or scheduled turn. Meant for keeping an agent that works in someone's repo away from
  DDL, raw SQL writes and inline interpreters (`create table`, `python3 -c`). A soft guard like the ask list.

### Changed

- **Domain records go to the agent that keeps them.** The master's crew roster says a fact the person
  reports in a crew agent's domain (a meal, a drink, an illness, a payment, a document), or asks to be saved,
  is handed to that agent to record, and a question about its cause is handed back with the new fact rather
  than answered by guesswork. `memory_save` and `user_memory_save` say they are not a substitute for that
  agent's records.
- **Delegation hands over intent, not method.** The `delegate` tool and the master's crew roster ask for the
  person's words and today's date, never an invented file, folder or table; the roster no longer lists each
  agent's workspace. A delegated turn's system prompt says the task was written by the coordinating agent
  and that the agent's own conventions win, so a path named in the task is not a file to create.
- **A delegated task grants no permissions.** The tool description, the roster and the delegated turn's prompt
  all say a question is asked and answered, not acted on, and that a new table, a schema change, code or
  config needs the person's explicit consent — a permission the task grants itself is not theirs. The
  always-on `delegation` skill now teaches the same contract; its per-file split applies only to coding work.
- **`shell_write_paths` confines an agent with the network on, too.** Set, every `shell_run` command runs under
  `sandbox-exec` writing only there and in temp, and without `open`/`launchctl`/`osascript`, so an agent can fetch
  and record data but cannot edit the code, scripts or config around it. `shell_network: false` still adds the
  network denial; without either key nothing changes.
- **Refusals tell the agent to report back.** A sandbox-denied write, a denied command and a `write_paths`
  refusal all say the change needs the person's consent: stop, say what is needed and why, and end a delegated
  turn with `Status: BLOCKED`. The master's roster and the `delegation` skill say a consent block goes to the
  person — never done by the master itself or handed to another agent.
- **An unfinished delegate reports what it already did.** When the child halts, errors or is interrupted,
  the result says so and lists its successful tool calls, so the delegator does not redo or escalate work
  that already landed.
- **A task is sized to the question asked.** The `delegate` tool, the roster and the `delegation` skill say to
  pass only what the person asked, and to pass a record-this request as just that; a master that put its
  remembered conclusions into the task turned a one-line question into a re-audit several times as expensive.
- **The Telegram bot reports when a message was cut off** because the bot restarted for more than 30 seconds, so the
  person resends instead of waiting for an answer that never arrives.
- **The host guard's 403 names the host** and the `MY_AGENT_ALLOWED_HOSTS` variable that needs it added; the log records
  it once per name (a wrong Origin is not logged). The docs state plainly that the server has no login — do not expose it through a public tunnel.
- **Refusing to remove the last key** names the route in `provider:model` form and how to detach it.

### Fixed

- **Charts a delegated agent attaches reach the person.** A child's `MEDIA:`/`FILE:` lines named paths in the
  child's workspace and the parent's retelling dropped them, so a coach's charts never arrived. The delegate
  tool now copies each attachment into the parent's workspace under `delegated/<child>/` and rewrites the line;
  a file that cannot be carried over becomes a sentence, and any relayed line the retelling left out is appended
  to the final reply.
- **Scheduled jobs are quieter and report correctly.** A check job told to answer OK when nothing is due no
  longer pushes that OK to the chat (the run still shows in the UI); each job's last run is looked up by its
  own source instead of inside the two hundred newest runs; a scheduled memory consolidation records its run
  under the job; and Telegram messages drop table dividers and join table cells on one line per row, so a
  table the model writes stays readable as plain text.
- **Conversation recaps carry absolute dates.** A recap written at night said "tối nay" and was read the next
  morning as the new day. Transcript lines now start with the day and time in the person's zone, the recap
  prompt asks for concrete dates, and the next conversation's section title says when the previous one ended.

### Upgrade notes

- **An agent with `shell_write_paths` and the network on is now sandboxed.** Before, the key was ignored unless
  `shell_network: false`; check that such an agent's commands only write where the list says.
- **Refresh `<home>/skills/delegation.md`.** Installing a template does not overwrite shared skills, so an
  existing home keeps the old file-list version; copy `my_agent_crew/agents/templates/_shared_skills/delegation.md`
  over it.
- **Set `ExitTimeOut` in the launchd plist** (the template in `docs/deployment-guide.md` uses 45).
  The bot waits 30 s for the running turn before reporting "message cut off", but launchd's default is only 20 s,
  so without this key a `kickstart -k` in the middle of a long turn will SIGKILL before it can report.

## [0.5.0] — 2026-09-23

This release gives agents more ways to work with people — ask back, say what they are doing, send files — adds
wiki-style memory, and a real guard at the operating-system layer for agents holding data that must not
leave the machine.

### Added

- **Memory wiki: one page store per agent** at `memory/wiki/`, split into three directories `entities`,
  `concepts`, `syntheses`. Daily notes are written by date — right at the time of writing, wrong at the time of
  asking: "when is the Eco deadline" is scattered across eleven notes. A page gathers those fragments
  under the name of the thing itself, so the question has one place to be answered. The compile prompt spells
  out how the three directories differ — has a proper name, a recurring concept, or a conclusion that spans
  many things — because merely listing their names in the JSON template makes the model dump everything into `entities`.
- **Every page must declare its sources.** `sources` records `note:YYYY-MM-DD` or `conv:<id>`;
  `wiki_apply` rejects a page without sources. This is not input validation but the whole point of
  the store: a page that cannot say where it came from is a made-up page, and letting one such page
  through makes every remaining page less trustworthy.
- **Only part of the file belongs to the machine.** The link block between two markers is rewritten after each
  compile; the rest belongs to whoever — person or model — wrote it and is returned
  intact. Without that boundary the store either freezes or cannot be trusted.
- **`[[Page name]]` links** build a bidirectional graph, rewritten after each compile
  or each page edit via the web — editing one link changes what *other pages* say about
  where they are pointed to from.
- **Compile from notes** runs right after `memory_consolidate`, with no separate cron, because
  both read the same set of notes. The result is a **proposal** carrying the whole batch of pages together with the
  old content for one-step undo; `autonomous` agents apply it themselves. A broken compile does not break the memory
  cleanup turn that already finished before it.
- **Lint and two tracking tables.** A store degrades quietly: a page loses its last source, a
  link points to a page nobody has written, a page stops being updated. Lint reads the whole store in one
  pass and reports four kinds: `unsourced`, `dangling`, `review`, `stale` (over 90 days, or no
  updated date — treating missing evidence as fresh is how a store starts lying).
  Nothing is deleted: a dangling link is usually a page that *should* exist, i.e. work for the next
  compile. The two files `wiki/reports/open-questions.md` and `stale.md` are rewritten in full
  each time, because a table that accumulates keeps reporting errors fixed months ago.
- **Three tools for agents**: `wiki_get`, `wiki_search`, `wiki_apply`.
- **Wiki tab in the manage screen** and the endpoints
  `GET/PUT/DELETE /api/agents/{id}/memory/wiki…`: browse the store by group, search, open a page, edit,
  delete, view the lint report, and run a compile right away without waiting for the nightly job.
- **`web_search` runs on every machine** — added a DuckDuckGo source that needs no key, last in the
  list so there is always at least one source. Order of attempts: firecrawl → Brave → Tavily → DuckDuckGo;
  a broken source is skipped and logged, and only when all of them fail does the tool report that the service
  could not be reached. Previously the whole crew lacked this tool because no machine had a search key set.
- **`fetch_url` reads pages as markdown via firecrawl** — keeps headings, lists and tables instead of
  raw text, limit raised from 6,000 to 20,000 characters. If firecrawl fails it falls back to raw text.
- **Two new environment variables** `FIRECRAWL_BASE_URL` and `FIRECRAWL_API_KEY`. The key is only sent when
  set, so a self-hosted host needs no key and a mistyped base url does not carry the key anywhere.
- **The Connections page shows the search source order** and the firecrawl host in use, enough to tell
  "not enabled" from "misconfigured".
- **A skill can declare the commands it needs** — `requires.bins: [gws]` and `cliHelp: "gws --help"`
  in the front matter. On a machine missing the command, the skill stays in the list with the label
  "missing: gws", and the skill body opens with a warning line — the agent knows why it cannot do the
  job instead of failing midway. The Settings tab shows the same label.
- **One rule in the system prompt**: for a command whose syntax is uncertain, run `--help` once,
  and do not try more than two new syntaxes for the same job. Added because one scheduled run burned 16
  steps guessing the parameters of a program it had never seen.
- **Scheduled jobs auto-attach skills the prompt names** — hyphenated names only (`gws-shared`),
  because a one-word name like `ledger` shows up in prompts that have nothing to do with it.
- **Data-gathering script template for jobs** at `docs/examples/job-data-script.sh`: one command returns one
  JSON block, and each failing source records its own error instead of breaking the whole run.
- **Overlong tool results are condensed intelligently instead of truncated.** JSON is reduced by
  structure: every top-level key stays, arrays lose their tail, long strings lose their middle, and the returned
  string still parses. Numbers, booleans and null are never rewritten — ledger figures and
  health data travel this path. Plain text keeps the first 40% and last 20% verbatim, the
  middle is summarised by the agent's own route, with a label saying plainly which part is a summary. A summary that fails,
  is slow or comes back empty falls back to plain truncation; the tool always answers.
- **Provider `ollama`** (OpenAI-compatible, `OLLAMA_BASE_URL`, default
  `http://127.0.0.1:11434/v1`). Needs no key so it is always built; on a machine not running ollama the
  route falls through to the next one. The Connections page shows the address being probed, enough to tell "not running"
  from "wrong host".
- **The run card says plainly that the model read a condensed version** — the label records the condensing kind and the original length, so
  a short answer built on a pruned source is not misread as the full picture.
- **`ask_user` tool: the agent asks back instead of guessing.** At a point it cannot know on its own — which deadline,
  which account, whether to continue — the agent stops the turn and asks one question, with a list of options
  if there are any. It differs from a tool approval in three ways, so do not read it as an approval: an agent with
  `autonomous: true` still stops, because the question exists precisely so it does not decide alone; the question closes through
  its own path, and `/approve` and `/deny` are rejected on it; and a timeout is not a
  refusal — the agent receives the `default` value and moves on, silence is read as "go with the default".
  Each conversation has at most one open question. Answer on the web with the question card, or on Telegram
  with the very next message — type a number to pick, type text and it is taken verbatim.
- **The run timeline has its own waiting state.** A stop for a question used to show
  as nothing at all, reading like an agent thinking for hours. Now it is a separate step carrying the
  question text, the card title reads "Waiting for your answer" and the running animation is off — the job only
  moves when someone types, so it promises no other progress.
- **`pdf_read` tool.** Text pages are read straight to text; scanned pages go through the vision route
  like images, one call per page, so reading a long scan is expensive. Default 50 pages, `pages`
  picks a range (`'1-5'`, `'3'`). A machine without a vision route still builds the tool: text pages read
  normally, scanned pages report as unreadable instead of breaking the whole turn.
- **`shell_allow_patterns`: a supervised agent can still run everyday work on its own.**
  `shell_ask_patterns` pulls a command toward asking even when `autonomous`; the new list does the
  opposite, letting familiar commands run straight through even when *not* `autonomous` — so
  a careful agent can still run its own tests or `git status` without stopping at every
  command. The order is fixed: questions always ask, then the ask list, then the allow list, then
  autonomy; declaring a command in both means ask. Settable in `config.yaml`, in each agent's `agent.yaml`,
  or via `MY_AGENT_SHELL_ALLOW_PATTERNS` (semicolon-separated). Patterns under
  two characters, and patterns that merely *look* like wildcards (`*`, `.*`, `.`, `-`, `--`, `/`,
  `&&`, `||`, `;`, `|`) are dropped: matching is substring matching, so `.*` matches only the literal `.*`
  while the author reads it as "allow everything" — that very misreading is what is
  dangerous. A broken pattern is dropped on its own rather than breaking the whole list, and dropping is the safe
  direction because the command then falls back to asking.
- **`progress_note` tool: see what the agent is doing while it is still doing it.** Before a
  long stretch of work, the agent says one short sentence and it appears immediately on the timeline, so the
  viewer reads "reading the calendar" instead of watching a spinner and guessing. It never stops
  anything: no approval, no touching the ask list — a note that needs approval would arrive after the very work
  it announces. The step written out has its own kind `note` rather than `tool`, because a note has no
  duration and cannot fail; drawing it as a tool call would leave a line forever
  unfinished. Over 200 characters it is cut rather than erroring mid-turn. This is not
  memory: the note lives with the run and dies with it.
- **The `FILE:` line sends the real file instead of a path.** Telegram recompresses images, which is right for
  a chart and ruinous for a CSV — so `MEDIA:` remains `sendPhoto`, while `FILE:` goes through
  `sendDocument`, preserving bytes and file name; the web shows a download link instead of an embedded
  image. Limit 20 MB and seven formats (`pdf`, `csv`, `md`, `txt`, `xlsx`, `json`, `zip`).
  This list guards the answer, not the workspace: the agent can write whatever it likes into its own
  directory, so restricting to the workspace alone still leaves one sentence enough to send out a key
  file or a `.env` that an earlier step copied in. A path outside the workspace, a file that does not
  exist, a wrong format or an oversized file are all reported into the chat rather than thrown — the text part has
  already gone out, so an exception only leaves a promise of a file with no word on why the file never arrived.
- **Runnable skill examples in `docs/examples/skills/`**, with tests keeping them real. When a
  skill wraps a command-line program, two fields decide whether it lives or dies:
  `requires.bins` so a missing program gets labelled instead of breaking mid-turn, and
  `cliHelp` so the model reads the real syntax instead of guessing flag names. The test requires both for every
  bundle with a `scripts/` directory, and scans every file for email addresses and long id strings — an example
  that carries a real id off its author's machine is worse than no example at all.
- **A second skill example, `goodreads`**, for a service that no longer has an API. Reads via the public RSS,
  writes via its own browser session. Two things worth copying elsewhere: the account id lives
  in `scripts/goodreads.json` next to the script rather than as a parameter, so the read command has
  nowhere for the model to fill in wrongly; and an **empty response is treated as an error**, because Goodreads blocks
  scraping by returning 202 with an empty body instead of an error — the client throws nothing, and the
  all-`null` record produced from that reads exactly like a real answer. That is the dangerous kind of failure.
  Write commands: `rate`, `shelf`, `progress`, `review`. The buttons on the book page only appear after
  JavaScript has finished running, so the writer waits for them instead of looking as soon as the HTML arrives.

- **`shell_network: false`: cut an agent's shell commands off from the network at the operating-system layer.** Every
  `shell_run` of that agent runs inside macOS `sandbox-exec`: no outbound connections, including
  `127.0.0.1` and DNS, no listening ports; `open`, `launchctl`, `osascript`, `shortcuts`,
  `pbcopy` are blocked because they ask a process outside the sandbox to do the work. File writes are only allowed under
  `shell_write_paths` and the temp directory — a line inserted into a script that a networked job will run is
  a scheduled command, so blocking the network while leaving writes free blocks nothing. Unlike pattern
  lists, this guard holds for both `$(…)` and a script the model just wrote itself. On a machine without
  `sandbox-exec` the command is refused rather than run bare. Meant for agents holding private data
  such as a financial ledger; it only restricts *commands*, while the agent's answer still goes to the provider and
  to the recipient.

### Changed

- **Nine coding templates merged into three**: `fullstack-developer` does a whole software job
  (survey, plan, write, test, self-review, commit following the shared skills), `kongming` is a read-only
  advisor for hard decisions — no write tools, no `delegate`, its own cost ceiling — and
  `researcher` looks up any topic, has `pdf_read` and a ≥ 3 sources checklist. Removed `dev`, `scout`,
  `planner`, `coder`, `reviewer`, `tester`, `debugger`, `git`: every delegation is an empty context
  that knows only the brief, and for a personal crew that is not code-focused, the lost context costs
  more than the parallelism gains. Agents already installed from the old templates keep running unchanged; only `agent add` changes.
- `web_search` is no longer in the optional tool group: it is always built, so an agent declaring
  `web_search` in `tools:` no longer silently loses the tool.
- **`docs/tools.md` spells out the consequence of `shell_run` filtering environment variables**: a script that runs
  in your terminal can still break when the job runs, because every variable outside the allowlist
  disappears. A script that needs a non-secret value should read it from a file, not rely on environment
  variables — widening the allowlist hands the API keys to every command the model writes. The filtering behaviour
  is unchanged; it is now pinned by a test.

- **Activity details become a right-hand column of the chat pane on wide screens.** From 1101px, the runs
  of the open conversation live in an always-open 380px column, which keeps its space even when there are no
  runs yet so the chat pane does not jump when work starts. Narrower screens keep the one-line strip below
  the message stream as before.

### Fixed

- **Truncated tool results no longer exceed the `tool_output_chars` ceiling.** The "truncated" label line
  used to be appended after the ceiling was already spent, so the returned version was always a few
  dozen characters over the ceiling. Now the label is paid for out of that same budget. The old test measured with a `+ 40` margin so
  it did not see it; there is now a test sweeping several ceilings and several data shapes to pin this invariant.
- **The `researcher` template respects the search ceiling the asker sets** ("at most 2 searches") and
  requires a **Sources** section with URLs. Before this, a report could cite no source at all even though the persona
  said to record them.
- **The `fullstack-developer` template reports point by point whether it followed `kongming`'s advice**, with
  reasons. Before this, it could say "followed the advice" while the code did the opposite.
- **The Goodreads writer waits for the page to render the buttons** before clicking, and uses the right shelf labels; the first
  real write failed at both spots.

### Upgrade notes

No manual migration needed. The `approvals` table gains three columns (`kind`, `options`, `answer`), added
automatically on startup with default values for old rows. All new keys in
`agent.yaml` (`shell_network`, `shell_write_paths`, `shell_allow_patterns`) are optional and default
to the old behaviour. Agents already installed from the nine old coding templates keep running; only
`agent add` switches to the three new templates.

## [0.4.0] — 2026-09-22

This release rebuilds the web UI around one idea: **see what the agent is doing**, and manage the whole crew
right on the web instead of editing YAML by hand.

### Added

- **Replies render as markdown** — headings, lists, tables, syntax-highlighted code blocks, replacing a
  block of raw text. Links open in a new tab; raw HTML is not rendered.
- **Conversation titles set automatically** from the user's first message, running in the background after the turn
  ends so it does not slow the answer. Manual renaming still works and always wins over the automatic title.
- **Run progress right inside the chat pane**: calling the model or running a tool, which step, how much
  spent so far — visible while waiting, no need to open another tab.
- **Manage area separated from chat**, navigated by hash route `#/manage/<section>` with nine tabs:
  Activity, Approvals, Crew, Tools, Schedule, Memory, Costs, Connections, Settings. Reloading the page
  stays on the same tab.
- **Open a single run** with `#/manage/activity/<run_id>` — shareable, survives reload,
  and also opens old runs the activity list no longer keeps.
- **Manage agents on the web**: add, edit, delete agents (master and child agents alike), edit the persona files
  (`AGENTS.md`, `SOUL.md`), view the assembled system prompt to know what the model actually reads.
- **Tool matrix** — which tools the whole crew uses, which agent uses what, in one table.
- **Connections page** — API keys, Telegram, vision route, see what is configured and what is not.
- **Agent management HTTP API**: `POST /api/agents`, `PATCH /api/agents/{id}`, `DELETE /api/agents/{id}`,
  `PUT /api/agents/{id}/files/{name}`, `GET /api/agents/{id}/prompt`, `POST /api/agents/reload`,
  `GET /api/tools`, `GET /api/connections`.
- **`scripts/gates.sh`** — runs all nine CI gates with one command, in the exact order of `ci.yml`, stopping at
  the first red gate and naming it (~22 seconds). Alongside it, a test keeps the version number in its five
  declared places from drifting apart.

### Changed

- **The "Activity" column now belongs to the open conversation**, inside the chat pane, instead of a
  shared bar showing activity from every conversation. Crew-wide activity moves to the Activity tab of the
  manage area.
- The Crew, Schedule, Approvals, Memory, Costs tabs are reclassified by scope: what is shared
  across the crew lives in the manage area, what belongs to one conversation lives inside the chat pane.
- A tool step's `arguments` are recorded as a name → value mapping (previously the whole thing was forced into
  one string, displayed as one row per character). The reading side tolerates both shapes so runs
  recorded before this release can still be viewed.

### Fixed

- An empty reply turn is no longer treated as a finished turn — the web UI stayed silent with no report.
- A run that ends while being viewed now shows the right status and end time: the page's in-memory
  copy lacked that timestamp, so the page re-reads exactly once on the frame where the status changes.
- Six Python files brought back to proper `ruff format` formatting; the `ruff format --check` gate in CI
  now runs in every development cycle, not just `ruff check`.

### Upgrade notes

No migration needed. The SQLite schema only adds tables, all `CREATE TABLE IF NOT EXISTS`; the
`config.yaml`, `agent.yaml` files and the home directory keep their shape. Upgrading is pulling the new code and
restarting the process.

## [0.3.0] — 2026-09-21

- Claude Code-style `.agents/` kit: commands, agents, skills, hooks.
- Image reading via vision route; Telegram albums merged into one turn; the user's time zone.
- Three-file persona; Vietnamese documentation set with five animated diagrams, published to GitHub Pages.

## [0.2.0]

- Multiple agents, `delegate` for the master to hand work to other agents, Telegram channel.

## [0.1.0]

- One agent, `run_turn` loop with a tool approval gate, web UI, memory on disk.

[0.9.2]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.9.2
[0.9.1]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.9.1
[0.9.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.9.0
[0.8.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.8.0
[0.7.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.7.0
[0.6.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.6.0
[0.5.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.5.0
[0.4.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.4.0
[0.3.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.3.0
[0.2.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.2.0
[0.1.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.1.0
