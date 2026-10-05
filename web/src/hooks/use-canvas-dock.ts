/**
 * What the canvas dock beside the conversation shows — nothing, the conversation's canvases, or
 * one canvas — and the moves between them, and which canvas a message sent now names.
 *
 * Leaving a canvas by hand (closing it, going back to the list, Escape) waits for its last save,
 * at most 5 seconds. When no version holds the text by then because the save failed, the panel
 * stays and says why, and the person may close it anyway, keeping the draft on this device, or in
 * this tab alone where the browser keeps none. A save still going out inside its own deadline does
 * not hold the panel: it closes, and `saveInBackground` goes on waiting. A deleted canvas closes at once.
 *
 * Opening another conversation does not wait: the dock shows nothing in that very render, and the
 * panel going away hands its last save to `saveInBackground`, whose failure becomes a notice in
 * `use-canvas-chat-notices`. Any move made while a "Canvas mới" request is out means its reply opens nothing.
 *
 * A message waits for the saves too, but only 5 seconds past the deadline a save was first given:
 * it then goes with the canvas as last saved, and the chat says so.
 *
 * The canvas this tab is talking about, `focusId`, is not the one on show: it is empty until a canvas
 * is opened here and null once the person closed it on a wide screen, while closing the overlay of a
 * narrow screen or going back to the list leaves it. The server keeps its own copy, set by the
 * message that names it, so opening a canvas tells the server nothing.
 */

import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CreatableKind, MessageCanvas } from "../api/artifact-types";
import { isArtifactId } from "../lib/artifact-tag";
import { closedFor, type DockState, type DockTab, type DockView } from "../lib/canvas-dock-state";
import { flushAll, handoffOut, within } from "../lib/canvas-handoff";
import { type CanvasChatNotices, useCanvasChatNotices } from "./use-canvas-chat-notices";
import { useCanvasCreate } from "./use-canvas-create";
import { type CanvasList, useCanvasList } from "./use-canvas-list";

export type { DockTab, DockView };

/** How long leaving a canvas, or sending a message, waits for the last save. */
export const DOCK_FLUSH_MS = 5000;

/** What the open panel lends the dock: its last save, whether its canvas is gone, whether its person
 *  types, how long its save in flight may still go unanswered (with `first`, by the deadline it was
 *  first given), and whether this device kept its draft. */
export type PanelHandle = {
  flush(): Promise<number | null>;
  gone(): boolean;
  typing(): boolean;
  waitMs(first?: boolean): number;
  draftFailed(): boolean;
};

export type CanvasDock = Omit<DockState, "conversationId"> & Omit<CanvasChatNotices, "kept"> & {
  list: CanvasList;
  showList(): Promise<void>;
  open(id: string, options?: { quiet?: boolean }): void;
  close(): Promise<void>;
  forceClose(): void;
  /** A new canvas of `kind`, markdown unless said, opened in the editor. */
  create(kind?: CreatableKind): Promise<void>;
  /** The Canvas button: opens the list, brings the canvas tab forward, or closes. */
  toggle(): Promise<void>;
  selectTab(tab: DockTab): void;
  /** Lends the dock the open panel's handle until the returned function is called. */
  bind(handle: PanelHandle): () => void;
  /** The open canvas's last save, or null when none lands within 5 seconds after the save in
   *  flight has had the deadline it was first given; waits for the saves of canvases left meanwhile
   *  as well, and gives up on those at the same time. */
  flush(): Promise<number | null>;
  /** The same wait, for a message about to go: whether the canvas it names still has text no version holds. */
  flushForMessage(): Promise<boolean>;
  /** The dock's own element, which its view fills in. */
  box: RefObject<HTMLDivElement | null>;
  /** Whether the person is typing in the open canvas or has the keyboard anywhere in the dock, in a
   *  page's frame too: either way a canvas opened now must not take the dock from them. */
  typing(): boolean;
  /** Whether the open canvas holds the person's typing: text no version has yet, or the keyboard in
   *  its editor. Narrower than `typing`, for what already covers the dock and is about to leave it. */
  editing(): boolean;
  /** What a message sent now says of the canvas: nothing until one is opened here. */
  messageCanvas(): MessageCanvas | undefined;
  /** A mark of the moves made so far, for `restore`. */
  ticket(): number;
  /** Opens the canvas an earlier answer named, quietly, unless the dock moved since `ticket` was read. */
  restore(id: string, ticket: number): void;
};

export function useCanvasDock(conversationId: string | null, connected: boolean, wide: boolean): CanvasDock {
  const [state, setState] = useState(() => closedFor(conversationId));
  const { kept, ...notices } = useCanvasChatNotices(conversationId);
  const list = useCanvasList(conversationId, connected);
  const moves = useRef(0);
  const panel = useRef<PanelHandle | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const shown = state.conversationId === conversationId ? state : closedFor(conversationId);
  const latest = useRef(shown);
  latest.current = shown;

  useEffect(() => {
    moves.current++;
    setState((was) => (was.conversationId === conversationId ? was : closedFor(conversationId)));
  }, [conversationId]);

  const flush = useCallback(async () => {
    // The panel's save starts first, so the deadline it brings is known when the wait is set.
    const saving = panel.current?.flush() ?? null;
    return flushAll(DOCK_FLUSH_MS, saving, panel.current?.waitMs(true) ?? 0);
  }, []);
  const flushForMessage = useCallback(async () => {
    const asked = panel.current;
    const version = await flush();
    const { focusId } = latest.current;
    if (typeof focusId !== "string") return false;
    // The panel asked is still the one open, its canvas is still there, and no version holds its text.
    const open = version === null && asked !== null && panel.current === asked && !asked.gone();
    return open || handoffOut(focusId);
  }, [flush]);
  const editing = useCallback(() => Boolean(panel.current?.typing()), []);
  const typing = useCallback(() => editing() || Boolean(box.current?.contains(document.activeElement)), [editing]);
  const messageCanvas = useCallback((): MessageCanvas | undefined => {
    const { focusId } = latest.current;
    if (focusId === undefined) return undefined;
    return focusId === null ? { artifact_id: null } : { artifact_id: focusId, selection: null };
  }, []);
  const readTicket = useCallback(() => moves.current, []);

  const move = useCallback(
    (next: Partial<DockState>) => {
      moves.current++;
      setState((was) => ({ ...was, conversationId, stuck: false, creating: false, createFailed: false, quiet: false, ...next }));
    },
    [conversationId],
  );
  const progress = useCallback(
    (next: { creating: boolean; createFailed: boolean }) => setState((was) => ({ ...was, ...next })),
    [],
  );
  const opened = useCallback(
    (id: string) => move({ view: "canvas", artifactId: id, focusId: id, created: true, tab: "canvas" }),
    [move],
  );
  const create = useCanvasCreate({ conversationId, moves, progress, opened });

  const actions = useMemo(() => {
    const leave = async (next: Partial<DockState>) => {
      const ticket = ++moves.current;
      const handle = panel.current;
      if (handle && !handle.gone()) {
        const version = await within(DOCK_FLUSH_MS, handle.flush(), null);
        if (moves.current !== ticket) return;
        // A save inside its deadline has not failed: the panel closes and the handoff waits on.
        if (version === null && !handle.gone() && handle.waitMs() === 0) {
          setState((was) => ({ ...was, stuck: true }));
          return;
        }
      }
      move(next);
    };
    // Only a wide screen's close ends the subject: a narrow one just puts the overlay away.
    const closed = { view: "closed", artifactId: null, created: false, ...(wide ? { focusId: null } : {}) } as const;
    const listed = { view: "list", artifactId: null, created: false, tab: "canvas" } as const;
    const open = (id: string, options?: { quiet?: boolean }) => {
      kept.current.delete(id);
      move({ view: "canvas", artifactId: id, focusId: id, created: false, tab: "canvas", quiet: options?.quiet === true });
    };
    return {
      showList: () => leave(listed),
      open,
      restore: (id: string, mark: number) => {
        if (moves.current === mark && latest.current.conversationId === conversationId && isArtifactId(id)) {
          open(id, { quiet: true });
        }
      },
      close: () => leave(closed),
      forceClose: () => {
        const open = latest.current.artifactId;
        // Told of the loss already only when this device kept the text; otherwise the notice follows.
        if (open !== null && !panel.current?.draftFailed()) kept.current.add(open);
        move(closed);
      },
      toggle: async () => {
        const { view, tab } = latest.current;
        if (view === "closed") await leave(listed);
        else if (tab === "activity") setState((was) => ({ ...was, tab: "canvas" }));
        else await leave(closed);
      },
      selectTab: (tab: DockTab) => setState((was) => ({ ...was, tab })),
    };
  }, [conversationId, wide, move]);

  const bind = useCallback((handle: PanelHandle) => {
    panel.current = handle;
    return () => {
      if (panel.current === handle) panel.current = null;
    };
  }, []);

  const { conversationId: _, ...view } = shown;
  const saves = { flush, flushForMessage };
  return { ...view, list, ...notices, ...actions, create, bind, box, ...saves, typing, editing, messageCanvas, ticket: readTicket };
}
