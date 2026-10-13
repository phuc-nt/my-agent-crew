// The window a person signs in through on an agent's browser, and the hosts that browser may
// still be signed in to, as both fakes answer them.
//
// It mirrors `server/routes_browser_login.py`, `browser/login.py` and `browser/logins.py`: an
// agent has one window at most, and asking for it again answers the one that is open without
// keeping it open longer; none opens for an agent with no browser, on a server with no screen
// to show it on, behind a locked screen, or under a call that is using the browser, and each
// is refused in the server's own sentence; an address no browser of the crew goes to is
// refused before anything else is looked at; a window closes when a person says they are
// done and by itself after a while; and of what a profile holds only host names and one
// moment each are told, the agent's own hosts in the order of its file, or, for an agent with
// none, the hosts that hold something, by name.
import type { BrowserLogin, BrowserSignedIn } from "../api/types";

/** `texts_browser_login`, word for word. */
export const LOGIN_OFF =
  "Agent này không có trình duyệt: chưa bật cho agent, hoặc máy chưa bật hay chưa cài trình duyệt. Không có hồ sơ nào để đăng nhập.";
export const LOGIN_NO_CONSOLE = "Máy chủ của đội không chạy trong phiên màn hình nào đang mở, nên không có chỗ để hiện cửa sổ.";
export const LOGIN_LOCKED = "Màn hình của máy đang khoá. Mở khoá rồi bấm lại.";
export const LOGIN_BUSY = "Agent đang dùng trình duyệt cho một lần gọi. Chờ lần gọi đó xong rồi bấm lại, hoặc dừng trình duyệt trước.";
/** `texts_browser.URL_SCHEME`, word for word: the one refusal of an address the fake makes by
 *  itself. A private address or a name that does not resolve is a test's to refuse. */
export const URL_SCHEME =
  "Trình duyệt chỉ mở địa chỉ http và https đầy đủ, ví dụ https://shop.example/don-hang. Tên máy chủ phải viết thẳng: không có tên đăng nhập đứng trước (user@…), không có dấu \\, ký tự mã hoá % hay khoảng trắng.";

/** How long a window stays open when nobody says they are done. */
export const OPEN_SECONDS = 15 * 60;
/** An agent with no hosts of its own is told of this many at most. */
export const TOLD = 50;

type Reply = { status: number; body: unknown };

/** What the windows are told of the agent a request is about. */
export interface LoginAgent {
  id: string;
  /** The `browser_hosts` of its file. */
  hosts: string[];
  /** Its file asks for a browser, on a machine that has one to start. */
  reads: boolean;
  /** Its browser is up, and a call is using it. */
  up: boolean;
  busy: boolean;
}

/** A moment as the server writes one: UTC, to the second, with its offset spelled out. */
export const moment = (when: Date) => when.toISOString().replace(/\.\d{3}Z$/, "+00:00");

/** Whether a cookie for `host` is one a page of the agent's own host would be sent, or one a
 *  page under it set. */
function covers(pattern: string, host: string): boolean {
  const base = pattern.replace(/^\*\./, "");
  return host === base || host.endsWith(`.${base}`) || base.endsWith(`.${host}`);
}

export class FakeBrowserLogin {
  /** Answer as the server did before it had the window: neither key in what is read, neither
   *  route, and neither of the tools that came with them. */
  old = false;
  /** The screen the server would show a window on: one that is on, a locked one, or none. */
  screen: "open" | "locked" | "none" = "open";
  /** The server's clock, for a test that turns it. */
  now: () => Date = () => new Date();
  /** The moment each open window closes by itself, by agent. */
  private windows = new Map<string, Date>();
  /** What each profile holds: when the last cookie that counts runs out, by host. */
  private held = new Map<string, Record<string, Date>>();

  /** The agent's profile holds these: each host with the moment its last cookie runs out. */
  signedIn(agentId: string, hosts: Record<string, Date>): this {
    this.held.set(agentId, { ...hosts });
    return this;
  }

  /** A browser on the agent's profile went down: from now on there is something written of
   *  what it held, were it nothing. */
  closed(agentId: string): void {
    if (!this.held.has(agentId)) this.held.set(agentId, {});
  }

  /** When the agent's window closes by itself; nothing when none is open. One whose time has
   *  passed closed with nobody saying they were done. */
  window(agentId: string): Date | undefined {
    const until = this.windows.get(agentId);
    if (until === undefined || until > this.now()) return until;
    this.windows.delete(agentId);
    this.closed(agentId);
    return undefined;
  }

  /** Closes the agent's window, whoever asks. Whether there was one to close. */
  close(agentId: string): boolean {
    if (this.window(agentId) === undefined) return false;
    this.windows.delete(agentId);
    this.closed(agentId);
    return true;
  }

  /** The two keys of what is read of an agent's browser; neither from a server older than them. */
  told(agent: LoginAgent): { login?: BrowserLogin; logins?: BrowserSignedIn[] | null } {
    if (this.old) return {};
    return { login: this.login(agent), logins: this.logins(agent) };
  }

  /** Opens the agent's window, stopping its own browser first, or says why none opens. */
  open(agent: LoginAgent, body: unknown, stop: () => void): Reply {
    if (!agent.reads) return { status: 409, body: { detail: LOGIN_OFF } };
    const url = (body as { url?: unknown } | null | undefined)?.url ?? "";
    if (typeof url !== "string") return { status: 422, body: { detail: [{ type: "string_type", loc: ["body", "url"] }] } };
    if (url.trim() && !/^https?:\/\/[^/\s@\\%]+(\/\S*)?$/.test(url.trim())) return { status: 422, body: { detail: URL_SCHEME } };
    let until = this.window(agent.id);
    if (until === undefined) {
      const why = this.whyNot(agent);
      if (why) return { status: 409, body: { detail: { no_console: LOGIN_NO_CONSOLE, locked: LOGIN_LOCKED, busy: LOGIN_BUSY }[why] } };
      stop();
      until = new Date(this.now().getTime() + OPEN_SECONDS * 1000);
      this.windows.set(agent.id, until);
    }
    return { status: 200, body: { open: true, until: moment(until) } };
  }

  /** A person says they are done. Whether there was a window for this request to close. */
  done(agent: LoginAgent): Reply {
    return { status: 200, body: { closed: agent.reads && this.close(agent.id) } };
  }

  private whyNot(agent: LoginAgent): "no_console" | "locked" | "busy" | "" {
    if (this.screen !== "open") return this.screen === "none" ? "no_console" : "locked";
    return agent.busy ? "busy" : "";
  }

  private login(agent: LoginAgent): BrowserLogin {
    if (!agent.reads) return { open: false, until: null, available: false, why: "off" };
    const until = this.window(agent.id);
    if (until !== undefined) return { open: true, until: moment(until), available: false, why: "" };
    const why = this.whyNot(agent);
    return { open: false, until: null, available: !why, why };
  }

  private logins(agent: LoginAgent): BrowserSignedIn[] | null {
    // A browser or a window that is up is asked; one that is down has what was written when
    // it closed, and a profile no browser ever closed on has nothing to tell.
    const asked = agent.up || this.window(agent.id) !== undefined;
    const hosts = this.held.get(agent.id) ?? (asked ? {} : undefined);
    if (!agent.reads || hosts === undefined) return null;
    const now = this.now();
    const live = Object.entries(hosts).filter(([, until]) => until > now);
    if (agent.hosts.length > 0) {
      return [...new Set(agent.hosts)].map((pattern) => {
        const last = live.filter(([host]) => covers(pattern, host)).map(([, until]) => until.getTime());
        return { host: pattern, until: last.length > 0 ? moment(new Date(Math.max(...last))) : null };
      });
    }
    return live
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .slice(0, TOLD)
      .map(([host, until]) => ({ host, until: moment(until) }));
  }
}
