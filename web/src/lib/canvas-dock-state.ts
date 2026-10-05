/** What the canvas dock holds at one moment: which view is on show, which canvas, and how it got there. */

export type DockView = "closed" | "list" | "canvas";
export type DockTab = "activity" | "canvas";

export type DockState = {
  conversationId: string | null;
  view: DockView;
  artifactId: string | null;
  /** The canvas a message sent now names: undefined until one is opened here, null once closed. */
  focusId: string | null | undefined;
  /** The canvas was opened without being asked for, so the keyboard stays where it was. */
  quiet: boolean;
  /** The open canvas was just made here, so its title opens for editing. */
  created: boolean;
  /** Leaving was asked for and no save landed. */
  stuck: boolean;
  tab: DockTab;
  creating: boolean;
  createFailed: boolean;
};

/**
 * Whether the dock has something on show. A canvas the agent is still writing shows there without
 * the dock having been opened, so a dock that is closed may be showing all the same.
 */
export const dockShowing = (view: DockView, writing: boolean): boolean => view !== "closed" || writing;

/** The dock of a conversation nothing has been opened in. */
export const closedFor = (conversationId: string | null): DockState => ({
  conversationId,
  view: "closed",
  artifactId: null,
  focusId: undefined,
  quiet: false,
  created: false,
  stuck: false,
  tab: "canvas",
  creating: false,
  createFailed: false,
});
