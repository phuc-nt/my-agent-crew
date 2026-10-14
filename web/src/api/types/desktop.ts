// The desktop as the server tells of it: the machine's helper on the connections page, an
// agent's own setting with what the machine is for it, a picture tried from the web, and the
// two permissions the helper holds after a person asked macOS for them.

/** An agent's `computer` key. The server takes the word and nothing a parser made of it. */
export type ComputerMode = "off" | "on";

/**
 * The `desktop` key of GET /connections. `present` is true only when a helper answered; with
 * none, every other key is null. Each null is "the helper did not say", never a guess.
 */
export interface DesktopConnection {
  present: boolean;
  version: string | null;
  protocol: number | null;
  locked: boolean | null;
  display_asleep: boolean | null;
  screen_recording: boolean | null;
  accessibility: boolean | null;
}

/** GET /agents/{id}/desktop: the agent's two keys and the machine as it is now. */
export interface AgentDesktop {
  mode: ComputerMode;
  apps: string[];
  machine: DesktopConnection;
}

/** A picture "Thử chụp" took: `path` is relative to the agent's workspace. */
export interface DesktopShot {
  frame_id: string;
  path: string;
  width: number;
  height: number;
}

/** What the helper holds once macOS was asked: null for one it did not say. */
export interface DesktopPermissions {
  screen_recording: boolean | null;
  accessibility: boolean | null;
}
