// The desktop routes and keys as both fakes answer them, so a screen is tested against one
// set of rules.
//
// It mirrors `server/routes_desktop.py`, `server/desktop_runtime.py` and `texts_desktop.py`:
// the machine is told as a helper that answered or as none, with every other key unknown; an
// agent's own setting is read whatever the machine has; a picture is refused first for an
// agent that is off, then for each thing the helper says is in the way, in one sentence of
// the server's own; it is saved under the first write path where the agent has one, a folder
// of the workspace that the answer names from the workspace (`browser/saved.py`); asking
// for the permissions answers what the helper holds afterwards, or a 409 when there is no
// helper or the console is locked; and the four tools are held by every agent whose file says
// `on`, with or without a helper.
import type { DesktopConnection, DesktopPermissions, DesktopShot, RegistryTool } from "../api/types";

export type DesktopReply = { status: number; body: unknown; wait?: Promise<unknown> };

type Refusal = { status: number; detail: string };

/** The server's sentences, word for word (`texts_desktop.py`, `texts.py`). */
export const DESKTOP_SAID = {
  off: "Agent này chưa bật computer nên không chụp màn hình.",
  absent:
    "Máy này chưa có trình trợ giúp desktop đang chạy, nên chưa nhìn và chưa thao tác được trên màn hình. Việc cài và mở nó là của chủ máy.",
  locked: "Màn hình của máy đang khoá, nên không chụp và không thao tác được. Chờ chủ máy mở khoá.",
  asleep: "Màn hình của máy đang tắt, nên không chụp và không thao tác được. Chờ chủ máy đánh thức màn hình.",
  noScreen:
    "Trình trợ giúp desktop chưa được cấp quyền Ghi màn hình (Screen Recording), nên không chụp được. Chủ máy cấp quyền này trong Cài đặt hệ thống.",
  outside:
    "Từ chối: ứng dụng đang ở trước nằm ngoài danh sách computer_apps của agent này, nên không chụp. Đưa một ứng dụng trong danh sách lên trước bằng computer_act với kind=focus_app.",
  unknownAgent: (id: string) => `Không có agent tên ${id}.`,
};

/** The four tools an agent's `computer: on` brings, in the order the registry lists them. */
export const DESKTOP_TOOLS = ["computer_act", "computer_observe", "computer_screenshot", "computer_state"];

/** A machine with no helper answering: every key but `present` unknown. */
export function desktopAbsent(): DesktopConnection {
  return { present: false, version: null, protocol: null, locked: null, display_asleep: null, screen_recording: null, accessibility: null };
}

/** A helper that answered, with the screen open and both permissions granted. */
export function desktopReady(overrides: Partial<DesktopConnection> = {}): DesktopConnection {
  return {
    present: true,
    version: "0.1.0",
    protocol: 1,
    locked: false,
    display_asleep: false,
    screen_recording: true,
    accessibility: true,
    ...overrides,
  };
}

/** What the fake reads of an agent: the desktop keys of its file and its write paths. */
export type DesktopCrewMember = { id: string; computer?: "off" | "on"; computer_apps?: string[]; write_paths?: string[] };

/** The size of the display the fake's helper pictures. */
const SIZE = { width: 1456, height: 910 };

export class FakeDesktop {
  /** Answer as the server did before it had a desktop: no key in `/connections`, no tool row,
   *  and no route here. */
  old = false;
  machine: DesktopConnection = desktopAbsent();
  /** The crew, each agent with the desktop keys of its file. Each fake points it at its own. */
  crew: () => DesktopCrewMember[] = () => [];
  /** What the helper holds once macOS was asked; unset leaves both as they were. */
  granted: Partial<DesktopPermissions> = {};
  /** What a kind of request is refused with, for as long as a test leaves it set. */
  refuse: Partial<Record<"shot" | "ask", Refusal>> = {};
  /** A picture taken while this is set is answered once it settles. */
  holdShot: Promise<unknown> | null = null;
  /** How many times the permissions were asked for: only a person's press may make one. */
  presses = 0;
  /** The pictures taken, by path, newest last. */
  shots: DesktopShot[] = [];

  /** The `desktop` key of GET /connections; nothing from a server older than it. */
  status(): DesktopConnection | undefined {
    return this.old ? undefined : { ...this.machine };
  }

  /** The rows GET /tools adds to the crew's own: each held by every agent whose file says on,
   *  with or without a helper; only the one that acts asks first. */
  registryTools(): RegistryTool[] {
    if (this.old) return [];
    const holders = this.crew().filter((a) => a.computer === "on").map((a) => a.id).sort();
    if (holders.length === 0) return [];
    return DESKTOP_TOOLS.map((name) => ({
      name,
      description: "",
      requires_approval: name === "computer_act",
      agents: holders,
      optional: false,
      with_desktop: true,
    }));
  }

  /** Answers one of the three routes, or nothing for a path that is not the desktop's. */
  route(path: string, method: string): DesktopReply | null {
    if (path === "/desktop/permissions") return this.old ? notFound() : method === "POST" ? this.ask() : notAllowed();
    const match = path.match(/^\/agents\/([^/]+)\/desktop(\/screenshot)?$/);
    if (!match) return null;
    if (this.old) return notFound();
    const shot = match[2] !== undefined;
    if (method !== (shot ? "POST" : "GET")) return notAllowed();
    const agentId = decodeURIComponent(match[1]);
    const agent = this.crew().find((a) => a.id === agentId);
    if (!agent) return { status: 404, body: { detail: DESKTOP_SAID.unknownAgent(agentId) } };
    if (!shot) {
      return { status: 200, body: { mode: agent.computer ?? "off", apps: agent.computer_apps ?? [], machine: { ...this.machine } } };
    }
    const reply = this.take(agent);
    return this.holdShot ? { ...reply, wait: this.holdShot } : reply;
  }

  private take(agent: DesktopCrewMember): DesktopReply {
    const m = this.machine;
    const refused = (detail: string) => ({ status: 409, body: { detail } });
    if ((agent.computer ?? "off") !== "on") return refused(DESKTOP_SAID.off);
    if (!m.present) return refused(DESKTOP_SAID.absent);
    if (m.locked) return refused(DESKTOP_SAID.locked);
    if (m.display_asleep) return refused(DESKTOP_SAID.asleep);
    if (m.screen_recording === false) return refused(DESKTOP_SAID.noScreen);
    if (this.refuse.shot) return { status: this.refuse.shot.status, body: { detail: this.refuse.shot.detail } };
    const frame_id = `${(this.shots.length + 1).toString(16).padStart(16, "0")}-${SIZE.width}x${SIZE.height}-1`;
    const folder = agent.write_paths?.[0] ? `${agent.write_paths[0]}/desktop` : "desktop";
    const taken: DesktopShot = { frame_id, path: `${folder}/${frame_id}.png`, ...SIZE };
    this.shots.push(taken);
    return { status: 200, body: taken };
  }

  private ask(): DesktopReply {
    this.presses += 1;
    if (this.refuse.ask) return { status: this.refuse.ask.status, body: { detail: this.refuse.ask.detail } };
    if (!this.machine.present) return { status: 409, body: { detail: DESKTOP_SAID.absent } };
    if (this.machine.locked) return { status: 409, body: { detail: DESKTOP_SAID.locked } };
    this.machine = { ...this.machine, ...this.granted };
    const { screen_recording, accessibility } = this.machine;
    return { status: 200, body: { screen_recording, accessibility } };
  }
}

const notFound = (): DesktopReply => ({ status: 404, body: { detail: "Not Found" } });
const notAllowed = (): DesktopReply => ({ status: 405, body: { detail: "Method Not Allowed" } });
