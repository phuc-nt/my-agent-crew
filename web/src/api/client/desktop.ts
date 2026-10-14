import type { AgentDesktop, DesktopPermissions, DesktopShot } from "../types";
import { request } from "./http";

const desktopOf = (agentId: string) => `/agents/${encodeURIComponent(agentId)}/desktop`;

export const desktopApi = {
  /** The agent's mode and applications, and the machine now. It asks the helper for its
   *  state and nothing else. A server older than the route answers 404. */
  agentDesktop: (agentId: string) => request<AgentDesktop>(desktopOf(agentId)),
  /** Takes one picture of the whole display, held to the agent's applications. A 409 says
   *  in one line why there is none. `signal` lets the page give up on a helper that hangs. */
  tryDesktopScreenshot: (agentId: string, signal?: AbortSignal) =>
    request<DesktopShot>(`${desktopOf(agentId)}/screenshot`, { method: "POST", signal }),
  /** The one request that may put a system dialog on the owner's screen: sent on a press,
   *  never on load or on a timer. A 409 says there is no helper or the console is locked. */
  askDesktopPermissions: () => request<DesktopPermissions>("/desktop/permissions", { method: "POST" }),
};
