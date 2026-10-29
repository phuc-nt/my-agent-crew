---
layout: default
title: Changelog
---

# Changelog

All notable changes to my-agent-crew. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [SemVer](https://semver.org/). One version number for both backend and web: within a
single release, `pyproject.toml` and `web/package.json` always carry the same number.

## [Unreleased]

## [0.25.0] — 2026-10-29

### Added

- A line of `MEMORY.md` can say how long it holds: `(2026-10-28 → 2026-11-02)`, its date and
  then the last day it is true. From the day after, the line leaves the prompt at once, and
  the nightly rewrite lists it for removal. Dropping such a line does not hold an
  `autonomous` rewrite for review, and neither does adding a new line with an end day; giving
  a line already in memory an end day, or an earlier one, does, since that schedules its
  removal.

### Changed

- The memory rewrite prompt asks for an end day on what holds only for a while, and asks
  that state an agent's own records or tools already keep (orders, transactions,
  measurements) stay out of memory.

## [0.24.1] — 2026-10-29

### Fixed

- A conversation an agent was handed while the master answered the person (a delegated
  child whose chain began in a chat, on Telegram or through the inbound API) now counts as
  one of its episodes. Leaving all delegated children out meant a specialist the person only
  reaches through the master had no episodes at all. Children of a scheduled job's turn, and
  children opened before chains recorded where they began, stay out.

## [0.24.0] — 2026-10-29

### Added

- The nightly memory rewrite reads the week's conversations as well as the daily notes. Each
  conversation someone took part in (not a delegated child, not a scheduled job's) joins the
  notes as its recap, dated by the day it was last spoken in, so what was said and never noted
  still reaches `MEMORY.md` through the same gate. At most 10 recaps per run; a conversation
  with no notes newer than `MEMORY.md` but a new episode is now enough to run the rewrite.

### Changed

- A conversation's recap that the conversation has outgrown (more was said after it) is
  written again rather than reused; `conversations.summary_seq` records how far a recap reaches.
  Recaps written before this release count as final.

## [0.23.0] — 2026-10-26

### Added

- `--uds PATH` serves on a Unix socket instead of `--host` and `--port`. The socket's folder is
  closed to every sandboxed command (and to the `tool_script` child) like a private folder, and
  no port is named, so under `bwrap` a confined command may keep the network on.

### Security

- On Linux the server makes its own process undumpable as it starts, so a command it runs as
  the same user cannot read its environment or memory through `/proc`.

## [0.22.0] — 2026-10-26

### Added

- On Linux, where macOS `sandbox-exec` is missing, a confined `shell_run` command and the
  `tool_script` child run under `bwrap` (bubblewrap) with the same policy: read-only root,
  writes only under `shell_write_paths` and the temp directories, no network, private folders
  covered. A confined command that keeps the network while the server has named its port is
  refused, since bwrap cannot close one port; with neither sandbox, confined commands are
  refused as before.

## [0.21.0] — 2026-10-26

### Added

- `MY_AGENT_SCHEDULER=external` leaves the clock to a host that may stop the server between
  requests: no job fires on its own, the host runs a due one through `POST /api/jobs/{id}/run`,
  and approvals left waiting still lapse on time.
- `MY_AGENT_TELEGRAM=webhook` stops the master's bot polling: the host holds the bot's webhook and
  hands updates over through `POST /api/channels/telegram/updates`. An update already handled is
  dropped, so a webhook that delivers one twice is answered once. The command menu is still
  published.

## [0.20.0] — 2026-10-14

### Added

- An agent whose own file says `computer: "on"` can see and work the real screen of the Mac the
  crew runs on, through four tools: `computer_state`, `computer_screenshot`, `computer_observe`
  and `computer_act`. The key is read from the agent's file alone: there is no machine-wide
  switch, no global key, no environment variable, and nothing is inherited from the master. The
  `tools:` list neither brings these tools nor takes them away, and a list that names one logs a
  warning. A bare `on`, `yes` or `true` stops the start with a hint to write `"on"` in quotes,
  since YAML reads those as a switch; a bare `off`, `no`, `false` and an empty key read as `off`.
- `computer_apps` lists the applications such an agent may read and act on, by name (case and
  accent form aside) or by bundle id (exactly). An empty list lets the agent look and never act:
  `computer_state` names every open application, `computer_screenshot` captures whatever is in
  front, and `computer_observe` and `computer_act` refuse every call. The list cannot name a web
  browser, by name or bundle id, a site saved as an app of its own included: such a line stops
  the start, or is a 422 through the API.
- The desktop helper, `desktop-helper/`, is a Swift package that builds `MyAgentCrewDesktop.app`
  for macOS 14 and later, an app with no Dock icon. It runs in the owner's login session as a
  LaunchAgent, holds the Screen Recording and Accessibility permissions, and answers one JSON
  line per connection on a Unix socket, mode 0600 in a folder only its owner can enter, taking
  connections from its own user only. It checks the lock, the display and both permissions
  before every command, and never asks macOS for a permission on its own. The server never
  captures or posts an event itself: it waits up to 10 seconds for the helper's answer.
- `scripts/desktop-helper-pack.sh` builds the app and signs it ad hoc; with `--install` it also
  copies it to `~/Applications` and writes `~/Library/LaunchAgents/com.my-agent-crew.desktop.plist`,
  and loads nothing. Packing again changes the signature, so macOS forgets both permissions.
  `scripts/desktop-helper-check.sh` builds the helper and runs its XCTest suite against a fake
  system, so no dialog appears, and a new macOS job in CI runs it; `scripts/gates.sh` does not.
- `desktop_socket` in `config.yaml`, or `MY_AGENT_DESKTOP_SOCKET`, says where the server looks
  for the helper, `<home>/desktop/sock` by default.
- `computer_state` tells whether the helper is there, whether the screen is locked or asleep,
  which permission is missing, and which listed applications are open and which is in front. It
  needs no permission and answers on a locked screen. An application outside the list that is
  in front is told as being there, never by name.
- `computer_screenshot` captures the main display, scaled down so its longest side is at most
  1,456 pixels, only while a listed application is in front both before and after the capture.
  The picture is saved as `desktop/<frame_id>.png` in the workspace, or under the first of the
  agent's `write_paths`, and the folder keeps the newest 40. With a vision route the picture is
  read, or asked the call's `question`, and the cost counts in the turn. When the screen has not
  changed since the conversation's last picture, nothing is sent again and no model is called.
- `computer_observe` returns the outline of an application's focused window, up to 400
  elements, each line led by a `ref` that carries a mark of that reading. A listed application
  can be read even when other windows cover it; a secure field never shows its value.
- `computer_act` clicks, double-clicks, right-clicks, drags, scrolls, types, presses keys, sets
  a value by `ref`, or brings an application forward. Every kind but `focus_app` needs the
  `frame_id` of the latest frame of the screen, no older than 300 seconds, and a picture taken
  by anyone after it ends it. A `ref` must belong to the outline the same conversation was last
  shown, and a click by `ref` names the element as that outline does. The helper acts only while
  that application is in front, and the answer says the action was sent and tells the model to
  look again before its next step. `set_value` may name the field as the outline does, and is
  refused when that name is another.
- `computer_act` needs approval like every tool that changes state, and some calls ask a person
  even in an autonomous conversation and after "Luôn cho phép": bringing an application
  forward, Enter or Space alone, a key outside the everyday few, typed text with a newline, a
  click or a drag at a point rather than on an element, every double click, and typed text, a
  value, or the name of the element clicked or the field set that holds a stop word. A field's
  name is the outline's own, whether the call gives it or not. The approval card reads the
  reason.
- From a script, the three tools that only look are called like any tool that reads;
  `computer_act` only under `script_calls: gated`, through the gate first, and a call that must
  ask a person stops the script there.
- `GET /api/agents/{id}/desktop` tells an agent's level, its applications and the state of the
  machine, waiting at most a second, and is never an error for an agent that exists; with no
  helper answering, `present` is `false` and the rest `null`. `GET /api/connections` carries the
  same machine block under `desktop`. `POST /api/agents/{id}/desktop/screenshot` takes a picture
  as the agent would, which ends the frame the agent holds, or answers 409 with the reason.
  `POST /api/desktop/permissions` has the helper ask macOS for both permissions and returns what
  it holds; it answers 409 when the helper is absent or refuses, as it does on a locked screen.
  `PATCH /api/agents/{id}` takes `computer` and `computer_apps`, effective from the next turn
  without a restart.
- The **Kết nối** page has a Desktop card that tells whether the helper runs, whether the screen
  is locked or asleep, and each permission, with a "Xin quyền" button that sends only when
  pressed. The agent editor has a "Dùng desktop của máy" section with the level and the list of
  applications. An agent's page has a Desktop card that tells whether it can work now and takes
  a trial picture. The tools grid marks the four tools as coming with the desktop.
- An approval card for `computer_act`, in the conversation and in the list of requests, puts the
  action in words ("Bấm «Gửi» (a2-3f9c) trong Mail") above the raw parameters, with the reason
  when it always asks, and below them the picture the agent planned on, with the point marked,
  when that picture can still be found. A `computer_screenshot` step shows its picture on the
  run's timeline and on the tool card in the chat.
- `GET /api/agents/{id}/desktop/pictures/{frame_id}` serves a frame's picture exactly as
  `computer_screenshot` or the trial button saved it for that agent, and the approval card reads
  its picture there. The agent may write in the folder the pictures are in, so the server
  remembers, in memory, the SHA-256 of each picture it wrote (the newest 40 per agent): a picture
  rewritten, replaced with a link or removed since, a frame not taken for that agent, and one
  taken before the last restart are all a 404, and the card then shows no picture.

### Changed

- `browser_ask_patterns` is now the stop-word list of the desktop as well: one list for the
  pages a browser opens and for the screen.

### Fixed

- A file `browser_download` gave up, as too slow or too large, could leave its half in the
  browser's holding folder for a moment after the call returned: Chromium says a file stopped
  before it has removed the half, and under load the next download counted those bytes toward
  its own limit. The folder is now emptied when a call is done with it, before the next may
  start.

### Security

- `<home>/desktop/`, and the socket wherever `desktop_socket` puts it, judged where the path
  leads rather than where it is written, is closed to every file tool and every sandboxed
  `shell_run`, whether the helper runs or not.
- The sandbox rules that close a private folder now deny an outbound connection into it as well
  as a read or a write, for the browsers' profiles as for the helper's folder: a Unix socket is
  reached by a connection, which the file rules do not judge.
- The server talks only to a socket owned by the user it runs as, in a folder nobody else may
  write in, and never through a symbolic link; otherwise every call is refused as `untrusted`.
- Some things no setting and no approval allow, and they are refused before anyone is asked: an
  application outside `computer_apps`; typed text holding `sudo`, an `rm` that recurses without
  asking, or a `curl` or `wget` fed into a shell, read as a shell would read it; `cmd+q`,
  `cmd+shift+backspace` and `cmd+opt+esc`, with any further modifier; `cmd+space` unless
  Spotlight is listed, and even then it asks; any text for a field the outline marks secure. The
  helper refuses again, in any order of modifiers, the keys that lock the screen, log out or
  force-quit, and refuses typing, keys and setting a value while macOS has secure input on.
- Typed or set text holding a control character other than tab, line feed and carriage return
  is refused by the server and by the helper: a backspace or an escape does not show on the
  approval card yet reaches the application as a key. Names from the screen that hold one are
  written out, as `[U+0008]`, on the card and in the reason.
- The desktop never acts in a web browser, where a page reaches the crew's own web page and the
  private network that the `browser_*` tools hold apart. Besides the list, the helper refuses
  every action while a browser is in front and never brings one forward (`browser_app`);
  bringing another application forward is how an agent leaves one.
- Before it posts a click, a scroll or either end of a drag, the helper asks macOS what is on
  top at that point and posts nothing unless it belongs to the application in front, and for a
  click by `ref` is that element or one inside it (`point_covered`). When macOS cannot tell, it
  refuses too, so a dialog or a notification that came up over the point is never clicked.
- Everything the screen chooses the words of stands inside a fence with a fresh mark per answer,
  as a web page does: the names of applications, the outline and window titles, what a model
  reads from a picture, and the helper's own sentence with a refusal.
- An unsandboxed shell reaches the helper's socket like any other program of the owner's, past
  the list of applications and the approval gate. The docs say so and advise a sandboxed shell,
  or none, for an agent with the desktop.

## [0.19.0] — 2026-10-14

### Added

- `browser_download`, brought by `browser: act`, clicks an element the way `browser_act` clicks
  one (the same `ref`, `name` and checks just before the click) and keeps the file that click
  makes the page send: the first file the tab sends after it, or one sent by a window the tab
  opens meanwhile. It is judged as a click is: it always asks a person on a page outside the
  agent's `browser_hosts` and on an element that carries a stop word, and otherwise asks in a
  supervised conversation and runs in an autonomous one. A file must begin to arrive within 15
  seconds and arrive whole within `timeout_s` (5 to 300, 60 by default), and is dropped as it
  arrives once it passes 50 MB. A browser has one call waiting for a file at a time. A script
  calls the tool only under `script_calls: gated`, through the gate first.
- `browser_pdf`, brought by `browser: read` as well, prints the page of a tab to an A4 PDF. It
  only looks at the page, so nobody is asked, and a script calls it like any tool that only
  reads. A print over 50 MB is not kept.
- Both tools save into `downloads/` in the agent's workspace, or under the first of its
  `write_paths`. A name comes from `save_as`, else from the name the site suggests or the
  page's title, and keeps only plain letters, digits, dots, underscores and hyphens. A
  downloaded file whose ending is not one data has (pdf, csv, xlsx, png and a few more) gets
  `.bin` after its name, so nothing loads or runs it by its name. A file never replaces another
  (`-2`, `-3`, … instead), is written through no symbolic link, and on macOS carries the
  quarantine mark from before its first byte. A folder that a link leads out of the workspace or
  its `write_paths`, or whose files already take 1 GB, takes no file, and both are checked
  before anything is clicked or printed. The answer names the folder and the size outside the
  fence; the file's name and the hosts it came from, which a page chose, stand inside it.
- The outlines `browser_act` and `browser_snapshot` return mark with `[new]` what appeared or
  changed its text since the model last saw that tab, with one line outside the fence that
  counts them. Nothing is marked once the tab went to another address, and `browser_navigate`
  marks nothing.
- A person can sign in for an agent. `POST /api/agents/{id}/browser/login`, with an optional
  `url`, stops the agent's browser and opens a Chromium window on its profile, on the screen of
  the machine the crew runs on, behind a proxy of its own with the same fence on addresses and
  keeping no file a page sends; `POST /api/agents/{id}/browser/login/done` closes it. The window
  also closes when its last page is closed, after 15 minutes, on `POST …/browser/stop`, when the
  agent is removed or set to `off`, and when the server stops. While it is open every
  `browser_*` call of the agent is told that the owner is signing in and to call
  `browser_navigate` again once the window is closed. It cannot open (409, with the reason) when
  the server runs in no screen session that is open, when the screen is locked, while the
  agent's browser is busy with a call, while the server stops, or when the agent was edited as
  the window was opening; an address the browser would refuse is a 422.
  `GET /api/agents/{id}/browser` tells of the window in `login`: open until when, or whether one
  can open and why not.
- `GET /api/agents/{id}/browser` also tells in `logins` where the agent's browser may still be
  signed in: each host holding an `httpOnly` cookie that outlives the browser and is not sent
  along to other sites, with the time the last such cookie expires. Only a cookie's host and
  expiry are read, never its name or value. An agent with `browser_hosts` is told each line of
  that list; another is told at most 50 hosts, and `logins_more` counts the rest. With no
  browser up the server reads `<home>/browser/<agent id>/crew-logins.json`, which a browser on
  the profile writes as it closes. It is a sign, not proof: a site may have signed the person
  out on its side.
- The browser card on an agent's page has a button that opens the sign-in window, with an
  optional address; while the window is open it says when the window closes by itself and has a
  "Xong" button, and when none can open it says why. Under it the card lists the hosts the
  browser may still be signed in to, each with its date. The approval bar reads a
  `browser_download` call as the element it presses and the name the file is to be kept under,
  and the tools grid marks `browser_download`, like `browser_act`, as needing `act`.
- `docs/examples/skills/browser-use/` is a sample skill that teaches an agent the browser's
  working loop; a test keeps the tools and parameters it names in step with the tools.

### Changed

- `browser_navigate` to an address that answers with a file no longer fails with the browser's
  own line: it says the address is a file, leaves the tab blank, and tells the model to open the
  page that links to the file and press the link with `browser_download`.
- An element's name loses its own « and » before it is quoted on the line a person is asked
  with, at the server and on the web, so a name a page chose cannot close the quote early and go
  on in words that read as the crew's.
- `browser_screenshot` writes its picture the way the new tools write files, through no link and
  on macOS with the quarantine mark, and a folder or a link under a picture's name is neither
  counted among the 40 kept nor removed. The vision route reads the picture as it was taken,
  not whatever stands under its name by then.
- Starting a browser is given up after 40 seconds, and closing one is waited for no longer
  than 10, so a Chromium whose driver fell silent no longer holds a stop or the server's
  shutdown.

### Fixed

- A browser call whose browser was stopped, or whose agent was removed or taken off the browser,
  while that browser was starting for it was handed the browser as it closed: it tried to open a
  tab until its 20 seconds were up and was then told the page did not answer, or now and then
  opened one that closed under it. It is now told at once which of the two happened: an agent that
  is gone is told to call no more browser tools, a stopped browser to call again if the page is
  still needed.

## [0.18.0] — 2026-10-14

### Added

- An agent can open and read web pages in a browser of its own and, where its file says so, click
  and type in them. Two switches bring it. The machine's `browser_enabled` (`config.yaml`, or
  `MY_AGENT_BROWSER_ENABLED`) is off by default; the agent's own `browser` key in `agent.yaml` is
  `off` (the default), `read` or `act`. `read` gives `browser_navigate`, `browser_snapshot`,
  `browser_text`, `browser_tabs` and `browser_screenshot`; `act` adds `browser_act`. The key alone
  brings the tools: a `tools:` list neither adds one nor takes one away, and the key is read from
  the agent's own file, never from the settings it starts from. A bare `on`, `yes` or `true` stops
  the start, since it does not say how far the agent may go. The browser is the Chromium the
  Playwright package pins, installed once with `uv run playwright install chromium`, or the
  machine's own Chrome with `browser_channel: chrome`. A machine that turns the browser on without
  one still starts, with one warning line that names the command, and gives no agent a browser tool.
  Each agent has one headless browser, started at its first call and stopped after
  `browser_idle_minutes` (10) without use, with a profile of its own under `<home>/browser/<agent
  id>/`: what one agent is signed in to is not another's, and stays over a restart. A browser whose
  driver went away is forgotten with it, and the next call starts another. A tab belongs to the
  conversation that opened it and no other conversation reaches it; the tabs of scheduled runs are
  kept apart from every conversation's. An agent holds at most `browser_max_tabs` (5) tabs, and a
  tab nobody used for half an hour is closed. The master is told the browser tools of each agent by
  name, like any other tool.
- A page is told to the model as an outline of what is on it, each thing that can be acted on with a
  `ref`, between two fence lines made anew for every answer: nothing a page writes can close the
  fence or stand outside it, so the words of a page stay data. A tool sizes what it fences to the
  agent's output cap, so no answer is cut, kept in a file or shortened by a model and the closing
  line is always there; under a cap with no room for a fence the answer says so in place of the
  page. An error of the browser is told outside the fence by Chromium's code or the kind of the
  error only, and the line the browser wrote, which may quote the page, inside it.
  `browser_snapshot` gives the whole outline, only what can be acted on, or the lines that hold a
  word, and can wait for words to appear; `browser_text` gives the text of the page or of one
  element; `browser_tabs` lists and closes the conversation's tabs without starting a browser;
  `browser_screenshot` saves a picture under `screenshots/` in the agent's workspace (under the
  first of its `write_paths` when it has them), keeps the newest 40, and, on a machine with a vision
  route, gives what that route reads in the picture between fence lines too. A window a page opens
  becomes the conversation's next tab, and a dialog is dismissed and told once.
- `browser_act` does one thing (`click`, `type`, `fill`, `press`, `select`, `hover`, `scroll` or
  `upload`) to the element the model names by `ref` and by the name the page shows for it, and only
  while that element is the one the model was shown: a page that went to another address, an element
  that is gone, became another kind of element, carries another name, or gained a word that stops
  for a person since the model looked, is not acted on. Nothing is ever typed into a password,
  one-time code or card number field, whatever the conversation allows: a field is one by its
  `type`, its `autocomplete`, the name the page draws for it, its `name` or `id` in the markup (a
  password box switched to show what is typed stays one), or by taking a single character, as each
  box of a code typed one digit a box does. Enter in a field is judged by the buttons it would
  press: where a submit button of the field's form carries a word a person would be asked about, the
  key is refused and the model is told to click that button, so a key is no way round the question.
  An upload takes a file of the agent's workspace.
- Two guards cannot be switched off. Every connection a browser makes goes through a proxy inside
  the server that lets it reach public addresses only, judged by the address a name resolves to and
  connected to that same address; a page that leads to a private one is refused, and the host it led
  to, a name of the page's choosing, is told inside the fence, as is what a page reached for and was
  refused. Nothing leaves a browser beside that proxy: QUIC is off, a page's WebRTC sends nothing
  around it (also on a profile used before), and the errands a Chromium runs for itself are turned
  off or sent nowhere (a connection to a search engine at each page, the forms of a page described
  to the autofill service, its sign-in service, the check-in of its push service). An address is
  read one way, the way the browser reads it too, and only a full `http` or `https` address is
  opened; a private address written out, `localhost` and every name under it are refused with no
  name resolved, and so is one written as a number in another base or in fewer parts (`2130706433`,
  `0x7f000001`, `0177.0.0.1`, `127.1`), which a browser reads as an address. The folder that holds
  the profiles, `<home>/browser/`, is closed to every file tool of every agent (read, list, write,
  search, through a link as well) and to every sandboxed shell, with the browser on or off. A shell
  that was never sandboxed is not sandboxed by this: `docs/deployment-guide.md` says what to check
  before the browser is turned on for an agent that has one. Downloads are refused in this release.
- `browser_navigate` and `browser_act` ask before they run, like any tool that changes something,
  and a tool can now say which of its calls stop for a person whatever the conversation allows and
  which are routine. An agent's `browser_hosts` (`shop.example`, `*.shop.example`) names the sites
  that are its own: an address there opens without a question, in a supervised conversation as well;
  any other host asks, in an autonomous one as well, and so does an action on a page outside the
  list. `browser_act` always asks for an upload, and for a click, a key or a choice on an element
  whose name, the words drawn under it, or the words of the button or link it stands inside (a click
  on the picture in a button is a click on the button) hold one of the machine's
  `browser_ask_patterns`: by default 49 words of paying, ordering, booking, sending, deleting,
  agreeing and signing out, Vietnamese and English (mua, thanh toán, đặt hàng, gửi, xoá, đăng ký,
  pay, buy, checkout, submit, delete, confirm, subscribe and the like; `docs/tools.md` has the
  list), as whole words in any case, an accented word also matching a name written without accents.
  A name is read as an eye reads it: characters a browser draws nothing for are left out, letters
  drawn in another form (fullwidth, ligatures, mathematical) are read as plain ones, and a name
  written the way code is (`btn_pay`, `CheckOut`) is taken apart first. An emptied list turns this
  guard off. The request carries the reason as a line a person reads. Nobody is asked about an
  address `browser_navigate` refuses whatever the answer (one it cannot read, one that is not `http`
  or `https`, a private one written out): the call goes straight to its refusal. From a script, the
  tools that only look are called like any reading tool; `browser_navigate` and `browser_act` only
  by an agent with `script_calls: gated`, through the same gate.
- `GET /api/agents/{id}/browser` tells what an agent's browser has open (each tab by number, label,
  conversation, host and title, never its whole address, last used first) and starts nothing; `POST
  /api/agents/{id}/browser/stop` stops it, a call in flight included, and keeps what it is signed in
  to; `DELETE /api/agents/{id}/browser/tabs/{tab_id}` closes one tab. `GET /api/connections` gains
  `browser` (on or off, channel, installed version or the missing part and the command that installs
  it, the agents whose browser is up). An agent's profile carries `browser` and `browser_hosts`, and
  `PATCH /api/agents/{id}` sets them from the next turn on; a save that leaves the agent at `off`
  stops its browser at once, and removing an agent deletes its profile folder with it; a turn that
  was running when either happened keeps its tools and is refused by them, so nothing opens that
  browser again or writes to the profile. A server going down stops every browser and starts none
  after that: no Chromium is left behind it. `GET /api/tools` marks the six tools with
  `with_browser`.
- The web shows and sets all of it. Connections has a "Trình duyệt" card: on or off, the channel and
  the version, or what is missing with the command that installs it, and the agents whose browser is
  up, a line it reads again by itself every five seconds while the page is looked at; it sets
  nothing. The agent editor has a "Trình duyệt" part, the level (Tắt, Đọc, Thao tác) and the hosts
  that open without a question: on a machine that has the browser off or not installed the form says
  so as soon as a level is chosen, and a line that is no host name is named under the box and holds
  the save. An agent's page has a card of what its browser has open, each tab with its title, host
  and conversation, a button that closes a tab and one that stops the browser; it reads again every
  five seconds while the page is looked at. The tools table marks the six tools as coming with the
  browser and explains an empty cell by the agent's `browser` key. A browser call that waits for a
  person is said in one line above its raw arguments ("Mở trang shop.example", "Bấm «Đặt hàng»"), in
  the chat and in the list of requests. A finished `browser_screenshot` step shows the picture
  small, as a link to the whole of it. On a server from before this release the web draws none of
  it.

### Fixed

- A sandboxed `shell_run` command that keeps the network (an agent with `shell_write_paths`) could
  reach the server it runs under. The API asks for no login, so one request saved any agent's
  file, the command's own `shell_write_paths` among them, and the sandbox was gone at the next
  turn. The server now names its own port as it starts, and every sandbox profile refuses a TCP
  connection to that port on every address; the rest of the network is the command's as before. A
  shell that was never sandboxed, a `command` job and another local service that would pass a
  request on are not covered.

## [0.17.0] — 2026-10-13

### Added

- A tool of an MCP server whose parameters are too long is no longer left out when the length is
  repetition. Parameters over 50,000 characters are folded first: each part that stands more than
  once is said once under `$defs` at the top and pointed to with `$ref`, wherever that makes the
  whole shorter, and the limit is asked of the folded form. Putting each part back where it is
  pointed to gives the server's own text again, letter for letter; a fold that does not is not
  used. The model is told the folded form. `tool_search`, the signatures the script tool shows
  and the call sent to the server go by the parameters as the server wrote them. Parameters
  within the limit are handed on untouched, however much they repeat. Left out as before, with
  the same warning line and its name in `skipped`, is a tool still over the limit once folded,
  one over 500,000 characters, and one whose parameters hold `$id`, `$anchor`, a dynamic or
  recursive reference, or a `$ref` to anywhere but `#/$defs/<name>` or `#/definitions/<name>`.
  Each tool row of `GET /api/mcp` gains `folded`: `null`, or `{"from": n, "to": m}`, the two
  lengths in characters, and a fold is logged once per connection (`MCP server <name>: tool
  '<tool>' parameters folded, <n> chars to <m>`). On the web, the server's card under Quản lý →
  Kết nối says "đã gộp tham số" on the tool's row, with both lengths.
- A front matter line with a second colon is read as the text it is. `description: Use when: the
  build fails` is not YAML, and a kit agent or a skill written that way was left out of the crew.
  A front matter YAML refuses is now read a second time: each `key: value` line that starts at the
  first column and whose value holds a colon before a blank, or ends on one, has its value taken
  as one text, the whole rest of the line, a trailing ` # remark` included. A value that opens
  with a YAML sign (a quote, `[`, `{`, `|`, `>`, `&`, `*`, `!`, `- `), a nested key, a value that
  runs over lines and an item of a list are left as written, so a front matter broken some other
  way is still refused, by the error of the second reading. So is a line holding a control
  character or a mark YAML ends a line at (a carriage return inside the line, U+0085, U+2028,
  U+2029); the carriage return that ends a line of a Windows file is cut off. Each line taken
  as text has to come out as an entry of its own at the top of what the block states: a line of
  that shape inside a value that runs over lines (quoted, or in `{…}` or `[…]`), or one of two
  lines under the same key, leaves the block refused, by the error YAML gave it. A front matter
  YAML takes is read as before. This holds wherever a front matter is read: a kit agent's file,
  a kit command, a skill's `SKILL.md` and a persona file, whose block is then left out of the
  prompt as any front matter is, where 0.16.0 handed the model the file as written. The memory
  files keep strict YAML.
- A job that keeps failing shows it. Each row of `GET /api/jobs` gains `failing`: `null`, or
  `{count, since, told_at, next_notice_at, telling}`, the failures in a row the job is in, when
  the first was, when the channel last took a message about them, when the next message may come
  and whether one is on its way now; the two times of the message are `null` while none got
  through. On the web, the job's row under Quản lý → Lịch chạy says since when and how many
  times in a row, and then when Telegram was told and when it will be told again, or "Đang báo
  qua Telegram." while the first message is on its way, or that no message got through yet.
- The activity stream (`GET /api/activity/stream`) carries a new event, `jobs`, whose payload is
  `{"type": "jobs"}` and nothing more. It says the job list is no longer what a page read. A
  failed run is counted into its job's streak, and the owner told of it, after the run is over,
  and a send can take most of a minute: the event is sent once the count of a run is settled,
  whenever that changed the job's `failing`. It is also sent whenever the scheduler reads the
  crew's schedules again (an agent saved, made, installed or brought in, a key or the shared
  routes saved) and when an agent leaves the crew, whether or not a row changed. The web reads
  the job list again on it, so a row moves from "Đang báo qua Telegram." to when the owner was
  told with no other run ending, and a page open in another tab shows a schedule saved in this
  one; of two reads of the list that are out at once, the page now shows the one it asked for
  last. A pause switch moved and a schedule made in chat deleted on that page are shown from the
  server's answer and then read again, so a read that was out meanwhile cannot put the row back
  as it was. A job's pause switch and the removal of a schedule made in chat are not sent: another
  tab sees them at its next read. A page on an older bundle does not listen for the event and is
  not disturbed by it.

### Changed

- A failed job that opened no conversation is told whatever its kind, and a job that keeps
  failing is not told at every run. 0.16.0 told a failed script job only, once for each failed
  run. A failed `command` job is now told too, by the code the command left with and the last
  line it printed (or that it ran past its 900 seconds and was stopped), and so is a failed
  rewrite of an agent's memory (`memory_consolidate`), by what its run was summed up by; that
  rewrite no longer stops the jobs due after it in the same tick. The first failure of a job is
  told at once. While the job keeps failing, a failure is told only when six hours have passed
  since the last message the channel took, and one in between is counted and not told: a job
  failing every five minutes for a day sends four messages, not 288. Every message of a failure
  now ends on a fourth line, "Nếu lịch còn hỏng, tin nhắc kế tiếp sẽ đến sau 6 giờ.", and from
  the second message that line first says how many failures in a row there have been and since
  when. When the job runs well again the channel gets one line, `Lịch "<name>" đã chạy lại được
  sau N lần hỏng liên tiếp.`, if it had been told of the failures and nothing if it had not. A
  message the channel did not take (no chat, a failed send, a minute gone by) leaves the job
  untold, so the next failure tries again without waiting, where 0.16.0 never tried again. The
  counts are kept in memory: a restart begins every job's count again, and a job still failing
  after it is told at once. A failed turn of a prompt job, or of the turn a `then_prompt` opened,
  is a conversation and is delivered as before; it is not counted here.
- A schedule saved in an agent's file is on the clock at once, with no restart. A save from the
  agent editor (`PATCH /api/agents/{id}`), a new agent (`POST /api/agents`), an installed
  template that joined the crew and an agent `POST /api/agents/reload` brought in all make the
  scheduler read the running crew's schedules again, `memory_consolidate` among them. An agent
  that already runs is still not read again by that reload. A new row runs from its first time
  after the save; a row whose `cron` or `every` changed, or that its file switched back on, is
  judged from the save by the timing it has now, and never for a time that passed under the row
  before it; a row whose prompt, command, script or name changed keeps the time it was going to
  run at, its pause switch and its count of failures; a row taken out never runs again, and its
  pause switch goes with it. A save of a key or of the shared routes, which builds every agent
  from its file again, also puts a schedule edited by hand on the clock. `restart_required` in
  the answer of a save stays and is always an empty list. `needs_restart` in the answer of
  `POST /api/agents/install` is true only when an agent that was written did not join the
  running crew (a file forced over an agent that runs), no longer whenever the template states a
  schedule. On the web, the "restart to apply" banner of the agent editor is gone: a save that
  changed the schedules says "Đã lưu. Thay đổi lịch chạy có hiệu lực ngay, không cần khởi động lại."
  until a field of the form is changed again or the form is reset, and Lịch chạy shows the new
  rows without a reload of the page.
- A save whose file cannot be written changes nothing. The order of a save is now validate,
  build, write, then swap: `agent.yaml` is written once the agent is built and before the
  running crew takes it. A write the system refuses (a full disk, a file that cannot be
  replaced) answers 422 with the system's reason and leaves the crew, the clock and every job's
  pause switch as they were, and a new agent whose file could not be written does not join the
  crew. 0.16.0 swapped first and answered 500, with the crew ahead of its file until the next
  restart.
- Every source file of the web is within the 200 lines the package's are held to, and
  `tests/test_file_size_budget.py` now holds `web/src` to it as well (`.ts`, `.tsx` and `.css`;
  tests and their helpers are not counted). Stylesheets and modules were split by concern, with
  no change to what a page shows.

## [0.16.0] — 2026-10-12

### Added

- An agent's own `agent.yaml` can take the script tool away from it. `script_calls: none` hands
  the agent no `tool_script`, whatever tools it holds and whatever a server offers to scripts, so
  the model writes no script in its turns. A schedule's `script:` of that agent still runs, and
  calls only the tools that read: that script is the owner's text in the file, not the model's.
  The master's roster says such an agent holds no `tool_script`. The key now reads one of three
  words, `none`, `read_only` (the default) and `gated`. Any other value stops the crew from
  starting with a line that names all three, and a YAML boolean (a bare `off`, `no`, `false`,
  `on`, `yes` or `true`) is told to write `none` or the one of the three meant.
- `script_llm: false` in the agent's own `agent.yaml` (default `true`, read from that file alone)
  keeps the agent's scripts from asking a model, in a turn and in a schedule's `script:` alike. The
  description of `tool_script` then tells of no `llm`, and a script that calls `llm.classify` or
  `llm.summarise` all the same is told "không hỏi model được ở đây.", a mistake it can catch: no
  model is asked, nothing is paid, and the call is neither on the run card nor among the calls the
  scripts of one turn may make. The script still counts it among its own 25 calls and ten askings,
  so one that catches each refusal and asks on ends at the eleventh. Only a real YAML boolean is
  taken: `"false"`, `0` or an empty value stops the start. A bare `off`, `no`, `on` or `yes` written
  by hand is one to the reader the server starts with, and a save of another key leaves the word as
  it was written. Both keys are in `GET /api/agents` and `GET /api/agents/{id}` under the same
  names, are taken by `PATCH /api/agents/{id}` and `POST /api/agents` (a wrong value is a 422 and
  nothing is written), and hold with no restart, from the agent's next turn and the next run of a
  schedule of its: there a save takes the script tool from the agent or hands it back. A turn or a
  job already running ends as it began, with the tool and the model it had.
- A schedule whose script failed tells the person. A script job opens no turn when its script
  fails, so nothing was sent on, and from the chat a failed job looked like one that ran well
  and printed nothing. When the run of the script itself ends `error`, the agent's channel now
  gets one message of the runtime's, three lines: which schedule it was (its name, as one line),
  why it ended, and where the run is on the web UI. Why is what ended the script: the line of its
  error, or the line that says none of what it stored could be kept. It is told on one line, whole
  up to 600 characters and by its first 200 and its last 400 past that. It holds nothing the
  script printed before it failed, which stays on the run's step, and never the script's text. A
  tool that failed is told in its own words, and an error the script raised says what the script
  wrote it to say, so what a call was given is in the message only where the failing tool says it
  back. A member's notice goes under its `[Name]` line, the master's as the bot speaks, and both
  are sent as every message to the chat is: `**bold**` and `*italic*` in the name or in the reason
  lose their asterisks. One message is sent for each failed run, with
  no grouping and no spacing, and a run started with `POST /api/jobs/{agent}/{id}/run` is told
  the same way. Nothing is sent for a script that ran well (whether it printed or not), for the
  turn a `then_prompt` opened (that is a conversation, delivered as a prompt job's is, failed or
  not), for a failed `command` job, for a run a server stop cut, or when there is no channel. A
  message that could not be sent, or was not sent within a minute, is logged
  (`job <id>: failure notice not sent`) and not tried again; the run stands as it ended and the
  jobs due after it still run. The run of a failed script is summed up the same way, by the line
  that ended it: on one line, its first 160 characters and an ellipsis when there is more, where
  it was the last 160 characters of all the script had said, what it printed among them.
- What scripts keep can be read whole and cleared out. `GET /api/agents/{id}/script-store` now
  says `limit_chars` at its root (262,144, the most each place may hold, which each place's
  `chars` is measured against), and each place says whose it is: `kind` (`job`, `conv`, or
  `other` for a name of neither shape), `ref` (the schedule's or the conversation's id; the job
  is `<agent id>/<ref>`), `title` (the schedule's name or the conversation's title, `null` when
  unknown or blank) and `orphan` (`true` when the schedule is no longer one of that agent's jobs,
  those made in a chat among them, or the conversation is gone). `GET
  /api/agents/{id}/script-store/value?namespace=&key=` gives one value whole, however long:
  `{namespace, key, text, chars, updated_at}`, 404 for a key that holds nothing and for an agent
  nobody knows. `DELETE /api/agents/{id}/script-store?namespace=&key=` forgets one key, or all
  the place holds when `key` is left out, and answers `{deleted: n}`; forgetting what is not
  there is `{deleted: 0}` and no mistake, and `namespace` must be named, so no call forgets all
  an agent kept at once. No route writes a value: only a script that ended well does. A script
  running while its place is cleared goes by what it had read and writes back only the keys it
  stored itself. Removing an agent (`DELETE /api/agents/{id}`) now drops what its scripts kept, so
  an agent later given the same id starts with nothing. Removing an agent stops nothing it is doing,
  so a script it is still running, or one a turn that outlives it begins later, runs to its end and
  keeps nothing: it is answered as a script that failed, with a line saying the agent it ran for was
  removed. That holds when another agent was given the id before the script ended. Such a script
  reads nothing under the id either: a `load` it first makes after the removal is answered with
  nothing, whoever has the id by then, and the script ends on the same line whether it stored or
  only loaded; what it had read before the removal it goes on reading. A save of the
  agent is no removal. A `namespace` or a `key` named twice, in a reading of one value or in a
  forgetting, is a 422 that names it: nothing is read or forgotten by a guess at which was meant.
- The agent editor on the web sets `script_calls` and `script_llm`. Its tools part ends with a
  "Script" section. "Script gọi được gì" is `script_calls`, one of "Không dùng script" (`none`),
  "Chỉ công cụ đọc" (`read_only`) and "Cả công cụ thay đổi dữ liệu" (`gated`), with a line under
  it saying what the choice leads to. "Cho script hỏi mô hình" is `script_llm`, and stays to be
  set on an agent that uses no script, since a schedule's script still runs there. An agent whose
  file writes neither key opens at what it runs with. A save sends only the key that changed and
  asks for no restart, the section says under its heading that both hold from the turn after a
  save, and a choice taken back leaves nothing to save.
  While the form holds both `gated` and a ticked "Tự chủ", the line under the choice is a warning
  that the agent's scripts change things and nobody is asked, and the same sentence stands under
  "Tự chủ" at the top of the form: whichever of the two is switched on second, the person reads it
  where they pressed. It goes by the form as it stands, before any save. The section ends with a
  link to what that agent's scripts keep. On a server that does not report a key yet (0.15.0
  reports `script_calls` alone of the two) the form reads it as its default.
  The **Công cụ** table marks `tool_script` with `⊘` ("agent được đặt “Không dùng script”") for an
  agent set to `none`, where `∅` stays the mark of an agent with no tool a script may call, and
  the legend line of `⊘` shows only when the crew has such an agent.
- The agent editor's tool list reads `listable_tools`. Under "Chỉ dùng các công cụ được chọn" each
  name the server tells is a row, described by the tools table where that has the tool, and the
  form keeps no rule of its own for which names a `tools:` list has a say over. So `delegate` has
  a row on an agent that hands work out, even while no agent holds the tool, and can be ticked
  back.
  A name the file's list holds and the server does not tell (a tool of another mode, one the
  machine cannot run now, one handed whatever the list says) keeps a ticked row of its own after
  the others, with a line under it ("Hiện giờ danh sách không đem lại công cụ này cho agent. Bỏ
  chọn thì tên này rời khỏi danh sách."), and is written back with the list until the person
  unticks it; ticking another row drops no name. A tool unticked and ticked again goes back where
  the file's list has it, which leaves nothing to save, and a name that list never held is written
  after the file's names, in the order of the rows. A save that changes nothing in the list sends
  no `tools`.
  The rows are those of the agent as saved. While the form holds an unsaved change of "Chế độ" or
  of "Có thể giao việc cho", a line under the list says to save that first: the answer to that
  save carries the new names. A row that goes with its tick while the keyboard is on it hands the
  keyboard to the row that took its place, else to the last row, else to the radio that is on
  above the list. On a server that reports no `listable_tools` the rows are the tools the table
  does not mark as a server's, as `tool_search` or as `tool_script`.
- A schedule's script is written in the agent editor, which in 0.15.0 showed such a row to read
  and offered no box to type in. "Làm gì" on a row picks one of "Nhắc agent" (`prompt`), "Lệnh
  shell" (`command`) and "Script" (`script`). A script row has a box for the script, sent
  character for character with no line break added at its end (so one of several lines is written
  to the file as a `script: |-` block), and a box for "Nhắc agent khi script in ra kết quả"
  (`then_prompt`) that may stay empty: the key is then not in the file, and emptying a box that
  held words takes the key out. Changing "Làm gì" carries no text from one kind's box into
  another's; while the row is on the page each kind keeps what was typed for it and gets it back
  when chosen again, and only the kind chosen at the save is written. Tab moves to the next box,
  so a script is indented with spaces, and a pasted tab is kept.
  The form holds a save over an empty script ("Nhập script cần chạy.", said once a save was tried)
  and over one past 20,000 characters (said as soon as it is, counted in characters as the server
  counts). It does not judge the Python: the server does at the save, and its 422 stands word for
  word over the form with all that was typed still there.
  A script row must have an id. What the script keeps is stored under `job:<id>`, and a row the
  file leaves unnamed is numbered by its place at every start, so a schedule added or taken out
  above it changes where the job reads and stores. A script row whose "Mã" is empty or only spaces
  is not saved, whether the row is new or was switched over from a prompt or a command: the box
  says why once a save was tried, and the hint under it says what the id is for in place of "Bỏ
  trống để tự đặt". The form fills no id in. A script row the server has numbered opens with that
  id in its box, so opening an agent is no change and nobody has to type; the next save of the
  schedules sends the id back and the file holds it from then on. Rows of the other two kinds may
  leave the id empty as before.
- The web shows what scripts keep. Quản lý → **Ghi nhớ** has a tab "Script giữ lại" with an
  address of its own (`#/manage/memory/scripts/<agent id>`), for one agent at a time; the link in
  the editor's "Script" section opens it on that agent. Each place is a block headed by its kind
  ("Lịch", "Cuộc trò chuyện", "Nơi khác") and its name: the `title`, else the `ref`, and for a
  place of neither shape the name it is stored under. That stored name stands beneath the heading
  when the two differ. A schedule's place links to that job's row in **Lịch chạy** and a
  conversation's to the conversation. An `orphan` place is marked "Không còn nơi dùng", says why
  it can be deleted and is no link. Under the heading stand the number of keys, the size against
  `limit_chars` and a bar. From 80% of the limit the bar changes colour and a line says the place
  is nearly full ("Sắp đầy: …"); at the limit it changes again and the line says it is full ("Đã
  đầy: …").
  Each key is a row with its size, when it was written and its `preview`. "Xem giá trị" reads the
  whole value into a box that scrolls on its own and that the keyboard reaches, set out as
  indented JSON when it reads as JSON and as it is otherwise, with a line saying so. A value
  written again since the list was read has the list read again, so the size and the time beside
  it are that writing's. A key gone by then is said to be gone and the list is read again.
  "Xoá" on a key and "Xoá tất cả" on a place ask first, naming the key and the place. Before "Xoá
  tất cả" asks, the list is read again, and the question counts the keys and names the place as
  that read found them, since a script may have written since; a place gone by then is said to
  have nothing left and nobody is asked. After a delete a line says what went, and the keyboard
  goes to the key that took its place, else to the last key, else to the heading of the place that
  took the emptied one's, else to the last place, else to the agent box. A refusal of the server's
  shows at the key's row or under the place's heading, and nothing moves.
  A key is whatever text a script took from what its tools read, so wherever the screen draws a
  key, a place's name or a title, or puts one into the name of a button, of a value's box or of a
  heading, into a question or into the line after a delete, the characters nobody sees are written
  out, one way everywhere: a quote, a backslash and a control character as JSON writes them (`\"`,
  `\n`, `\t`); the controls JSON leaves as they are, U+2028 and U+2029 the same way (`\u0085`,
  `\u2028`); a character that draws as nothing or as an odd space as its code (`[U+200B]`); and a
  space that opens or ends the name or stands next to another as `[U+0020]`, since a page folds
  those. Two keys that differ only in such a character therefore read differently in every place.
  In a question and in the line after it the name stands in quotes and is cut at 80 characters.
  The screen does not read again by itself while it is open: what a script writes meanwhile shows
  once the agent is chosen again or the page is loaded again. Between a new bundle on disk and the
  restart, the 0.15.0 server still running has the list alone: places show under the names they
  are stored by, with a size and no limit, mark or bar; "Xem giá trị" is answered 404, so the key
  is said to be gone, the list is read again and the row is back; "Xoá" and "Xoá tất cả" are
  answered 405, shown as a refusal, and nothing is deleted.

### Changed

- A tool call that failed keeps more of what it said on the run card. A step kept the first 160
  characters of an answer, which for a refusal is the complaint and not the way round it, and
  for a call that did not fit is the mistake and not how the tool is called. A failed call (a
  tool call of a turn, a call a script made, a script's asking of a model, the closing step of
  a command job or a script job) is now kept as one line, whole up to 600 characters, and past
  that as its first 200, an ellipsis and its last 400. `output` of such a step, and of a failed
  entry of a script's `calls`, is therefore up to 601 characters where it was up to 161. A call
  that went well stays at 160, as do a route that was passed over, what the model said, a
  question and the arguments of a call. A text kept that way has a cut in its middle, and the
  exported trajectory covers what the cut left of a secret on either side of it: its first
  characters before the ellipsis, as it did, and its last ones after it, where the cover looked
  only at the start of a text.
- The web shows why a step failed without a press, and whole. A failed step's answer was folded
  behind "Xem kết quả" in a box that scrolled, and a step heard while its run went on was cut at
  160 characters however it ended. A call that failed or was refused now stands open on the step
  of a run, on the tool card in the thread, on a script's call once the list of its calls is open,
  and on the card of a task handed on that failed. An answer within what a step keeps is shown
  whole, wrapped to the card and in no box that scrolls, and "Ẩn kết quả" folds it. The tool card
  in the thread holds all the tool answered, so a longer failure there is open and whole too, in
  the box that scrolls. A step that went well stays folded until it is pressed. A failed step
  heard while the run goes on is kept by the server's rule above, counted in characters and
  folding the white space the server folds, so it reads as the stored one that takes its place
  when the run ends.
- The message a script job opens a turn with is drawn as the schedule's prompt and what the script
  printed. That message holds the `then_prompt`, a sentence for the model and what the script
  printed between two marker lines, and the thread drew all of it in the bubble. The bubble is now
  the `then_prompt` alone. Under it stands a block "Script in ra" with what was printed, line for
  line, the number of its lines and "Đã đưa cho model làm dữ liệu, không phải lời dặn.". The block
  is open while short and folded past 12 lines or 800 characters; opened, it scrolls in a box of
  its own that the keyboard reaches, and a character nobody sees is written there as its code
  (`[U+200B]`). Only a message of the very shape the server writes is read this way: the closing
  line last, the opening line of the same number, and right over that the server's sentence, word
  for word. Any other stays the plain message it is. The stored text is untouched, so "Sửa và gửi
  lại từ đây" and the Markdown export use the message as it was stored.
- "Sửa lịch" on a job in **Lịch chạy** opens the agent's editor at that schedule's own row, where
  it opened at the heading of the schedules: the row is scrolled into view right under the
  editor's sticky bar and takes the keyboard. A job with no row in the form (the memory pass,
  `memory-consolidate`) lands on the heading as before. The way back still returns to that job's
  row in the list.

### Fixed

- A batch that changes things and was ended partway no longer leaves a later script of the same
  turn short of calls. A batch takes all its calls from what the scripts of one turn may make
  before the first runs; when a call was refused as its turn came, or the script's clock or a
  stopped turn ended the batch, the calls that never began stayed counted, and a later script
  could be ended for calls nobody made. They are now given back however the batch ended. A call
  that began stays counted.
- A script no longer asks a model once its conversation has spent all it may. The turn read what
  the conversation had spent before each call of a model it made itself, and never before the
  ones a script made, so a script went on asking, up to its ten, past the cost cap. Each asking
  is now refused before it is made or counted, and the script ends there ("cuộc trò chuyện đã
  chạm trần chi phí, script không hỏi model thêm được."), which it cannot catch. The askings
  before it were paid and stay on the run card. What the tasks the script handed on have spent
  counts as spent there from the moment each comes back, though the conversation is charged it
  only when the script ends: a script whose task took the conversation to its cap asks no model
  after. The script of a schedule runs in no conversation, so only its ten askings bound it.
- The refusal past the eight tasks a conversation may hand on no longer promises the next turn.
  It said a turn hands on at most eight and to hand the task on at the next one; the count is the
  conversation's, tasks handed on by a script among them, so the next turn was refused in the
  same words. It now names the conversation and says what is left: do the work itself, or tell
  the person a new conversation is needed.
- A conversation is no longer counted as handed on by a script it has nothing to do with. A
  script's child is found by the id of the call that ran the script with the nested call's number
  taken off, and an id that ended where the number would begin matched too. The child of a call
  that goes by that very id was then counted among the script's: in the eight tasks, in the
  conversation's tree and in the cost shown for it.
- The description of `tool_script` now says that `store(key, None)` forgets the key and keeps no
  value, so a model does not keep a `None` to mark a thing as done and read back a key that holds
  nothing. A `None` inside a list or a dict is kept as it is.
- A switch written by hand as a YAML 1.1 word no longer holds up every save of its agent.
  `shell_network: no` (or `off`, `on`, `yes`) starts the agent, because the reader the server starts
  with takes the word for a boolean. The library a save reads and writes with takes it for a text,
  and a save was validated by that reading, so every `PATCH /api/agents/{id}` on such an agent
  answered 422 (`shell_network must be true or false`), whatever key the edit was about. A save is
  now validated, and the running agent rebuilt, from the file about to be written as the next start
  will read it; the word stays in the file as it was written. The agent that runs after a save is
  therefore the one the next start brings up: a hand-written `max_steps: 010` stays 8, where a save
  of another key had made it 10 until the restart, a schedule row written `enabled: no` is still
  shown as off, and such a save no longer asks for a restart over schedules it did not touch. An
  edit that itself sends a word for a switch (`"shell_network": "no"`) is still a 422.
- An agent whose hand-written `agent.yaml` keeps a path outside the crew home can be edited from
  the web and the API again. Every `PATCH /api/agents/{id}` on such an agent (one that
  `agent add --workspace` aimed at a repo elsewhere, or whose file names a persona or a skills
  folder outside the home) answered 422 naming that path, whatever key the edit was about. The
  check now measures what the edit brings: a path outside the home is refused unless the running
  agent already has it, each kind against its own kind (the workspace against the workspace, a
  skills folder against the skills folders, a persona file against the persona files), so a
  workspace elsewhere vouches for no skills folder and no persona file. Moving an outside
  workspace to another place outside the home is still refused, moving it into the home is
  accepted, and a new agent still may name no path outside the home. An edit spells such a path as
  the file already spells it for that kind of path, or as the path itself with nothing left to
  follow. The file keeps the text an edit sent and every start follows that text again, so one
  that reaches the agent's tree through a link, or by going into a folder and back out with `..`,
  would lead wherever the link or the folder is moved to afterwards: it is a 422 that names the
  path to write ("Đường dẫn … đi qua liên kết hoặc ..; hãy ghi đường dẫn thật: …"), and nothing is
  rewritten on the person's behalf. Taking a key out is judged the same way, by the name the start
  then reads in its place. A hand-written file that spells its path through a link is still saved,
  and a path inside the home is judged as before, however it is spelled.
  A path is inside the home when its text is and where it leads is: the text read with nothing
  followed (`~`, the agent's folder before a relative text, `.` and `..` folded as text), and the
  place it resolves to. Where it leads was all that counted, so a link lying in a tree outside
  the home and leading into it was saved for a workspace, a skills folder and a persona file
  alike, and the agent followed it wherever it was pointed afterwards, with no restart for a
  persona. Such a text is now the same 422, naming the place inside the home to write, unless
  the file already spells it for that kind of path. This refuses what v0.15.0 took: a link
  outside the home that leads into it, and an absolute text that reaches the home through a
  link the home is named by (`/tmp/…` on macOS for a home under `/private/tmp`); a text
  relative to the agent's folder is unchanged.
- A message to Telegram on a line gone quiet no longer waits for ever, and no longer stops the
  schedules. A call that named no limit of its own (`sendMessage`, `sendChatAction`,
  `setMyCommands`, `getFile`, a photo or a document sent from a file) handed the HTTP client `None`,
  which it reads as no limit at all and not as its own 120 seconds. Such a send held whoever waited
  for it. The clock of the schedules runs its jobs one after another and waits for a job's message
  before the next, so one send that never came back kept every later job of every agent from running
  until the server was started again. A call that names no limit is now held to the client's own,
  and one that runs out ends as any call that failed does: a job's message is logged
  (`job <id>: delivery failed`) and not tried again. The long poll (35 seconds) and an upload from
  memory (60 seconds) keep the limits they name.
- A start no longer warns `tools lists unknown tool delegate` about an agent that lists `delegate`
  as the docs tell it to. Naming it is how an agent with a `tools:` list keeps handing work out,
  and the tool is handed once every agent exists, after the list was matched, so every such agent
  was warned at every start. The warning now tells three cases apart. A name that is honoured
  later (`delegate` on the master, a work agent or an agent that names `delegates`) is passed
  over. A real tool the list cannot bring is named with the reason in place of "unknown":
  `tool_script`, `tool_search` and a server's `mcp__…` tools come by what the agent holds and the
  servers under `mcp`, whether listed or not; `workspace_edit`, `workspace_grep` and
  `workspace_glob` come with `mode: work`; `delegate` is not given to an agent that hands work to
  nobody. A name no tool carries is still `tools lists unknown tool …`, word for word. The same
  judge now answers whoever edits the list: `GET /api/agents`, `GET /api/agents/{id}` and the
  answer to a save carry `listable_tools`, the sorted names a `tools:` list can bring that agent
  as it runs now (every tool made for it before the list is matched, so by its `mode`, with
  `image_read` only where the machine has a vision route it can use; and `delegate` where the
  agent hands work out). `tool_script`, `tool_search` and a server's tools are never among them.
  The names do not shrink to what the agent's own list holds, and a save that changes `mode` or
  `delegates` answers with the new ones. A name is told there exactly when a list holding it
  earns no warning, bar `image_read` on a machine with no vision route, which is neither told nor
  warned of.
- A run summed up by the end of a long text now shows that its start was cut. The run of a
  `command` job, and of a script job that ran well, is summed up by the last 160 characters of
  what was said, and a longer text lost its start with nothing to say so. Such a summary now
  opens with an ellipsis, 161 characters in all; a text of 160 characters or fewer is kept whole,
  as it was. A rewrite of memory or a wiki compile that failed is summed up by the start of its
  error as one line, with an ellipsis where it was cut, where it was the first 160 characters as
  they stood.
- A profile of the wrong shape is refused, and no longer crashes whoever reads it. Some shapes
  raised an error nobody reads as a bad profile: `persona_files` holding an entry that is no text
  (`[1]`, `[["a"]]`, `[{"a": 1}]`) or a name longer than the disk gives a file, `schedules` that
  is no list of mappings (`5`, `true`, `[5]`, `[[]]`), a schedule's `skills` that is no list, and
  a `workspace` or a `skills_dirs` entry written `~somebody` where nobody is called that. `PATCH
  /api/agents/{id}` and `POST /api/agents` answered 500 for each; a persona name too long was
  written to the file first, and the agents could not be listed after. `POST /api/agents/reload`
  answered 500 for such a file, or took a `persona_files` entry that is no text and brought up an
  agent nobody could list. Each is now a 422 that names the agent and the key
  (`agent coder: persona_files must be a list of names`,
  `agent coder: schedules must be a list of mappings`,
  `agent coder: workspace '~somebody/x' cannot be followed: …`), with nothing written and the
  running agent as it was, and a file written by hand that way stops the start with the same
  line.
- An edit can no longer bring a schedule whose `prompt` or `command` is not a text. A number, a
  list or a mapping there was saved, and the job failed when its time came. `PATCH
  /api/agents/{id}` and `POST /api/agents` now answer 422
  (`agent coder: schedule sang: prompt must be a non-empty string`). Only the rows an edit adds
  or changes are judged, so a row the file already holds that way does not hold up a save about
  something else.
- What a conversation outside the sidebar has spent no longer stands still on the web. The sidebar
  lists the master's conversations; one of another agent, such as that of an agent a task was
  handed to, is opened from a run card or from "Cần bạn xử lý", and no row of the list is read
  again for it when a run ends. The header's chip read what the thread heard as each turn ended
  and the overview card of the activity column read the conversation as it was loaded, so after a
  turn the two showed two amounts, and the overview and the hold on the composer of a conversation
  over its budget stayed at what the load found until the page was loaded again. Both now take one
  reading, the larger of the load and what the thread heard, since the server only adds to what
  was spent. Only a turn that ends `done` or `halted` says the amount: after a turn of this tab's
  that ends in an error, stops to ask the person or is stopped, the conversation is loaded once
  more, for both places.
- The web reads the crew again after a save on **Kết nối**. A key that is set or removed, and the
  routes saved for every agent, are applied to the running crew, which the server builds anew: a
  key can hand an agent a tool it did not hold, and an agent that names no route runs on the new
  ones. The tools were read again and the crew was not, so an agent editor opened next began its
  tool list without the new tool and showed the routes as they had been.
- Switching on an agent's tool list in the editor no longer writes every tool the crew holds. "Chỉ
  dùng các công cụ được chọn" began with every tool of the crew in the list, so the agent was
  listed tools only other agents get, `delegate` on an agent that hands work to nobody among them,
  each one a warning when the server starts. The list now begins from the tools the agent holds
  among its rows, and from all the rows for an agent that holds none of them.
- A schedule's command row keeps the `skills` its file lists. In the agent editor a row made a
  command was handed an empty list, so a command whose file lists skills counted as changed after
  a switch to a prompt and back, and a save wrote the list away. Each kind of row now keeps its
  own list.
- The keyboard is no longer left on nothing when an MCP server that `config.yaml` no longer
  declares is unticked in the agent editor. Its row goes with the tick; a keyboard that was on it
  now goes to the row that took its place, else to the last row, else to the radio that is on
  above the tools.
- The agent that runs after a save from the web is the agent the next start brings up, in every
  field. `PATCH /api/agents/{id}` and `POST /api/agents` built the running agent from its file
  alone and left out what a start adds once the file is read: the skill folders, commands and
  hooks of the crew's kit and of the agent's own (`.agents/`, `.claude/`, `.opencode/`). An agent
  edited or made from the web ran without them until a restart, or until a key or the model
  routes were saved. A master whose `agent.yaml` gives no `name` ran under the name `default`
  after any save, where a start calls it by the default's name. A start and a save now read a
  file through one function and add the kits through one.
- A removed agent's schedules leave the clock with it. After `DELETE /api/agents/{id}` the jobs
  its `agent.yaml` stated stayed on the clock: each time one came due the tick raised, and the
  jobs after it in that tick waited for the next. The jobs the agent was given in chat and the
  switch flipped on any job of its stayed in the database. Once an agent was made under the same
  id, all of them were that agent's: the jobs ran again, as it, switched as the one before left
  them. A removal now takes the three with it at once (the run history stays), an agent made
  under the id starts with none of them, and a job that comes due with no agent in the crew is
  left out with one log line while the rest of the tick runs.
  The web's box for removing an agent said only that the folder goes to `.trash` and is not
  deleted. It now also says, before the id is typed, what the folder does not bring back: what
  the agent's scripts kept, the jobs it was given in chat and the switch on each of its jobs.
- A whole number without end is refused as a bad profile. `max_steps`, `tool_output_chars` and
  the `chat_id` of a `telegram` block take a whole number, and `.inf` there (`Infinity` or
  `1e400` in a request) raised an error nobody reads as a bad profile: `PATCH /api/agents/{id}`,
  `POST /api/agents` and `POST /api/agents/reload` answered 500. Each is now a 422 that names
  the agent (`agent coder: cannot convert float infinity to integer`,
  `agent coder: telegram chat_id must be an integer`), with nothing written and the running
  agent as it was, and a file written by hand that way stops the start with the same line.
- A number is written to `agent.yaml` as the number the next start reads. A save writes through
  a library that shows a number the way Python does (`1e-05`, `1e+16`), and the reader the
  server starts with takes a number without a dot for a text: a `cost_cap_usd` of `0.00001` or
  `1e16` could not be saved from the web at all (422, "tệp ghi ra sẽ được đọc lại khác…"). Such
  a number is now written with `.0` before its exponent (`1.0e-05`), which both read as the
  number saved. A number written with an exponent and holding every digit a float has was
  saved once, then written back one digit off by the next save of anything else, which the same
  check refused: the agent could not be edited again until the number was set anew or the file
  mended by hand. It is now written back as the number it is. A number a person typed stays as
  typed, `1e-5` among them. `config.yaml` goes through the same writer when the model routes
  are saved, and there such a number was changed with nothing to stop it.
- Each schedule of an agent goes by an id of its own, at the start as over the API. An
  `agent.yaml` written by hand whose `schedules` put two rows on one id used to start with one
  of the two dropped: the later row ran, the earlier never did, and nothing said so. The pair
  may be an id written twice, a row with no `id` (which goes by its place, `job-1`) beside a
  row that writes that id, or a row named `memory-consolidate` while `memory_consolidate` is
  on. Such a file now stops the start, with a message naming the agent and the id
  (`Agent coder: hai lịch cùng mã job-1; mỗi lịch cần một mã riêng.`): give each row an id of
  its own before upgrading. A save from the web and `POST /api/agents/reload` over such a file
  are a 422 in the same words, whatever the save changes, and the refusal an edit already got
  for bringing such a pair now names the agent too. Ids are compared as the texts they are,
  capitals apart. Two agents may each have a schedule of one id, as before: the clock knows a
  job by its agent and its id together.
- An install that is refused leaves the home as it was. `POST /api/agents/install` wrote the
  template first and read the crew afterwards, so a refusal could come after the write: beside an
  `agent.yaml` the start cannot read it answered 500 and left the new folders, and a workspace
  that is a file did the same. The id and the template were used as path segments unchecked: an
  `agent_id` of `../../out` wrote the agent outside the home, `a/b` two folders deep in it, and a
  `template` of `../templates/kongming` read a template from wherever that led. An `agent_id` of
  `default`, or with `force` the id of an agent a kit brings, wrote a folder that stopped the
  next start or took the id from its holder. Now everything the request names is checked and the
  home read before a file is written: 422 for an id that is no agent id
  (`Mã agent chỉ gồm chữ thường, số và dấu gạch ngang.`), for a home that cannot be read as a
  crew, in a sentence naming the file, and for a workspace that cannot be a folder; 404 for a
  template that is not one of the bundled ones by its plain name; 409 for the master's id and
  for the id of an agent that runs with no `agent.yaml` of its own, whatever `force` says. When
  what was written still cannot join the crew, the folders the install made are removed and each
  file it wrote over holds what it held. `agent add` on the command line refuses the same ids
  and template names and prints why.
- `POST /api/agents/reload` takes in every folder copied in, or none. An agent whose workspace
  cannot be a folder was a 500, and the folders read before it had joined the running crew by
  then while the ones after it had not. It is now a 422 naming the path, with the crew as it was.
- An `agent.yaml` that does not parse is refused by name. The start reads the file with one
  library and the routes caught the error of another, so a syntax error in any agent's file was
  a 500 on `POST /api/agents/reload`, on an install, and on saving a key or the model routes.
  Each now answers in the words a broken file gets elsewhere, with the path of the file in front
  of the parser's line and column (422 on a reload and an install, 409 on a key or the routes
  with nothing saved), and the start stops on the same sentence.
- A markdown file whose front matter is not YAML costs that one file. A description with a
  second colon in it (`description: Use when: the tests fail`) is the usual case. One such file
  among the home's skills, or the agents or commands of its kit, stopped the start of the whole
  crew with the parser's own error, and a persona file that opens with such a block failed
  every turn of its agent. An agent, a command or a skill in such a file is now left out and
  named in the log while the rest load, and a persona is read as written, block and all. A
  skill whose front matter parses but states no keys (a line of plain words between the two
  `---`) stopped the start the same way and is now a skill with no description, by its file
  name.

## [0.15.0] — 2026-10-12

### Added

- An agent's scripts can call the tools that change things too, when its owner says so.
  `script_calls: gated` in the agent's own `agent.yaml` (default `read_only`, read from that file
  alone: no global key, no environment variable, inherited from nobody) lets a script run by
  `tool_script` call every tool the agent holds that writes or asks first (`workspace_write`,
  `shell_run`, `memory_save`, the canvas tools, a server's tools not under `read_only`), beside
  the ones that read. Each such call is put to the approval gate before it runs, by the rules a
  direct call meets: it runs where a direct call would run unasked (an autonomous conversation, a
  tool the person said to always allow, a command on `shell_allow_patterns`). A script never waits
  for a person, so a call a person would be asked about (a supervised conversation, a command on
  `shell_ask_patterns`) ends the script there, unrun, with a line that tells the model to make the
  call directly; so does a command on `shell_deny_patterns`. The line names the tool and the
  owner's pattern and never repeats the command, which may hold a secret. `ask_user` and
  `schedule_create` stay out of every script, as do the tools no script calls and a server's
  `hidden` tools. A batch with a call that changes things runs one call at a time in the order
  written. Every call of it is put to the gate before the first is made, and one the gate refuses
  means none of them runs. Each call after the first is put to the gate again as its turn comes,
  since what an earlier call left behind, or a person taking back what they had allowed, may
  change the answer: one refused then ends the script there, the calls before it ran and stay, and
  the ones after it are not made (they still count among the calls the scripts of one turn may
  make). A tool the agent no longer holds when its call comes, as when its server was signed out
  while the script ran, ends the script the same way. A call that went through the gate carries
  `gated: true` wherever a script's calls are listed (`calls` on the `tool_result` event and the
  run's step, the `nested_call` event, the stored result); a call that only reads is written as
  before. A script of such an agent that a restart cut is closed as cut and not run again, since
  nothing says what it had written. The master's roster says of such an agent that its scripts
  call the tools that write. Any other value of the key stops the crew from starting and is a 422
  through the API.
- A script can keep a thing from one run to the next. `store(key, value)` keeps a JSON value,
  `store(key, None)` drops the key and `load(key)` reads it back, or gives `None` when nothing
  is kept under it. The two are names of the script like `print`, not tools: they are none of
  the 25 calls or the 40 lookups, are not on the run card and are not put to the approval gate,
  so an agent whose scripts only read keeps things too. A script reads its own writes while it
  runs, and they are written only when it ends well, all of them at once: one that failed, was
  ended by the gate or a limit, ran out of time or was stopped keeps nothing. A script whose
  calls only read is run again when a restart cut its turn; one cut after it had ended and kept
  its values, and before its answer was saved, runs again over what it kept, so a count kept
  this way can count that run twice and a model it asked is paid twice. Where a value is
  kept is the server's to say and never the script's: the script of a schedule keeps under
  `job:<schedule id>` and so does the turn a job opens, a prompt job's too; any other turn,
  the one a person takes up in that conversation among them, keeps under
  `conv:<conversation id>`. Each place is one agent's own, and a script with neither a job nor
  a conversation is told there is nowhere to keep it, which it can catch. Deleting a
  conversation deletes what its scripts kept.
  A key is at most 200 characters, a value 65,536 as the JSON it is kept as, and one such place
  262,144 for its keys and values together, measured as it would stand after the write. Over
  any of them, or a value JSON cannot write (a set, NaN, a dict whose keys are not text), is a
  mistake the script can catch, and that write is not made. The place is measured again when
  the writes are made; if another run has filled it since, none of them is made and the script
  is told so as one that failed. `GET /api/agents/{id}/script-store` shows what an agent's
  scripts keep, by place: each key with the beginning of its value, its length and when it was
  written. Nothing writes or deletes through the API. The values live in a new table,
  `script_store`, made when the server starts; no table that was there changes.
- A schedule can run a script instead of asking the model. A row of `schedules` in `agent.yaml`
  takes `script` (the source, checked when the file is read as a turn's script is before it runs)
  in place of `prompt` or `command`, and exactly one of the three; `then_prompt` may stand beside
  `script` and nowhere else. When the job is due the script runs with what `tool_script` runs with
  for that agent (the same tools by `script_calls`, the same limits), whether or not the agent
  holds `tool_script`, and no turn of the agent is opened: a model is asked only if the script
  asks one itself (`llm.classify`, `llm.summarise`, below). Nobody is there to be asked either:
  the approval gate treats the job as an autonomous conversation, so a command on
  `shell_ask_patterns` or `shell_deny_patterns`, or a tool with a reason of its own to ask, ends
  the script there, unrun, and nothing waits. The job is a run with no conversation and one
  `tool_script` step holding the calls it made, `done` or `error`, summed up by the end of what it
  printed or of the error, and the calls that paid a model are charged to it. A tool that works
  through a conversation has none there and says so. With `then_prompt`, a script that ended well
  and printed something opens one turn the way a prompt job does. The turn's message is
  `then_prompt`, then one sentence saying that what follows is what the schedule's script printed
  and is data to work on, not instructions, then what was printed (cut to `tool_output_chars`)
  between two marker lines. The lines carry a number made for that one message after the script
  ended, so nothing the script printed can write the line that closes them. What a script prints
  is what its tools read (a mail's subject, a page), and nobody is asked in that turn; the fence
  keeps it from reading as the owner's own words, and holds no model to anything. The answer is
  delivered by the rules of a prompt job. A script that printed nothing opens no turn and tells
  nobody. What the script kept with `store` is written before that turn opens, and the turn's own
  scripts read and keep under the same `job:<schedule id>`. A schedule row, as the API reads and
  writes it and as `GET /api/jobs` lists it, always carries `script` and `then_prompt` (`null`
  when unused) and says `kind: "script"`; a row that names none or two of the three, or a script
  that could not run, stops the crew from starting and is a 422 through the API. `schedule_create`
  still makes prompt jobs only.
- A script can ask a model a small question of its own. `llm.classify(text, labels)` gives back
  one of `labels`, as the script wrote it, and `llm.summarise(text, max_chars=500)` a summary of
  at most `max_chars` characters. The server makes the call, with the agent's own model on the
  first of its routes and no other (no fallback route, no escalation route), offering no tool
  and asking for the least reasoning where the route states an effort. The process that runs the
  script is handed the answer as a text and nothing else of the call, and holds no key. The text
  is put to the model in a message of its own, fenced as data to work on and not instructions;
  what holds whatever the text says is how the answer is read. `classify` hands back a label the
  script gave (the answer trimmed and compared without case, or the one label that occurs in it)
  and any other answer is a mistake the script can catch, in fixed words that repeat nothing the
  model said; a summary is cut to `max_chars`. Each asking is a call of the script: one of its
  25, one of the calls the scripts of a turn may make between them, and one of at most 10 a
  script may put to a model, the eleventh ending the script. `text` is at most 20,000 characters
  and is never cut on the way: a longer one is a mistake the script can catch, as are labels
  that are not 2 to 20 different non-empty texts of at most 100 characters each and a
  `max_chars` outside 1 to 4,000. An asking is listed with the script's calls wherever they are
  listed (`calls` on the `tool_result` event and the run's step, the `nested_call` event, the
  stored result) under the name `llm.classify` or `llm.summarise`, with a preview of what was
  asked and of what was answered, `metered: true` and what it cost; `received_chars` counts
  what it handed the script. Its cost reaches the run and the conversation once, and the usage
  ledger files it as a side call of a new purpose, `script`, under the turn's conversation. A
  model that could not answer is a failed call of the script, charged as one of unknown cost,
  and a mistake the script can catch. An agent whose scripts only read asks as one with
  `script_calls: gated` does, and so does the script of a schedule, whose side call is written
  with no conversation and whose cost lands on the job's run.
- A canvas written by a script (`artifact_create`, `artifact_edit`, `artifact_rewrite`,
  `artifact_import`, for an agent with `script_calls: gated`) is the canvas a direct call would
  have written: linked to the turn's conversation, under the agent's name, counted with the
  turn's own writes against what one turn may write, refused to a turn that came through the
  inbound API, and nobody is asked, since no canvas write waits for a person. What is kept of
  such a call opens with the canvas tag whole (`[artifact <id> v<n>]`), which is where the web
  opens the canvas from. `artifact_read` stays out of every script, so a script cannot write
  over a version a person saved that its conversation has not seen. The script of a schedule
  has no conversation, and each canvas write fails there in words that say a canvas needs one,
  which the script can catch. On Telegram the message that lists the canvases a turn wrote names
  a canvas a script wrote as well, read from the calls the script's result lists (live, or from
  the stored run when a job's brief is delivered) and never from what the script printed.
- A script can hand a task to another agent. `tools.delegate(task=..., agent=...)` is a call a
  script makes where three things hold: the agent's file says `script_calls: gated`, the agent
  holds `delegate`, and the script runs in a turn of the agent's own. Anywhere else (an agent
  whose scripts only read, a task the agent was itself handed, the script of a schedule, which
  has no conversation to be the parent) the call ends the script, unrun, with the line that
  tells the model to call the tool directly, and the description of `tool_script` speaks of
  handing tasks on only to an agent whose scripts do. The approval gate is not asked, as it is
  not when the model calls `delegate` itself: what the other agent then does is put to the gate
  in its own conversation. A task for an agent outside the ones this agent may hand to ends the
  script before any call of its batch is made, with a line that names the agents it may hand to
  and does not repeat the name it was given. Each such call is carried out under a call id of
  its own, `<tool_script call id>:<number of the call in the script>`, which the conversation
  it opens is linked to, so a script run again under the same id finds the conversation each of
  its tasks opened and opens none. The tasks of one `tools.batch` are handed on side by side, at
  most three at a time, and answered in the order written; a batch that also holds a call that
  changes things is made one call at a time. A task a script hands on is one of the eight a
  conversation may hand on, counted with the ones the model handed on itself, and one too many
  is a mistake the script can catch. A script that may hand tasks on is given 1,800 seconds in
  all where any other is given 300; how long it may compute and how long it may stay silent are
  as they were. A task whose agent stops to ask a person holds the call as a direct one does,
  for as long as the script has left. When the script's time is up it ends as one that ran out
  of time, and the conversations it opened go on as the runs they are. Such a call is listed
  with the script's calls under the name `delegate`, with the beginning of the tool's answer
  (`conversation=<id> status=... spent=$... steps=...`) and a new key, `child_spent_usd`: what
  the conversation it opened spent, written only when above zero and never as `null`. Its
  `cost_usd` stays `null` and its `metered` `false`. The script's own result carries the sum
  over the tasks that ended, however the script itself ended, and the conversation that ran it
  is charged that once. `relay` means nothing in a script: the answer of a task is the script's
  to use and never becomes the turn's reply. The conversations a script opened are found where
  a direct call's are: in the count of tasks handed on, in a conversation's activity
  (`GET /api/activity/runs` with `conversation_id`) and in the exported trajectory, where such
  a child's `tool_call_id` is `<tool_script call id>:<number>`. On Telegram the message that
  lists the canvases a turn wrote does not name a canvas written by an agent a script handed a
  task to: of a script's calls it reads the ones that write a canvas, and what is kept of a
  task handed on is the beginning of its answer only.
- The web shows all of the above where a script's calls and an agent's schedules already stood.
  **Lịch** names a script job by its kind ("chạy script") and shows the script as it was written
  and the `then_prompt` that follows it. The agent editor shows such a row to read (the script
  whole, with a line saying it is changed in `agent.yaml`), lets its name, timing and switch be
  changed and the row removed, offers no box to type a script in, and sends the script back as
  it came when anything else is saved. A call that went through the gate says "qua cổng duyệt"
  on its row of the script's list: on the chat card, on the run's step and in the exported
  conversation. An asking of a model is listed in words ("Phân loại bằng model", "Tóm tắt bằng
  model") with what it cost, never as a tool, and the usage breakdown by purpose names the new
  one ("Script gọi model"). A task a script handed to another agent says what that agent spent
  ("Cuộc con đã chi …"), apart from what the script's own calls cost, and opens the conversation
  the task ran in, which hangs under the turn that asked as one opened by a direct `delegate`
  does. A canvas a script wrote has its card under the script's card and opens beside the thread
  on a wide screen once the script is done.

### Changed

- A save from the web writes a text of several lines into `agent.yaml` as a block (`prompt: |`,
  `script: |`), each of its lines on a line of the file, the way a person writes one by hand. It
  was one quoted line with `\n` in it, and a hand-written block became that line the first time
  the agent's schedules were saved. A text holding a tab, a carriage return or a character that
  does not print is still written in quotes, since a block would not hand it back whole. The
  text read back is the text saved, to the character, either way.
- A save is looked at as the next start will read it, before anything is written or rewired.
  `agent.yaml` is written by one YAML library and read at the start by another. The file as it
  is about to be written is read by the start's reader and set against the file as that reader
  reads it now with the edit's keys set. If any key would read back as something the edit did
  not ask for, the save is a 422 that names the keys, the file stays as it was and the running
  crew is not touched; a file the start's reader cannot read at all is refused the same way,
  with the reader's own words. Both sides are read by the one reader, so a value a person wrote
  by hand that the two libraries read differently (`enabled: no`, `max_steps: 010`) holds up no
  save.
- A save no longer wraps a long line of `agent.yaml`: a long text stays on one line of the file,
  and a line a person had wrapped by hand is written back unwrapped the first time its key is
  saved.
- The line that sums up a script's calls on its card reads "Script đã thực hiện N lời gọi" (it
  read "Script đã gọi công cụ N lần"), and a run stopped on the calls of a turn says "Đã dừng vì
  script dùng hết số lời gọi của một lượt.": some of a script's calls now ask a model or hand a
  task to another agent, and name no tool.

### Fixed

- A text saved from the web could be another text at the next start, or no text at all. A long
  text written in quotes was wrapped at about 80 columns, and where the wrap fell right after an
  escape (a tab, a lone carriage return, a backslash, U+0085) it was read back with a space it
  never had; a long plain line could lose one of two spaces. No line is wrapped now. A text of
  one line that the start's reader takes for something else was written bare: `No` or `on` was
  read as a boolean and `1:30` as a number, and a schedule whose prompt was such a word stopped
  the crew from starting; a bare next-line character (U+0085) was read as a space. Any one-line
  text the start would not read back as itself is now written in quotes.

## [0.14.0] — 2026-10-11

### Added

- A script can look up the tools it may call instead of guessing. `tools.names()` lists their
  names, `tools.search("words", limit=5)` ranks them the way `tool_search` does (only tools a
  script may call, ten at most, each with a one-line description) and `tools.describe("name")`
  gives how the tool is called, what it does and every parameter with its kind, whether it is
  required and what it is for, nested ones by path (`filter.owner`, `pages[].title`). A lookup
  runs no tool: it is not one of the 25 calls and not on the run card, and a script may make 40
  of them. A tool the description of `tool_script` does not name is found by one script and
  called by name from the next.
- A script can ask for calls that do not wait on one another together. `tools.batch([{"tool":
  "name", "args": {...}}, ...])` takes up to 10 calls, makes them side by side (four at a
  time, each through the agent's own hooks as a call made alone is) and returns a list with one
  answer per call, in the order they were written: `{"ok": true, "output": ...}` or
  `{"ok": false, "error": ...}`. One call that fails is its own answer and spoils none of the
  others, and so is one that breaks outside its tool (an answer that could not be kept, say),
  alone or in a batch: the script is told `Công cụ lỗi: <kind of error>` and goes on. Each call of a batch is one of the 25, and the run card lists them in written order.
  A script ended while a batch is under way (its clock ran out, the turn was stopped) keeps the
  calls that had ended, where they were written.
  A batch asked for the wrong way (empty, longer than 10 or than the calls left, an element that
  is not `{"tool", "args"}`) is a mistake the script can catch and costs no call. A batch with a
  call the script may not make (it writes, asks first, or is hidden) runs none of its calls and
  ends the script, as that call would alone.
- The calls a script makes are shown as they end, not once the script is over. The turn sends a
  `nested_call` event (`tool_call_id`, `index`, `call`) between the script's `tool_call` and its
  `tool_result`; the run card and the tool card in the chat list each call when it ends, and the
  run and the conversation add its cost at once. When the result arrives the list is put in the
  order the script wrote the calls and only the calls no event told of are charged, so nothing
  is counted twice. Stopping the turn while a script is calling ends the call it is on, and the
  calls it had made stay charged to the conversation as they are billed to the run.
- A script's result says what the script saved the model from reading: how many characters its
  calls handed it and how many it printed (`received_chars` and `printed_chars` on the
  `tool_result` event and on the run's step). Both cards show them on one line under the calls
  once the script has ended ("Nhận 184.220 ký tự từ 12 lời gọi, trả về 640 ký tự"), with a dash
  for a number that was not counted. The second number is what the script printed: a result
  longer than the agent's `tool_output_chars` is shortened after it is counted, as any tool's
  is, so the model may read less than that.
- The tool card in the chat still lists a script's calls after a reload. The calls and the two
  measures are stored with the script's result, beside the output and never sent to a model; a
  branch of the conversation copies them, and the Markdown export lists them under the agent's
  turn as a numbered list of names, failures, durations and costs, without arguments or answers.
- A tool's answer longer than the 200,000 characters a script is handed is no longer lost past
  the cut. The script gets the first 200,000 and a line saying how many are left and how to read
  on: `tools.tool_output_read(id="<the script's call id>.<n>", offset=200000)`, where `n` is the
  number of the call. The whole answer is kept, up to 5 MB, where a turn's long results are.
  A script reads on in segments as long as it may hold, close to 200,000 characters each
  unless it asks for fewer, whatever the agent's own `tool_output_chars`: a million characters
  take five more calls. A call the model makes itself is held to the agent's cap as before.
  Nothing is kept for a call that failed or for an agent without `tool_output_read`; those
  are cut as before. What `tool_output_read` answers a script is sized to fit, so it is never
  cut and never kept as another answer.

### Changed

- The scripts of one turn share a count of the calls they may make: ten for each call of the
  model the turn is allowed (`max_steps` × 10, 120 by default), on top of the 25 calls of each
  script. The script that would pass it is ended there in a way it cannot catch, a batch that
  does not fit whole makes none of its calls, the calls the model asked for after that script
  are closed unrun, and the turn halts with the reason `nested_calls`, which the web and
  Telegram say in words. A name no tool has is not counted, and the next turn starts from
  nothing.
- A script that prints more than 60,000 characters is no longer ended at the line that passed
  the limit. It runs on, and its result keeps the first 45,000 characters and the last ones
  around a line saying how much was printed and how much was left out, never more than 60,000
  in all. The agent's `tool_output_chars` (8,000 unless set) still applies to that result as
  to any tool's, so the model reads all of it only where that cap is as wide. A script that
  prints without end is still stopped by its steps.
- A script (`tool_script`) may now call every MCP tool the owner lists under `read_only` and does
  not hide, however far the tool is let in. Until now such a tool also had to be set to
  `codemode`, which made letting a script in a second decision on top of saying the tool only
  reads. The level now decides only whether the description of `tool_script` names the tool
  with its parameters (`codemode`) or it has to be found, by a script with `tools.search` or by
  the model with `tool_search`; the tools it does not name are counted on one line, and a name
  learned from a search is as good as a listed one.
  Tools that write or ask first, and tools set to `hidden`, are refused as before: the script
  ends there with a line saying to call the tool directly, where the approval gate sees it. The
  Connections card says what the level now decides.
- `tool_script` no longer comes with an MCP server. Every agent that holds at least one tool a
  script may call has it: a built-in tool that only reads (`workspace_read`, `memory_search`,
  `skill_read`, …) or a server's tool listed under `read_only` and not hidden. Like
  `tool_search` it follows neither the agent's `tools:` list nor its `mode`; an agent left with
  nothing a script may call (say `tools: [workspace_write]` and no server) does not have it.
  `artifact_read` only reads and is still not a script's to call: reading a canvas to its end is
  what tells `artifact_rewrite` the agent has seen the version the person last saved, and a
  script hands the model only what it printed. A script that calls it ends with a line saying
  to call it directly; `artifact_list` is a script's to call.
  It stands after the agent's own tools, `delegate` and `tool_search`, ahead of the servers'
  tools, and is handed again with a fresh description whenever a server connects, drops or
  changes. The description names the agent's own tools first, one line each with their
  parameters, then the servers' tools set to `codemode`, thirty lines in all; whatever is left
  of either kind is counted on one last line that points to `tools.search`. The master's
  roster tells `tool_script` like any other tool, so it is named only for an agent that differs
  from the master in it.
  In `GET /api/tools` the row of `tool_script` carries `with_reads: true` in place of
  `with_mcp`, names every agent that reads, and shows the description the first of them is
  given. The Tools table marks it "đi kèm công cụ đọc" and draws `∅` for an agent with no tool
  a script may call, with a legend line of its own.
- A script that calls a name no tool has no longer ends there. The call fails in a way the
  script can catch, naming the nearest tool it may call and pointing to `tools.names()` and
  `tools.search`; it still counts toward the 25 calls. A call that failed because a required
  parameter was left out, or one the tool has no place for was given, is answered with the
  tool's own words and a line saying how the tool is called. Refusing a tool the agent holds but
  a script may not call (it writes, asks first, or is hidden) still ends the script. The names
  `names`, `search`, `describe` and `batch` belong to `tools`, so no built-in tool can take them.

### Fixed

- The agent editor no longer writes the tools an agent holds into its `tools:` list. The crew
  list reports `tools` as the names an agent holds, which is never empty and counts the tools no
  list gives (`delegate`, `tool_search`, `tool_script`, a server's tools); the editor read it as
  the allow-list. Every agent opened on "Chỉ dùng các công cụ được chọn" (only the chosen tools)
  with everything ticked, and one tick saved the whole of today's toolbox as its list: an agent
  that listed nothing, and so got every tool its mode grants, was capped from then on, and the
  server warned of an unknown tool for each name no list gives. The Tools grid read the same
  names and marked every tool an agent lacked as left out by its list, so the marks for a
  missing key and for work mode never showed. `GET /api/agents` now carries the list as the file
  writes it in `declared.tools`, beside `declared.delegates` and `declared.schedules`, and both
  screens read that. A list an earlier save wrote stays as written: take the names it should not
  hold out of the agent's `tools:`, or choose "Dùng tất cả công cụ hợp lệ" (every valid tool) in
  the editor to drop the list.
- A tool's answer holding half of a character no longer breaks the turn that reads it. A server
  that cuts its text between the two code units of an emoji sends one half (a lone surrogate),
  which no database row, file or request to a model can carry: storing the result raised, and
  an answer long enough to be kept for reading back raised before it was kept. Each half is now
  replaced by U+FFFD where a tool's answer comes in, in the tool's own error message too, and
  the rest of the answer is left as it was.
- What a run keeps of a call's arguments is now held down in width as well as in length. Each
  value was already cut at 160 characters, but every name was kept, so a call given a mapping
  of hundreds of names was written to the store whole and sent again with every later step of
  the run. A step, and each call a script makes, now keeps the first twelve arguments, a name
  cut like a value and a number written out longer than that cut as text, and one last entry
  `…` saying how many more there were ("còn 288 tham số nữa"). The tool is handed every
  argument as before, and so is the person asked to approve a call.

## [0.13.0] — 2026-10-07

### Changed

- The master is now told what every agent it can hand work to holds at that moment, instead of
  only the description its owner wrote. Under each agent's line of the crew roster the system
  prompt carries lines read from the running crew each time a prompt is built: the MCP servers
  the agent reaches and whether it reads and writes there, only reads, waits for the owner to
  sign in or cannot connect; its skills, with what a skill the master lacks is for and whether
  a command it needs is missing on this machine; the scheduled jobs that are switched on, those
  made in a chat included; its tools; its model and the model a stuck turn moves to. Tools and
  skills are told against the master's own ("như của bạn, thêm: …") where that is shorter. A
  server is told by its connection first, so a sign-in that ran out or a key the server stopped
  taking shows as out of reach although the agent still holds the tools; one whose tools the
  owner (`read_only`) or the server itself (`readOnlyHint`) all mark as only reading is told as
  read-only. Nothing is cached, so the lines change when what the agent can use changes: a
  server that connected or dropped, an OAuth sign-in, a job made in a chat or switched on or
  off, and an agent added, removed or edited through the web UI or the API (`mcp`, `tools`,
  `routes`) reach the master on its next model call with nobody editing a description; a new
  skill file is told once the agent is built again (such an edit, or a restart), which is also
  when the agent itself first holds it. A
  closing note tells the master that these lines outrank the description and what it said
  earlier in the conversation, to hand over work that needs something another agent holds
  rather than answer that it cannot be done, and, when the server such work needs is waiting
  for a sign-in or cannot connect, to say so to the person instead of handing the work to an
  agent that cannot reach it. A job or skill name is told on one line whatever it contains, so
  a job named in a chat cannot add lines to the roster. What an agent does only through its
  persona or through scripts in its workspace is still told by `description` alone.

## [0.12.0] — 2026-10-07

### Changed

- A turn started from the web now belongs to the server, not to the tab that sent the message.
  Closing the tab, reloading or opening another conversation no longer cuts the turn short: the
  server reads it to its end, and Stop is what ends it. A tab opened in the middle of a turn,
  whoever started it (another tab, Telegram, a job), now shows what the turn has written so far
  and follows it live through `GET /api/conversations/{id}/turn`, instead of showing nothing
  until the answer is stored. The text being written is kept in memory only; after a restart the
  stored conversation is the whole truth. `POST /api/conversations/{id}/stop` now also answers
  `cancelled`, and ends a turn the web started from any tab. Deleting a conversation ends the turn
  the web started or the queue runs for it, once the delete has held, and that run closes as
  interrupted; a turn a bot or a job reads is not ended by it, as it is not by Stop. A tab that only
  reads a turn along still says how it ended once the run's end has been read back: that it was
  stopped from that tab, ended in an error, stopped short or went on by another route. A tab does
  not join again a turn the server has just ended on its own Stop.
- When the server stops under a Telegram turn, the bot now says the turn will be carried on once
  the server is back, instead of saying it was cut off. A bot restarted while the server stays
  up still says the turn was cut off, since nothing will carry it on.
- A home runs one server at a time. A server takes its home directory for itself before it opens
  what is kept there and holds it until its process is gone, however that ends. A start that
  finds the home held reads nothing of it, says which home it is and exits 1, whatever port it
  was given and with `--no-schedule` too. Such a start used to close the running server's runs
  in the record before it failed to bind the port, and would now have carried each of its
  turns on a second time. Trying things out beside a crew that is up wants its own
  `MY_AGENT_HOME` and port. The `agent` subcommands hold nothing and work as before.
- The summary of the previous conversation and the daily notes of yesterday and today are no
  longer part of the system prompt. A turn reads them in a framed block in front of the message
  that opens it, stored with that message, and a later message carries only what changed since:
  the lines added to a note, the new text of one that was rewritten, or a line saying a note is
  gone. One `memory_save` used to change the text in front of the whole conversation, so the
  provider's cache of everything said so far was lost: on the owner's install the model call
  right after a `memory_save` had 15.1% of its prompt tokens billed as cached, against 85.5% for
  the others (4 of 334 calls in ten days). The system prompt now changes only with the date,
  and the history is a prefix that only grows. A turn learns of a note it saved itself from its
  own tool call; the conversation is told with the next message that opens a turn. A
  conversation begun before this reads the memory as it is now in front of its first message
  until its next message is stored. `GET /api/agents/{id}/prompt` also returns `opening` and
  `opening_chars`, what a new conversation's first message would be read after, and the agent
  editor shows it under the prompt; a run's trajectory carries each message's block as
  `turn_notes`. A line of the frame counts only where the block was put: inside a note, a tool
  result or a message it is read in round brackets, so nothing a person or a tool wrote can end
  the block early or pass for one. The messages the web is sent are unchanged.

### Added

- A message sent twice is said once. Each send from the web carries a `request_id`; when the
  answer to a send is lost on the way back and the same words are sent again, the server stores
  nothing new and starts no second turn. It answers with what became of the first send: the same
  place in line while the message waits, or the conversation as it stands and the turn under way.
  The web keeps the name of an unanswered send until the page shows that message as said: sent again
  before then, the same words are the same message. Once the conversation shows the message, the
  page takes the words it handed back out of the box again, unless the person has changed them; the
  same words typed after that are a new message with a turn of its own, as when a person reads the
  answer and sends "go on" a second time.
  The name is stored in the same transaction as the message it names, is kept across a restart,
  and is left unused by a send the server refused or a message Stop handed back. `POST
  /api/inbound` takes no `request_id`.
- A turn cut by a server restart is carried on when the server is back, once. The run that was
  cut is reopened as the same run, with its timeline and what it had spent, and goes on from the
  stored conversation; whoever was reading that kind of turn reads the rest (the bot answers a
  Telegram chat, a job's answer is pushed as usual, a tab can watch and Stop any other). The
  chat of a Telegram turn carried on is answered with all the turn wrote, before the cut and
  after it, a canvas written before the cut among it, and is not told again what it was sent
  when the turn stopped to ask a person. What a delegated child spent reaches its parent as the
  delegation's result is written, so a child that had ended before the cut is charged once. Two
  guards cannot be turned off: a run is marked `resumed` before its turn takes a step, so a turn
  that brings the server down again is closed at the next start instead of being tried for ever,
  and a turn carried on stays under the conversation's cost cap. A turn is not carried on when
  its conversation waits on a decision, was deleted, has had a later turn or has spent its
  budget, when it is a Telegram turn and no bot is up, or when the server runs with
  `--no-schedule`. Stop, a failed turn and a bot restarted under a running server close the run
  as before. The web says "Tiếp tục sau khi server khởi động lại" under the progress bar of a
  run that was carried on (`resumed` on a run in `/api/activity/runs`). The tab that sent the
  message reads the rest too, with no reload: a stream the server closed before the turn's last word
  is not taken for the turn's end, and the tab asks the server about the turn at once and again when
  the activity stream is back. A server that has been told to stop answers that question as it does
  for a conversation with no turn to watch (204).
- Each tool says whether a call cut by a restart may be made again (`Tool.replay_safe`, off
  unless declared). The eighteen tools that only read declare it and are simply called again. A
  call to any other tool that may already have run is closed with a note saying it was cut and
  that nobody knows whether it ran, and the model decides after looking; nothing that writes,
  sends or pays is done twice unseen. A canvas write closed that way is remembered by later
  turns as cut off, to be looked up before it is written again, not as a write that saved
  nothing. A call that never ran (it still had to ask, was refused,
  or could not be run) is settled the way it always was.
- An agent may name an escalation route: one `provider:model` its turn moves to only when the
  turn is stuck (`escalation_route` in `agent.yaml`, or "Tuyến leo thang" under the routes in the
  agent editor). Off unless an agent's own file sets it, and never inherited. A turn moves when
  the loop guard is about to halt it for making the same call again and again, or when a model
  call failed on every one of the agent's routes before any text was shown; the rest of that
  turn runs on the escalation route and the next turn starts on the usual ones. A turn moves at
  most once: stuck there too, it halts or fails as it did before. Running out of steps or of
  budget never moves a turn. A route that is one of the agent's own, or whose provider has no
  key, is no way out: it is left unused at start with a warning in the log, and saving one from
  the editor is refused (422) with the reason. The move is a new event, `escalated`, with why it
  was made; the web says so above the message box, and the run's timeline gains an `escalation`
  step naming the route. The notice stays through the load that follows the turn's end.
- Agents can use the tools of remote MCP servers. A server is declared once under `mcp_servers` in
  `config.yaml` (its address, a description, headers, how far its tools are let in, which of them
  only read, a timeout) and an agent is handed it by name: `mcp:` in `agent.yaml`, or the "Máy chủ
  MCP" boxes in the agent editor, which apply at once. The client speaks streamable HTTP and is
  written on `httpx`; stdio servers are not run. A server's tools are named
  `mcp__<server>__<tool>` and follow `mcp:`, not the `tools` allow-list or the mode. A server's
  name is runs of letters and digits set apart by a single `-` or `_`, at most 32 characters, so
  no two servers' tools can come to one name. Every one of them asks before it runs and is never
  made again after a restart, until the owner lists it under `read_only`; a server saying its own
  tool only reads is shown and decides nothing. The file holds no key: a header takes its value
  from the environment as `${NAME}`, the variables are set from Connections, and saving one has
  the servers that are down tried at once. An address is used and shown as it is written: one that
  names a variable stops the start, since the server would be sent those very characters in place
  of a key. A server that answers 401 with no key of its own can be signed in to from Connections
  (OAuth 2.1 as a public client: discovery, dynamic registration, PKCE), which is how the hosted
  Notion server is reached. A sign-in starts only from a browser on the machine the crew runs on,
  goes only to public `https` addresses, and its tokens are kept beside the provider keys and
  shown by no API. A refresh token is said only to the authorization server that granted it, and a
  server that comes to name another is signed out instead; the code a person comes back with is
  traded only when it comes from the place that was asked (`iss`, RFC 9207); a sign-in begun and
  left changes nothing of the one in use; and only the authorization server saying the grant is
  spent or the client unknown ends a sign-in, so one that is merely down leaves it as it was. What
  a server may send is bounded: 4 MB an answer, a thousand tools, 128 characters a tool's name and
  50,000 characters of JSON its parameters. A tool past either of the last two is left out and
  named on the server's row; a server past the thousand is not connected and says so. `timeout`
  (60 seconds, 600 at most) is what one request gets and what connecting as a whole gets; a
  sign-in request gets 15 seconds and looking for where to sign in 30. A session the server has
  forgotten is opened again, and one that could not be is opened by the next call. A server that
  is down is a row that says why, never a crew that does not start: the crew waits ten seconds for
  its servers as it starts and keeps trying the rest behind, at growing intervals. A server is
  tried by one connect at a time: the round behind leaves out a server someone is connecting,
  and a connect asked for under another waits for it and then tries afresh. New routes:
  `GET /api/mcp`, `POST /api/mcp/{name}/reconnect`, `POST` and `DELETE /api/mcp/{name}/login`,
  `GET /api/mcp/oauth/callback`. Connections gains a card with each server's state, reason, tools
  and who uses it, and that last line follows an agent being saved, made or removed with no
  reload; the Tools matrix lists MCP tools with their server and marks an agent that has not been
  handed the server apart from every other reason.
- An agent finds the MCP tools it was not told of with `tool_search`. A server's tools are let
  in `deferred` unless the file says otherwise: the model is not told of them on every call, and
  an agent that holds any such tool is handed `tool_search` with them. It asks in a few words or
  by a tool's name; the tools it holds are ranked by BM25 over each one's name, description and
  parameters, and the answer names the best five (ten at most) on a line each. From the next
  model call on those are told to the model like any other tool, after the ones it already
  knew, so the part of a request a provider keeps from call to call stays as it was. What a
  conversation loaded is read back from its stored `tool_search` answers: it lasts the
  conversation, reaches no other, and is the same after a restart. A loaded tool still asks
  before it runs; the search asks nobody and calls no server. `GET /api/tools` marks its row
  `with_mcp`; the Tools matrix gives it a "đi kèm MCP" badge and a mark of its own for an agent
  with nothing to find, and the agent editor's allow-list leaves it out.
- An agent can call its read-only tools from a short script with `tool_script`. A turn that
  needs one tool twenty times, or three lines out of a long answer, used to pay for every call
  and every answer in context; now the model writes that work as a script, the script makes
  the calls, and only what it prints comes back. The script is a small part of Python
  (variables, `if`/`for`/`while`, functions, lists, dicts, sets, tuples, f-strings,
  comprehensions, `try`/`except`, `json`, a fixed list of functions): no imports, classes or
  attribute reads, no files and no network. It runs in a process of its own with an empty
  environment, under limits on calls (25), steps, memory, CPU seconds, time and output, and on
  macOS inside a sandbox that denies the network, every write and a second process. A script
  may call only what reads and asks nobody: the built-in tools that declare a call may be made
  again, and of a server's tools the ones the owner both listed under `read_only` and let in
  as `codemode`. Anything that writes or asks first ends the script with a line saying to
  call it directly, where the approval gate sees it; so a script never waits on a person and
  is simply run again after a restart. A script that does not run to its end, whatever ended
  it, answers with the line "Script không chạy xong." before what it had printed and why it
  ended; a stored answer keeps no word of whether the call failed, so that line is what
  keeps the call's card saying "lỗi" after a reload. The tool comes with such MCP tools and
  goes with them (an agent with no `read_only` + `codemode` tool has no `tool_script`),
  follows `mcp:` and not the `tools` allow-list, and each call a script made is charged like
  a call made directly and listed under the script's step on the run card (`calls` on a tool
  step in `/api/activity/runs` and on the `tool_result` event), folded until opened.

### Fixed

- The Tools matrix no longer goes on showing who held a tool when the manage screen was opened.
  It was read once, so after an agent was edited, made or removed, or an MCP server was signed
  out of or tried again, the grid kept the old holders until the page was reloaded. It is now
  read again each time it is opened, and while it is open when a server's tools change or a try
  of one ends, with tools or with none.
- Saving an agent's own routes from the agent editor no longer fails. The editor holds a route
  as a provider and a model apart and sent it so, while the server read only the
  `provider:model` line a person writes in `agent.yaml`, and answered 500. A route sent either
  way is now saved as that one line, and anything else is refused with a 422 that says what a
  route looks like.
- What a turn said of itself no longer goes when the conversation is read again right after it. That
  a turn ended in an error, stopped short (out of steps, of budget, or halted by the loop guard) or
  went on by a fallback route is told by a notice above the message box that only the tab holds. A
  message sent before the conversation had finished loading made the tab read the conversation again
  once the turn was over, and that load cleared the notice, leaving a message with no answer and no
  word of why. The notice now stays while the stored conversation ends where the thread on screen
  ends, and goes once a load brings anything after it. An error of a request the tab itself made, a
  load or a send that failed, is still cleared by the next load that answers.

## [0.11.1] — 2026-10-05

### Changed

- On Telegram a `FILE:` line that names a picture in the workspace (png, jpg, jpeg, webp) now
  sends it as a photo, the way a `MEDIA:` line does. It used to be refused as a format a chat
  does not take, so an agent that reached for the wrong prefix left the person with a line
  saying the file could not be sent. The list of documents a `FILE:` line may send is unchanged.

### Fixed

- The whole app no longer slides up and leaves a blank band under it. The labels a screen
  reader hears inside a message were positioned against the frame around the thread instead of
  the thread itself, so they stayed where the unscrolled thread put them, thousands of pixels
  below the window, and made the page itself scrollable. A wheel or trackpad that ran off the
  end of another column, a long canvas above all, then dragged the page. The thread now holds
  its own labels and the page has nothing to scroll.
- The same slide could start from two other columns, and no longer does: a long list of
  conversations with unread ones below the fold, whose dot carries such a label, and the manage
  screen, where an agent's editor with its prompt opened, or the canvas library, reached past
  the window. Each of those columns now holds its own labels as well.
- An agent asked over Telegram to write a canvas and send it now sends the canvas itself. The
  result of creating or importing one told every turn that the person saw the canvas beside the
  chat and named no way to send it, so the agent exported the canvas to its workspace and sent
  that file: a note arrived without its caption, and a page or a picture was refused for its
  suffix. A turn read over Telegram, or a job's, is now told that its reader does not see the
  canvas and given the `FILE: artifact:<id>` line that sends it.

## [0.11.0] — 2026-10-05

This release adds the canvas: a versioned document that a person and an agent edit together. An
agent writes one with its tools, the person edits it in a panel beside the web chat, and each is
told what the other changed. A canvas can be markdown, code, an HTML page, an SVG drawing, a
Mermaid diagram or a picture, moves to and from workspace files, and reaches Telegram chats and
scheduled jobs as an attached file with a list of what the turn wrote.

### Added

- Agents write canvases: versioned documents kept beside a conversation, in six kinds. Markdown,
  code, HTML pages, SVG drawings and Mermaid diagrams are written by an agent or a person; a
  picture (PNG, JPEG, GIF or WebP, told by its bytes and not by its name) comes in only when a
  workspace file is imported, and `artifact_read` says it cannot read one. One version holds at
  most 512 KB of markdown, code or Mermaid, 2 MB of SVG or picture and 4 MB of HTML, and a write
  past that is refused with the size and the cap. All versions of all canvases share 1 GiB, which
  a person may fill and where an agent is refused at nine tenths. Seven tools work on canvases:
  `artifact_create`, `artifact_list`, `artifact_read`, `artifact_edit`, `artifact_rewrite`,
  `artifact_import` and `artifact_export`. Only `artifact_export` asks for approval, since a
  canvas version stays restorable and a file written over does not. A web-chat, Telegram or job
  turn, or an agent delegated from one, may write; a turn from the inbound API lists, reads and
  exports, and its system prompt says so before the model tries. The master reaches every canvas;
  another agent reaches those linked to its conversation, shared down its delegation chain or made
  by itself, and one out of reach reads as missing. A canvas is read a page at a time within the
  output cap. An edit replaces one exact passage, quotes what it changed as a diff, reports the
  canvas's new length and, when it misses, quotes the closest passage. A rewrite needs the newest
  version read whole and is refused with a diff when someone saved since. A change spread over too
  many lines to show one by one is said to be so, and the agent is sent to read the canvas again.
  A page or a write over versions the agent has not seen names who wrote them: at most the six
  newest runs of one author, a restore as a run of its own naming the version it brought back. A
  version or line number sent as `Infinity` or `NaN` is refused with a sentence naming the
  argument, and a version number too large to exist reads as a version that is gone. A turn writes
  at most 30 versions of one canvas and creates at most 30 canvases, and later turns carry a note
  of where a write went instead of the document it sent. The tool descriptions send any document
  the person will keep editing to a canvas, however short, keep answers read once and questions in
  the chat, say how an edit adds text after a passage, and give the rules of a page: a Mermaid
  canvas is the diagram's syntax alone, with no code fence around it. An agent with a `tools:`
  allow-list gets only the canvas tools it lists.
- What a person changed in a canvas reaches the agent with their next message, without a tool
  call. The message is stored with a canvas note, built in the same transaction, naming each
  linked canvas that moved since the agent last saw or was told of it: a diff of the person's own
  edits for at most three canvases, the most recently changed first, or one line asking the agent
  to read again for another agent's versions, a restore or a very long change. Each diff and the
  whole note have a size cap, and canvases that do not fit are counted in a last line. The model
  reads the note right before the message in every call of the turn that message opened, and a
  fixed stub in later turns, so the system prompt and the cached prompt prefix do not change. A
  diff from the version seen whole that shows every change counts as seeing the new version;
  otherwise the agent reads again before a rewrite. A note that fails to build leaves the message
  stored without one. Forking a conversation copies each message's note and the canvases linked by
  the fork point, with nothing seen or read, and the run trajectory carries the note with its
  secrets redacted. A web-chat message also names the canvas open in the tab that sent it, so the
  note names what that device shows even when another device opened a different canvas since, and
  quotes the passage selected there. Opening a canvas shares it with the conversation, so the
  agents it delegates to reach it too. A selected passage, in the editor or in the page being
  read, can be asked about: a bar at the foot of the panel names the lines the selection lies on
  and offers a box for a question, which goes as one message with the passage as of the version
  just saved. In the page being read, a paragraph, a list item, a table row or a code block counts
  as the whole of its source lines; a passage longer than a message is cut at a line end, and a
  selection made with a touch screen's handles or select-all counts too. Asking is off while a
  turn runs, while the conversation waits for a decision and once the budget is spent, and the bar
  says which. A question the server refuses, or that cannot be saved or reached, stays in the box
  with the reason; on a phone, where the canvas covers the chat, the canvas is put away once the
  question went through, so the answer shows. A 422 for a message that carried a selected passage
  reads as a passage that no longer matches the canvas. In the thread, a message that carries a
  note shows a chip, closed until pressed: it shows the note as text with hidden characters
  written out as marks, and a button copies the note exactly as the agent read it.
- Typing in a canvas is saved, merged and kept. A save goes out 1.5 seconds after the last key, at
  once on Cmd/Ctrl+S, when the tab hides, when the canvas closes and before a message is sent from
  the chat, and names the version it was made on. A version saved elsewhere meanwhile merges with
  the typing when the two change different lines, and otherwise raises a conflict bar with a diff:
  keeping mine saves over it, and loading theirs can be undone. Typing not yet saved stays in a
  draft on the device, reopened with the canvas and dropped after 30 days or beyond the ten
  newest. A draft the device refuses first frees the drafts of other canvases, oldest first; when
  that makes no room the typing stays in the tab's memory, the panel says so, and the browser asks
  before the tab is closed. A failed save is tried again after 2 to 60 seconds. A read unanswered
  for 30 seconds counts as lost, and so does a save once 30 seconds and the time its size takes at
  50 KB a second have gone by; each save in a row that goes unanswered doubles the time for its
  size, up to eight times. The header says where the save stands, from saving and saved to waiting
  for a network, a slow network, the server not answering, too large (naming the kind's cap), the
  server full (naming the largest canvases) or deleted. The composer keeps a message's words
  read-only until the save has landed and the server has answered, then empties, or leaves the
  words in place when the message was refused. The wait for the save ends 5 seconds past the
  deadline the save was first given, with "Đang lưu canvas…" shown from 300 ms on; a message that
  goes before the save landed goes with the last saved version, and the chat says so. The history
  lists every version, newest first, with its author, age and size, compares one with the version
  before it or with the oldest, and restores one as the newest once the typing is saved. Opening
  another conversation saves the typing and closes the canvas; a save that fails after the switch
  is told in the chat until dismissed or saved after all, saying whether the typing is kept in the
  draft on the device or only in the tab. A canvas deleted elsewhere keeps its text to read and
  copy.
- The web chat opens canvases beside the conversation. A Canvas button leads the conversation
  header with the number of canvases linked to it and opens their list, newest first, each with
  its kind, version and last change; a button there makes an untitled canvas of the kind picked
  beside it (markdown unless changed) and opens its name to type over. A new HTML or SVG canvas
  starts as an empty page or drawing, and a Mermaid one as a flowchart of two boxes. From 1101 px
  wide the canvas takes a column, in a tab beside the activity, whose edge widens or narrows it by
  dragging or with the arrow keys; it is never narrower than 360 px and keeps its width for the
  next visit. Narrower, it covers the chat column, and Escape or "← Chat" closes it and gives
  focus back to the button. A canvas opens to edit when a person wrote its newest version and to
  read when an agent did, a picture always to read, and switches between the two without losing
  the typing. Reading shows markdown as the thread does, code as text, an HTML or Mermaid canvas
  as its page and an SVG or a picture as a picture; bidi and zero-width characters show as visible
  marks with a notice, while copy and download keep the text as it is. A canvas renames in place
  and downloads its newest version. The dock remembers which canvas it opened in each
  conversation, and entering a conversation on a wide screen opens again the canvas the server has
  open there, without taking focus from the composer. In the thread, a canvas write shows as a
  card for the canvas it touched: its title, what was done to which version, and a button that
  opens it. An import shows the same way, as "Đã nhập" or "Đã nhập lại"; an export, and a write
  that failed, was refused, was stopped or waits for approval, keep the plain tool card, and a
  card never shows arguments or content. A canvas the server no longer has says so and offers no
  button. A canvas the agent creates, or imports as a new one, during a turn the tab is showing
  opens beside the thread on a wide screen without taking the keyboard, unless the person is
  typing in a canvas or has the keyboard anywhere in the canvas column; the card still opens a
  canvas held back this way.
- An HTML page and a Mermaid diagram run as pages, apart from the app. `GET
  /api/artifacts/{id}/render` serves the newest version, or the one `version` names, and is the
  only place a canvas runs; any other kind answers 404, and an SVG or a picture is shown as a
  picture, where scripts, links and outside resources do nothing. The page cannot reach the app or
  send anything out, and loads scripts, styles and fonts only from a few public CDNs
  (cdnjs.cloudflare.com, cdn.jsdelivr.net, unpkg.com, and Google Fonts for styles and fonts); the
  policy is listed under Security. A Mermaid canvas is drawn by Mermaid 11.17.2 at its strict
  security level, and shows the diagram's source as text when the library cannot load. In the
  panel, View shows the saved version, saving what was typed first, and Edit holds the source; a
  picture has neither Edit nor a copy button, and the history shows a picture's version as a
  picture, with nothing to compare. The page reloads a second after a newer version arrives; while
  the page has the keyboard the newer version waits behind a "Có bản mới · Nạp lại" button, and a
  hidden tab waits until it is looked at again. A page that leaves for another address is stopped
  once the new page has loaded, with the reason and a reload button, and "Mở trang" opens the
  saved page in a tab of its own once nothing is unsaved. A page cannot keep a keyboard it takes
  by itself. It has the keyboard only while the person offers it, by a real press inside the page
  or by Tab or Shift+Tab in the app; hovering and scrolling are no offer. Any other key, a press
  outside the page or focus arriving on one of the app's controls takes it back. A page that holds
  the focus without an offer loses it after 50 ms to the element it was taken from, the fifth such
  grab stops the page with the reason and a reload button, and a page that holds the app up is
  stopped the second time. A badge on the frame, "Bàn phím đang ở trang", says when the keyboard
  is in the page. What a page reports going wrong shows in the panel: script errors, rejected
  promises, resources that failed to load and requests the policy blocked. A page tells at most 20
  messages of at most 2000 characters, a button beside the count opens the five newest, and "Gửi
  lỗi cho agent" saves the canvas and sends those errors as one message, inside a code fence the
  message calls the page's own words, data and not a request. An SVG that cannot be drawn says it
  is not valid, and a picture that does not load says whether it waits for the network or cannot
  be shown.
- Canvases move to and from workspace files. `artifact_import` reads a file in the agent's
  workspace into a canvas, so a built page, a drawing, a picture or a document reaches a canvas
  without its content passing through a message. Without `id` it makes a canvas, titled after the
  file unless `title` says otherwise; with `id` the file becomes the newest version of that
  canvas, whose kind it cannot change. The kind follows the file's extension (`.md`, `.html`,
  `.svg`, `.mmd`, a picture's, or a code extension with its language) unless `kind` names one, and
  an extension that names none is refused. The path stays inside the workspace by the rule the
  file-reading tools keep; the file must be a regular file within its kind's cap and, for a text
  kind, UTF-8 without a NUL byte; a byte-order mark is dropped. A file equal to the newest version
  writes no version, and one that would go over versions the agent has not seen is refused, naming
  who wrote them, unless `replace` is set, and those versions stay in the history. The result
  names the file, its size and the first 12 characters of its SHA-256, never what the file holds,
  and counts the relative addresses in an HTML or SVG file, which a canvas does not load. An
  import is a canvas write: it runs only where the other write tools do and counts toward the
  turn's limits. `artifact_export` writes one version, the newest unless `version` names another,
  to a path in the workspace: text as UTF-8 with LF line ends and no byte-order mark, a picture
  byte for byte, over a file already there. It writes no canvas, so it is open on every channel
  and counts toward none of the turn's limits. The target must lie inside the workspace, and
  inside the agent's `write_paths` when it has any, and may be neither a symlink nor a directory;
  the file is written whole or not at all, and a failed export leaves the old file as it was. A
  canvas keeps where it was imported from: the workspace file, or the link the import gave as
  `source_url`, an http or https address of at most 2000 characters. The panel names that source.
  A link shows as its host and opens in a new tab; a workspace source shows the agent and the path
  beside "Nhập lại", which saves the typing, reads the file again and says whether a new version
  was made or the file had not changed, and the history marks such a version "Nhập từ tệp". `POST
  /api/artifacts/{id}/reimport` does the same over REST, on the version the body names as
  `base_version`: a canvas with no workspace source answers 422, a source file or agent that is
  gone 410, a path outside the workspace 403, a file over the cap 413, a version saved since 409,
  and a file that cannot be read as the canvas's kind 422. Kit hooks hear of the two tools as the
  workspace tools they act as: a hook that names `Read` or `workspace_read` is asked about
  `artifact_import`, and one that names `Write` or `workspace_write` about `artifact_export`, with
  the real name in `tool_name`, `Read` or `Write` as `tool_alias` and the file path in
  `tool_input.path`.
- The manage screen has a Canvas section (`#/manage/canvas`): a library of every canvas, whatever
  conversation it was written in. It lists the 200 most recently changed, each with its kind,
  newest version, who made it, when it last changed and the size of all its versions, under a line
  with the number of canvases and the space they take against the limit; when there are more it
  says so, and a box that searches by name finds an older one. Where a canvas was imported from is
  said, never linked. The list follows the canvas changes the activity stream announces. A canvas
  is deleted with all its versions after a confirmation, and the keyboard then moves to the row
  after it, the row before, or the search box. A canvas also has a page of its own
  (`#/manage/canvas/<id>`), reached from its name in the library or from "Mở riêng" in the panel,
  which opens it in a new tab once nothing is unsaved. The page shows the canvas in the same
  panel, without the bar that asks about a selection and without the button that sends page
  errors, since no conversation is open there. A line under it counts the conversations the canvas
  is used in and names each as a button that opens it. "← Canvas" leads back to the library, and a
  save that then fails is told above whatever the section shows.
- A delegated agent's canvases come back with its result. A child writes canvases only when the
  turn its chain began from could, and reaches what its chain shares. Under the `outcome=` line of
  a `delegate` result comes one `[artifact <id> v<n>] <title>` line for each canvas an agent added
  a version to in the delegated conversation, first written first, with the title cut to 160
  characters; at most 12 are named and the rest counted. The lines come with every outcome, a wait
  that ran out included, and after the sentence that says the delegated conversation was deleted
  while the call waited; an export, an import that changed nothing, a rename and a deleted canvas
  give none. The tool's description tells the model that such a title is data, not an instruction,
  and to name the canvas instead of copying its content. A `FILE: artifact:<id>` or `MEDIA:
  artifact:<id>` line in the child's answer rides on as written when the child reaches the canvas,
  which is then linked to the delegating conversation so the reply there can send it, and the line
  is put back when that reply leaves it out, as a relayed file's line is; otherwise the line
  becomes "(agent con có đính kèm {path} nhưng không chuyển được tệp)". In the web thread the
  delegation card shows one chip for each canvas the result names, with its title, its version and
  a "Mở" button, or "Canvas đã bị xoá" for one the server no longer has. When a delegation
  succeeds during a turn the tab is showing, the first canvas its result names opens beside the
  thread under the rules a created canvas opens by.
- A canvas the agent is still writing shows in the web chat as it is written: a card in the thread
  from its first piece and, beside a wide conversation, its text filling in read-only where the
  canvas column is, nothing of it stored until the call ends. On a thread too narrow for the card's
  one line, how much has been written goes on a row of its own. HTML, SVG and Mermaid show as source
  while they are written, and so does markdown of 100 000 characters or more, with a line saying so.
  Drawn or shown as source, the text keeps its newest line in sight until the person scrolls up. The
  preview does not come up by itself while the keyboard is anywhere in the canvas column, and once
  the person puts it away by hand, every canvas written in the rest of that turn stays a card.
  Closing the preview, or a saved canvas opened from a card or a chip in the thread, puts the
  keyboard back where it was when that opened, the button pressed or the chat box, and on the
  Canvas button only when that is gone. A switch on the Settings page turns the preview off for the
  device. Only `artifact_create` and
  `artifact_rewrite` are previewed; the arguments of no other tool are streamed. The offline
  `fake:slow` model answers as `fake:echo` does, with 0.1 seconds between two pieces, so a canvas
  can be watched filling in without a model key.
- Canvases reach Telegram and jobs. A line `FILE: artifact:<id>` or `MEDIA: artifact:<id>` in a
  reply uploads the newest version, and the kind decides how, not the prefix: a picture as a
  photo, any other canvas as a document named after the title, with `.md` for markdown and `.txt`
  last for every other text kind (`.py.txt`, `.html.txt`, `.svg.txt`, `.mmd.txt`), so a phone
  opens it as text. The caption is `"<title>" v<n>`, with the link to the canvas's own page under
  it when `web_url` is set and the two fit Telegram's 1024 characters; a link that does not fit is
  left out whole. A picture Telegram refuses as a photo is sent once more as a document. Workspace
  files go first, then canvases, each once however often it is named. A reply sends only what the
  agent's canvas tools would let it read in that conversation; a canvas out of reach, one over 20
  MB, a failed upload and a miswritten id each get a one-line notice in the chat and do not stop
  the next attachment. A text canvas imported from a workspace file of a type a `FILE:` line would
  not send is not sent either. After a Telegram turn or a job's brief, a message headed "Canvas
  vừa ghi:" follows the reply with one line `• "<title>" v<n>` for each canvas the turn wrote,
  what a delegated agent wrote included, at the newest version written and only when the agent
  still reaches it. Under each comes the link to its page when `web_url` is set; without it the
  message ends "Mở web UI để xem.". At most ten are listed and the rest counted. A write that
  changed nothing, a read and an export name nothing, and a job that answers `OK` sends no list. A
  turn that wrote canvases and said nothing is answered by the list, a turn that broke or a run
  that stopped early still names what it wrote, and each reply of a turn that waited for approval
  names what was written on its own stretch. In the web chat the same attachment line shows as a
  chip that names the canvas and opens it with "Mở". `web_url` in `config.yaml`, or
  `MY_AGENT_WEB_URL`, which wins, is the address people open the web UI at, and the links read
  `<web_url>/#/manage/canvas/<id>`. It must be a plain http or https address with a host, an
  optional port and a plain path, with no user name, password, query or fragment; any other value
  stops the settings from loading, with an error that names the key and never the value. A final
  slash is dropped.
- Canvases over REST and on the streams. `GET/POST /api/artifacts` lists (newest first, by
  conversation or title) and creates the five text kinds, and `GET/PUT/PATCH/DELETE
  /api/artifacts/{id}` reads, saves, renames and deletes one. A save names the version it was made
  on, and a save on an older version is refused with 409 and the newest version's number, author
  and text. `GET …/versions[/{n}]` lists the history and reads one version, `POST …/restore`
  writes an old version back as the newest (a version number too large to exist is a version that
  is gone: 404 on a read or a restore, the conflict of a stale save on a save), `GET …/raw` serves
  a version as text, as a picture or as a download named after its title, and `GET
  /api/artifacts/usage` reports the number of canvases, the bytes their versions take, the ceiling
  they share and the bytes of each. `GET/PUT /api/conversations/{id}/canvas` reads and sets the
  canvas open in a conversation, with the passage selected in it; a selection the note would drop,
  or one cut through a character, is refused with 422 and changes nothing. Every write over REST
  is the person's: no body names an author or a conversation for it. A refusal from the store
  answers with its own status (404, 409, 413, 422, 507) and a structured body, never a 500, and
  text holding half of a surrogate pair is refused with 422 naming the part of the request that
  holds it. The activity stream announces every canvas change as an `artifact` event with the
  conversations linked to the canvas. The stream a web-chat message is answered with carries two
  new events, neither stored nor sent on the activity stream. `user_context` opens a turn with the
  note stored with the message, when it has one, so a tab that merely watches the conversation
  never receives a passage someone quoted. `tool_call_delta` carries a piece of the arguments of
  an `artifact_create` or `artifact_rewrite` call, with `index`, `name`, `chunk` and `attempt`:
  the first piece as soon as the call is named, later ones at most once every 3 seconds, and an
  event with an empty `name` calls off an attempt that was given up. The whole call still comes
  with `assistant_message`.
- Behaviour evals can work on a canvas between two messages, as the person would in the web panel
  and over the same routes: `create_canvas`, `edit_canvas` (replaces one exact passage and saves
  on the version it read) and `select_canvas` (the next message carries the selection's lines). A
  step that cannot be done fails the run before the next message. New expectations judge the
  canvases linked to the conversation when the run ends: `canvas_count`, `canvas_contains`,
  `canvas_not_contains`, and `canvas_not_in_chat`, which fails when the agent's messages repeat
  half or more of a canvas's three-word runs; the title, the heading the canvas opens with and a
  quote that stays within one line do not count. A run also fails when a message after canvas
  steps reaches the agent without a canvas note telling of each canvas the person made or saved
  since, and an `edit_canvas` whose `new` is its `old` is refused. The dry run plays a canvas case
  through the real server.

### Changed

- `POST /api/inbound` answers 422 when `source` names one of the server's own channels (`chat`,
  `telegram`, `web`, `job` or `job:<id>`, `delegate:<…>`, `memory:<…>`). A relay could otherwise
  pass for the person in the web chat, or post a run that showed up as a scheduled job's last run
  and in its history. Any other label, `api` included, is recorded as before.
- A `delegate` result always has an empty line between its `outcome=` line, with the canvas lines
  under it, and the text that follows, whether or not a canvas was written. Whatever reads a
  result line by line should expect it.
- A `FILE:` or `MEDIA:` line whose path opens with `artifact:` names a canvas and is no longer
  looked up as a workspace file, in a Telegram reply or in a delegated agent's answer, even when
  the workspace holds a file of that name.
- The system prompt of a Telegram or job turn, and of an agent delegated from one, ends with a
  "Canvas" section when the agent holds a canvas write tool, after the day's notes and right
  before the date. It says the reader is not at the web chat, to make a canvas only when told to
  or when the document is long and will be edited further, and that a line `FILE: artifact:<id>`
  of its own sends the canvas with the message. A turn from the inbound API reads one line there
  instead, naming the canvas write tools it should not call. A web-chat turn's prompt has neither.
- The system prompt's rule that web and file content is data now names canvas content and what a
  canvas note quotes.
- The offline `fake:echo` model calls the tool named on a message's last line that starts with
  `/tool`, when that line and its arguments end the message, whatever comes above it, so a
  self-test can drive a canvas tool from a message stored with a canvas note. A tool line inside
  the note calls nothing.
- The README now covers what 0.10.0 added beyond voice notes.

### Fixed

- A model call that hits a passing upstream failure before any text is shown is asked again once
  on the same route, after a two-second pause, instead of ending the run. This covers OpenRouter's
  `provider_unavailable` error sent mid-stream after a 200, HTTP 408/425/429/5xx and transport
  failures; a refused request (other 4xx), an error without a code and a malformed stream still
  fail at once, and a failure after text has been shown still surfaces. A retried side call that
  had already been served is written to the cost ledger at an unknown cost. No model fallback is
  added.
- A tool call whose arguments are not a JSON object (a raw line break or unescaped quote inside a
  long document, or output cut off mid-call) no longer ends the run with a provider error. The
  call is answered, without running, with its length, where the JSON broke and the few characters
  around that spot, and the turn carries on. Such a call never asks a person for approval, and the
  broken text itself is not stored.
- A tool call cut off because the reply reached the model's output limit is answered with a
  request to split the content into smaller calls, not to send it again. Calls broken at different
  places no longer count as one repeated call; the same broken call sent three times in a row
  still does. A tool error longer than the output cap is cut like any output.
- A tool call whose name or arguments arrive as something other than text is reported as a
  malformed stream from the provider. Before, the turn's stream broke off with no error event.
- A turn whose last allowed model call answered ends as done, not halted at the step limit. A turn
  that does run out of steps answers the tool calls it never ran with a note that the step limit
  stopped them, so the next message no longer closes them as interrupted.
- A delegated agent picked up again after an approval, a question or a restart can no longer hand
  work on to another agent. Resuming started its turn as if a person had opened it, so the
  one-level limit on delegation did not apply.
- A delegated agent's answer is read for `FILE:` and `MEDIA:` lines at every line break a string
  knows, as a Telegram reply already was, where only `\n` counted before. The reason an unfinished
  delegated run stopped for is quoted in the `delegate` result on one line, cut at 160 characters,
  so a provider's error can add no lines of its own to the result.
- A Telegram notice about an attachment that could not be sent no longer stops the attachments
  named after it when the notice itself cannot be sent; it is logged instead.
- Deleting a conversation is all or nothing. A delete that failed midway is rolled back, where the
  next unrelated write used to finish it and take the messages of a conversation reported as still
  there.
- An agent id that ends in a line break is refused. `coder` followed by a newline passed the check
  and named a directory.
- The web app ignores a stream event of a kind it does not know. A tab older than the server broke
  on the first such event; a tab still open from 0.10.0 has this fault until it is reloaded.
- An image from another site, which waits for a tap before it loads, asks again when its address
  changes. One agreed image used to let any later image in the same place load unasked.
- A message the server queued, because the conversation was busy somewhere the web tab could not
  see, no longer comes back to the composer while a chip stands for it. A message the server
  refused now gives its words back and takes its bubble back. A send cut off on purpose, by Stop
  or by leaving the conversation, counts as sent, not as failed.
- The conversation no longer stops following its newest line while a reply arrives. A reply that
  came in a burst, or a turn whose start removed the fork buttons above the view, could read as
  the reader scrolling up, and the answer sat below the screen. Only a move up lets go of the
  newest line now; a reader who has scrolled back keeps their place.
- A tool call that failed stays failed when the conversation is read back. The web drew every
  stored call that was not denied as done, with the error only inside the result. That holds now
  for every way a call fails: a tool that raised, a tool that does not exist, a hook's block,
  arguments that were not valid JSON or were cut off, the step limit, a repeated call, an approval
  given to another call, a branch away, a call cut short, and a handed-off task whose wait ran
  out.
- A link whose address holds an escape that cannot be read, `#/manage/crew/%` for one, no longer
  opens the web app on a blank screen. The part that cannot be read is taken as not there, and the
  section opens on its list.
- Each behaviour eval run starts from the server as the first run found it. The runs share one
  server, so a later run was judged on the conversations, canvases and notes an earlier one left.
  Before every run the runner deletes every canvas and conversation, checks none is left and puts
  the memory files back, never outside the run dir and without following a link; when it cannot,
  the eval stops. What a deleted conversation's turns cost still counts toward the budget. Each
  run also leaves a JSON transcript of its conversation, child conversations, canvases and
  approvals in `results/transcripts/`; it can hold what the agents know, so delete it by hand.
- An eval expectation pinned to a turn counts turns by the messages the case sent. A note the
  server stores as the person's message, the loop guard's above all, started a turn of its own, so
  a tool called after it was judged as the next turn's. A conversation that does not hold every
  message the case sent now fails the run.

### Security

- A file in an agent's workspace no longer opens as a page of the app. `GET
  /api/agents/{id}/files` served each file with the type its extension suggested, so an HTML or
  SVG file an agent wrote, opened from its link, ran its scripts with the app's origin and could
  call every API route. Now only raster images, PDF and plain text open in place, and any other
  file downloads as `application/octet-stream`. Every response but a PDF's is sandboxed with no
  scripts, and every one carries `X-Content-Type-Options: nosniff` and
  `Cross-Origin-Resource-Policy: same-origin`. The types are pinned in code, not read from the
  machine's MIME table.
- A browser request to the API that says it comes from elsewhere is refused. The local guard
  judged a browser request by its `Origin` header alone; it now also reads `Sec-Fetch-Site` and
  answers 403 to a request under `/api/` whose value is anything but `same-origin` or `none`. A
  request without the header, as `curl` or another program that is no browser sends, passes as
  before, and a canvas's render page is the one address such a request still reaches.
- The web app can no longer be shown in a frame on another site. Every response, an unhandled
  error's included, carries `Content-Security-Policy: frame-ancestors 'self'`.
- A canvas page runs under a policy of its own. The render route answers with `sandbox
  allow-scripts` and never `allow-same-origin`, so the page has an origin that is not the app's.
  Scripts, styles and fonts come inline or from the three CDNs (styles and fonts also from Google
  Fonts), images and media only from `data:` and `blob:` addresses, and the policy allows no
  `fetch`, `XMLHttpRequest` or WebSocket, no form target and no `<base>`. The response may be
  framed by the app alone and is sent with `nosniff`, no referrer, DNS prefetching off and
  `no-store`. Mermaid is loaded under an integrity hash. The raw route serves a version with no
  scripts, and an HTML page, an SVG drawing and HTML code download as `.html.txt` or `.svg.txt`,
  so opening the file shows the code.
- What the runtime itself says in a Telegram chat goes out as it stands and is no longer read for
  `FILE:` and `MEDIA:` lines: the answer to a slash command, `/status` with the conversation's
  title among them, that an approval ran out, why a run was cut short or did not finish, that a
  reply was empty, and the error a turn broke with. A line of such a sentence shaped like an
  attachment line used to send the file it named. What the agent said before a turn broke is still
  read for the files it names.
- A canvas sent to Telegram passes the secret filter the run trajectory uses: secrets the server
  knows are covered in the text, the caption, the file name and the titles in the list of written
  canvases. A picture's bytes go as they are.
- A source link with a user name or a password in it is refused by `artifact_import`, since it
  would be stored and shown to everyone the canvas is. In the panel only a plain http or https
  address on another origin than the app's becomes a link.
- The export log names where a write was going with the place quoted and any line break in it
  escaped, so a folder's name cannot start a log line of its own.
- The bench and eval servers get only what a program needs to run from the caller's environment
  (`PATH`, `HOME`, the locale, `TERM`, `TMPDIR`, `USER`, `LOGNAME`, `SHELL`, `TZ`) and
  `OPENROUTER_API_KEY`. Before, they got the rest of the operator's shell but for a short list of
  dropped names, and so did every hook they ran.

### Upgrade notes

- The database gains four tables (`artifacts`, `artifact_versions`, `conversation_artifacts`,
  `canvas_focus`) and three columns (`messages.context`, `conversations.root_id`,
  `conversations.root_source`), all added on start and empty for existing rows. Nothing is
  rewritten or removed, but back up `agent.sqlite3` before the first start.
- Agents with their own `tools:` list in `agent.yaml` get no canvas tool until its name is added
  to that list; agents without a list get all seven on start.
- `web_url` (`MY_AGENT_WEB_URL`) is empty by default, and without it Telegram messages carry no
  link to a canvas. A host that is neither `localhost` nor an IP address must also be listed in
  `MY_AGENT_ALLOWED_HOSTS`, or the server refuses the request the link leads to.
- Reload browser tabs left open from 0.10.0. The old page breaks on the stream events this version
  adds, and the update bar only offers the reload.
- The system prompt of a Telegram or job turn gains a "Canvas" section for an agent that holds a
  canvas write tool, and a turn from the inbound API gains one line telling it not to call them. A
  web-chat turn's prompt is unchanged.
- A `FILE:` or `MEDIA:` line whose path opens with `artifact:` is no longer a workspace file.
  Rename a workspace file or folder of that name.
- A `delegate` result always has an empty line before the answer. Anything that reads the result
  line by line should expect it.
- `POST /api/inbound` answers 422 for a `source` of `chat`, `telegram`, `web`, `job`, `job:<id>`,
  `delegate:<…>` or `memory:<…>`. A caller that sent one of these needs another label.
- A workspace file that is not a raster image, a PDF or plain text now downloads from its link
  instead of opening in the browser. This includes HTML and SVG files.
- A browser request to `/api/` from another origin, another local port included, gets 403. A
  browser tool served from elsewhere that called the API no longer can; programs that are no
  browser are not affected.
- The eval and bench servers no longer inherit the caller's `MY_AGENT_*` variables or any key but
  `OPENROUTER_API_KEY`. A hook or a case that relied on another variable will not find it.
- A delegated conversation opened before the upgrade has no record of the channel its chain began
  from, so an agent resumed in it cannot write canvases. A new delegation can.
- `write_paths` now also holds `artifact_export`: an agent with the key exports only inside the
  paths it lists.

## [0.10.0] — 2026-09-30

The crew now works more like people who share a desk. A message sent while an agent is busy
waits its turn, and one that starts with a slash command steers the turn already running;
Telegram turns run in the background so the bot keeps answering, and a voice note is
transcribed, with the transcript echoed back, before the master sees it. What was said stays
findable: an agent searches its own past conversations and the master the whole crew's, and a
conversation can be forked at an earlier message to try it another way. Memory keeps itself
current: each line carries the day it was last confirmed, and a rewrite that drops or rewords
a line waits for a person. An agent can propose its own repeating job, which runs only after a
person approves the verbatim prompt, and a tool output cut short stays readable in full
through `tool_output_read`. Every model call, including the side calls for titles, summaries
and memory, now lands in the cost ledger, and a run's trajectory downloads as JSON or Markdown.

### Added

- A tool result that was shortened for being over the output cap can now be read back in full.
  The original is kept under `spill/<conversation>/` in the home, the shortened text ends with
  a line naming the call id, and the new `tool_output_read` tool (`id`, `offset`, `limit`)
  returns it in segments that always fit the cap. It reads only the conversation it is called
  from and refuses an id that more than one result shares. Once old tool results are stubbed
  out of the prompt, the stub names the id to read them back with. Only agents whose tool list
  includes `tool_output_read` (every agent without an allow-list, and the kongming and
  researcher templates) get the spill and the pointer; an agent with a narrowed list is
  unchanged. Spill files go away with their conversation, a fork gets its own copy, and a daily
  sweep removes anything older than seven days.
- Every line in `MEMORY.md` can now carry the day it was last confirmed. On the next
  consolidation, an undated line or one older than ninety days goes back to the model for an
  explicit keep, fix or drop with a reason, and a newer note wins over an older line it
  contradicts. The reasons show on the proposal card before anyone decides. A master's
  consolidation also reviews the shared user facts and may propose forgetting or updating one
  that new notes contradict or nobody has confirmed in a while; those proposals always wait for
  a person, since every agent reads the facts. The facts list on the memory screen flags a fact
  nobody has confirmed in over ninety days.
- A button under a saved user message forks the conversation there: the server copies every
  message before it into a new conversation, closes any tool call still open at the cut without
  running it, and resets cost, approvals and autonomy to the agent's own defaults. The composer
  opens on the fork prefilled with the cut message's own text; the source conversation, its spend
  and its approvals are untouched. The header names where a fork came from and links back to it.
- A voice note (or audio file) sent on Telegram is transcribed by its own `audio_routes` chain
  before the master ever sees it. The channel replies "Đã nghe: …" with the transcript so the
  sender can catch a mishearing, then hands that text to the master as an ordinary message —
  never as a slash command or a `/steer`, whatever it starts with. A note over 300 seconds, over
  10 MB, or in a format none of `mp3/m4a/ogg/wav/flac/aac` covers is refused before download.
  Transcription cost is recorded under a new `transcribe` purpose in the cost ledger, and the
  connections page lists the configured audio route the same way it already lists vision routes.
- The costs page splits the whole ledger by what each call was for: the turns' own calls, and
  the ones made beside them — a conversation's title, a session recap, a long tool output
  summarised, a picture or a scanned PDF page read, memory consolidation, the wiki compile.
- A tool that asked a model itself shows the price on its row of the run timeline.
- A turn that keeps making the same tool calls is stopped before it burns its step limit. At
  the third identical call in a row the agent is told it is repeating itself, naming the tool
  and nothing a tool returned; three more identical calls halt the turn with the reason "loop",
  and the call that would have been the sixth is answered with a refusal instead of running.
  Repeats with a change in between ("run the tests, fix, run them again") are left alone.
- `scripts/run_evals.py` plays written cases against your own agents and the real model. A case
  is a short conversation with one agent plus what must, and must not, happen in it: the tools
  it calls, what it asks approval for, what it says, whom it delegates to and what it costs.
  Every case is played several times and passes when two runs in three do. It runs on a copy of
  your home in a throwaway folder, so nothing touches the live crew: the copy has no schedule,
  no Telegram bot, no secrets file, no shell allow list and no login files, and a command that
  names a path of the live home or a workspace is refused even when the case approves. Money
  spent is read from the usage ledger and capped by `--max-usd`. `--dry-run` swaps in the fake
  model to check the plumbing. Cases live in `<home>/evals/`; see docs/testing.md.
- `--no-schedule` starts the server with no scheduler and no channels.
- A delegation's result says what the handed-off task came to, on its second line, not only how
  the child's run ended: `outcome=done`, `done_with_concerns`, `blocked`, `needs_context` or
  `failed`, with a reason when it is not done. The runtime's facts come first: a run that
  errored, halted or outlasted the wait failed, and a child whose last tool approval was refused
  or lapsed is blocked; a question answered after that does not lift it. Otherwise the child's
  closing `Status:` line decides, however a model writes it (a bold key, a heading, a value with
  spaces or hyphens, in backticks), and a child that declared nothing is done, as before. A
  `Status:` line inside a code block is something the child is showing, such as a task list or
  a ticket, and counts only when there is none outside one. The tool tells the agent that
  delegated to say plainly when a task is not done, and why.
- The delegation card on the web names the outcome in words, marks one that is not done, and
  shows the reason beside it, in words too: how the child's run stopped, a wait that ran out, a
  tool approval refused or lapsed.
- An eval case can require what a delegation came to: `delegates_to: {agent, outcome}`.
- A schedule, or the master's `telegram:` block, may say how long an approval in the
  conversation it opens waits for a person: `approval_ttl_seconds`, whole seconds from 60 to
  43200. A job that asks at night can wait for the morning instead of expiring in ten minutes.
  The conversation keeps its wait for every later approval, after a restart too, a delegated
  child copies its parent's, and the parent waits on the child that long plus five minutes.
  Without the key the global `approval_ttl_seconds` applies as before. The web editor keeps the
  key through edits of other rows and of the chat id, but has no box for it.
- A run downloads from its own page as JSON or Markdown
  (`GET /api/activity/runs/{id}/trajectory?format=json|md`): its record, the messages of that
  run alone, every tool call with its arguments and result, and the transcript of each child it
  delegated to. A new run notes where its conversation stood when it began, so its messages stop
  where the next run's begin; a run recorded before that is sliced by its start and finish time
  and says so. Secrets are covered on a best-effort basis: the values of the server's
  environment variables named like a key, token, secret, password or credential, and common key
  shapes (`sk-…`, `Bearer …`, JWT). An environment value is also covered where the run's record
  holds only part of it: a title or preview cut partway through it, a summary kept from partway
  through it, a copy escaped inside JSON, or an argument's name. A secret from anywhere else is
  not, so the file and the page both say to read it before sharing. A tool result is cut at
  2,000 characters unless `full=1` is asked for. In the Markdown, a title stays on one line and
  a code block a message left open is closed before the next message begins.
- A message sent while its conversation is busy waits its turn instead of starting a second
  turn beside the running one. A plain message waits in the conversation's line; once the
  running turn is over, everything that waited is answered by a turn of its own, as one message
  in the order it was sent. A message that starts with `/steer <text>`, or with a command from
  the agent's kit, goes into the running turn instead: the agent reads it once the tool it is
  running returns, before its next model call, the run shows it as a step, and the same turn
  answers it. One that arrives after the turn's last look waits in line like any other message.
  With nothing running, `/steer X` is simply the message X, and a bare `/steer` is refused (422)
  either way. A line holds 20 messages; the 21st is refused (429) with the reason. The line lives in
  the database, so what waits is answered after a restart too (a server started with `--no-schedule`
  starts nothing on its own and leaves it for the conversation's next turn), and it goes with its
  conversation when that is deleted. A conversation waiting on a person's decision still refuses new
  messages (409).
- `GET /api/conversations/{id}` lists what waits under `queued`, and
  `POST /api/conversations/{id}/stop` hands it back as `cleared`, empties the line and stops the
  turn the line started, if one runs (`cancelled`). A turn a browser tab is reading, one the
  Telegram bot runs for a message it just got, or a job's, is not the line's to stop.
- The composer no longer locks while its conversation is busy: typing and Enter still send, only
  where the message goes changes. A plain message becomes a chip reading "Đã xếp hàng, chạy sau
  lượt này" and is sent by a POST of its own, never touching the running turn's stream or its
  `AbortController`; a `/steer` message or a kit command becomes a chip reading "Sẽ chèn vào lượt
  đang chạy", and once the server folds it in, the chip turns into a user message in place and the
  run draws an empty dot on its timeline for the step, so a person's steer reads apart from the
  agent's own work. Stop is the only way to take a message back: it calls the server first, within
  three seconds, so the line has a chance to be cleared in order before the tab aborts its own
  turn, then returns every cleared chip's text to the composer in the order it was sent. Stopping
  with nothing left to clear says nothing; clearing chips from a turn the server could not cancel
  (Telegram, a job, another tab) says so instead of clearing them silently. A conversation's chips
  survive a reload: they come from `queued` on the conversation's own record, not from anything
  kept only in the tab.
- A run first seen already running while its tab still shows a queued chip is reloaded right away,
  instead of waiting for a status change that a turn finishing between polls, or one halted on its
  own budget, may never produce — the chip could otherwise outlive the turn it was queued behind.
- A message sent to `POST /api/inbound` while its conversation is busy is answered at once with
  `status` `queued`, `queued: true`, no steps and a notice as its text; the answer itself is read
  back from the conversation. Every reply carries `queued`.
- The Telegram bot reads the chat while a turn runs: the turn runs in the background, `/status`
  answers mid-turn with how many messages wait, a plain message waits in the conversation's line
  and is answered by a turn of its own, and `/steer <text>` (or a kit command) is steered into
  the running turn. The chat stays in its conversation until the turn and its line are done, even
  past midnight, and `/new` waits for them. A stop waits for every running turn before cutting it
  off, and a "typing…" indicator Telegram does not answer no longer holds the turn.
- A new `conversation_search` tool finds what was said in an older conversation, across a full
  FTS5 index of every message body. An agent searches its own conversations; the master can name
  another agent or search the whole crew. Typing without accents still reaches an accented word
  (`đ`/`Đ` are folded to `d`/`D` before indexing, on top of SQLite's own accent-insensitive
  tokenizer), results are capped at three per conversation so one long thread cannot crowd out
  everything else, and the conversation a call runs from is left out of its own search. The
  sidebar's own search box, once it is showing, now searches message content the same way and
  lists "Trong nội dung" hits below the title matches, each naming the agent it came from and
  opening straight into that conversation on a click, over a new `GET /api/messages/search`.
- A new `schedule_create` tool lets an agent propose a recurring job itself instead of waiting
  for `agent.yaml` to be hand-edited: a name, a prompt, exactly one of `cron` or `every`, and an
  optional list of skills. It always stops for a person, even in an `autonomous` conversation,
  even when the tool sits in `auto_approve`, even when it sits in the agent's own allow list —
  no setting in `agent.yaml` or `config.yaml` can wave this one through, because approving it
  means handing the agent an unattended future turn. The approval card spells the schedule out in
  words the same way the jobs tab already does ("Mỗi ngày 07:00"), lists the next three times it
  would run (approximate for an interval, which counts from the approval), and shows the
  verbatim prompt that will run every time after that. A proposal outside the limits — under
  15 minutes apart, an interval over a year, no run within the next year, a cron over 100
  characters, an empty name or prompt, one over the length cap, an unknown skill, an agent that
  already has 20 such schedules — still produces an honest card whose reason is the error
  itself; the cap is checked once more when the approved call runs, since another approval can
  land in between. Once approved, the schedule runs
  without a server restart and survives the next one; the jobs tab labels it "tạo từ chat" beside
  the ones written by hand and offers a delete button only for this kind, since a hand-written
  one needs its file edited instead. It has no edit button either: the agent editor holds only
  the schedules from `agent.yaml`, so changing one means deleting it and proposing it again.

### Changed

- The web approval card no longer offers "Luôn cho phép" on a request that stopped for a
  reason — a shell command matching the ask list, or a proposed schedule. Always-allowing the
  tool from there never waived that pause; it only quietly let the same tool's other calls run
  unasked, which is not what a card about one flagged call suggests. Other cards keep the
  button.
- Whether a memory rewrite applies on its own is decided by code from the old and new text, not
  by the model, and this changes what an `autonomous` agent does: a rewrite that only adds lines
  or updates dates still applies at once, but one that drops or rewords a line, or brings a
  date found in neither the old memory nor the notes it read, now waits for a person. A new
  rewrite proposal replaces any older one still pending for the same agent.
- A halted run says why in words on Telegram and in the reply of an API turn (the cost cap, the
  step limit, the same call over and over) instead of the loop's code, as the web already did.
- Only a task that came to `done` is handed straight to the person. A child that needs more
  context, finished with concerns or was blocked goes back to the agent that delegated, which
  reports it. The check reads the child's closing `Status:` line instead of looking for the word
  BLOCKED anywhere in its answer, so that word in the prose of a finished task no longer holds
  the answer back.
- An approval nobody answered tells the model that the action did not run and nothing changed,
  and not to redo it or reach the same end with another tool, but to tell the person what is
  waiting so they can ask again.

### Fixed

- Approving a memory rewrite after `MEMORY.md` changed since it was proposed is refused (409) and
  the proposal is marked superseded, instead of overwriting what was written in between; a
  rewrite applied on its own checks the same way. A superseded proposal shows in the history
  with no undo, since none of it was ever applied.
- `fetch_url` no longer returns an empty result. A server that answers 202 (accepted, nothing to
  read yet) is reported as not ready, and a page with no readable text (an empty body, or one
  drawn only by JavaScript) is reported as such instead of reading as a page that says nothing.
  A blank scrape from firecrawl falls back to fetching the page itself, as an empty one did.
- A delegation that outlasts its wait still names the child's conversation, so its card can
  open it, and reads as failed.
- The fake model gives every tool call an id of its own, as a real provider does. Two
  conversations that delegated at the same point used to share an id, and the second was handed
  the first one's child.
- Model calls made beside a turn now reach the usage ledger. Titles, recaps, tool-output
  summaries, picture and scanned-page reads, consolidation and the wiki compile were billed by
  the provider but missing from the day and model totals. Each is now written down with its
  purpose, provider, model, tokens and price, never its prompt; a call abandoned mid-answer is
  written down at an unknown price instead of being lost.
- A run's total includes what its tools paid a model (a picture, a scanned page, a summary), so
  the run, its conversation and the ledger agree.
- A tool-output summary whose provider gave no price counts as a call of unknown cost instead of
  a free one, and a session recap that came back empty is still charged to its conversation.
- Grouping the ledger by model keeps one model name served by two providers as two rows.
- Runs that began in the same second keep the order they were created in. A run is saved again
  at every step, and each save used to move it ahead of the others in the activity list.
- Two turns no longer run at once in one conversation. A message sent while a turn was running
  started a second turn beside it, both writing into the same history.
- A decision holds its conversation from the moment it is taken. A message sent right after it
  waits for the turn the decision resumes instead of being refused or running beside it; a
  second decision on the same request, sent before that turn began, is refused (409) instead of
  racing the first; and the sweep that expires unanswered approvals leaves it alone.
- A tool call a turn left without a result — the turn was stopped, or the server went down
  mid-call — no longer runs again when the next message arrives, with its result landing after
  that message. It is closed before the message: with the decision taken on it when there was
  one, otherwise with a note that it was interrupted and may or may not have run, so the model
  checks before trying again. A call still waiting on a person is left open.
- Finding a cron schedule's next run no longer walks the calendar minute by minute: it jumps to
  the next day, hour or minute that can match instead, so a yearly schedule whose next run is
  months away resolves in a handful of steps rather than several hundred thousand.
- A tool call id that a provider left out is now a unique generated id instead of one derived
  from its position, so two such calls in one conversation no longer share an id.
- A reused call id whose stored approval names a different call is refused instead of being
  run under that approval.
- A delegated child conversation is found only through its own parent's call, so a call id
  from another conversation can no longer open it.

### Upgrade notes

- The database gains a `side_calls` table, created on start. Calls from before the upgrade
  stay as they were: the ledger is complete from this version on.
- The database gains a `queued_messages` table, created on start.
- The database gains a `messages_fts` full-text index over message bodies, built and filled on
  the first start; with a long history that start takes longer, once. A Python whose SQLite has
  no FTS5 module stops at startup with a message saying so.
- The `conversations.forked_from` and `memory_proposals.reasons` columns are added on start,
  empty for existing rows.
- The database gains a `created_schedules` table, created on start, holding the schedules an
  agent proposed through `schedule_create` and a person approved.
- The `conversations.approval_ttl_seconds` and `runs.after_seq` columns are added on start,
  empty for existing rows. A conversation without its own wait uses the global
  `approval_ttl_seconds` as before; a run from before the upgrade exports its trajectory by its
  start and finish time instead of by message sequence.
- Agents with their own `tools:` list in `agent.yaml` do not get `conversation_search`,
  `schedule_create` or `tool_output_read` until those names are added to that list; agents
  without a list get all three on start.
- Voice notes are transcribed through `audio_routes`, which defaults to
  `openrouter:google/gemini-2.5-flash-lite`: the key that already enables image reading enables
  this too. Set it empty to turn transcription off.
- A tool output too long for its cap is kept whole under `spill/` in the home, at most 5 MB a
  file. The server sweeps files older than seven days on start and once a day, and deletes a
  conversation's folder with the conversation.

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

[0.20.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.20.0
[0.19.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.19.0
[0.18.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.18.0
[0.17.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.17.0
[0.16.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.16.0
[0.15.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.15.0
[0.14.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.14.0
[0.13.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.13.0
[0.12.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.12.0
[0.11.1]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.11.1
[0.11.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.11.0
[0.10.0]: https://github.com/phuc-nt/my-agent-crew/releases/tag/v0.10.0
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
