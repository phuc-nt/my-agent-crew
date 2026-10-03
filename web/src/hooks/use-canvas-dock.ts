/**
 * What the canvas dock beside the conversation shows — nothing, the conversation's canvases, or
 * one canvas — and the moves between them, and which canvas a message sent now names.
 *
 * Leaving a canvas by hand (closing it, going back to the list, Escape) waits for its last save,
 * at most 5 seconds. When no version holds the text by then, the panel stays and says why, and the
 * person may close it anyway, keeping the draft on this device. A deleted canvas closes at once.
 *
 * Opening another conversation does not wait: the dock shows nothing in that very render, and the
 * panel going away hands its last save to `saveInBackground`, whose failure becomes a notice here.
 * Any move made while a "Canvas mới" request is out means its reply opens nothing.
 *
 * The canvas this tab is talking about, `focusId`, is not the one on show: it is empty until a canvas
 * is opened here and null once the person closed it on a wide screen, while closing the overlay of a
 * narrow screen or going back to the list leaves it. The server keeps its own copy, set by the
 * message that names it, so opening a canvas tells the server nothing.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { artifactApi } from "../api/artifact-client";
import type { MessageCanvas } from "../api/artifact-types";
import { vi } from "../i18n/vi";
import { isArtifactId } from "../lib/artifact-tag";
import { flushAll, type HandoffFailure, onHandoffFailed, within } from "../lib/canvas-handoff";
import { type CanvasList, useCanvasList } from "./use-canvas-list";

/** How long leaving a canvas, or sending a message, waits for the last save. */
export const DOCK_FLUSH_MS = 5000;

export type DockView = "closed" | "list" | "canvas";
export type DockTab = "activity" | "canvas";
/** What the open panel lends the dock: its last save, whether its canvas is gone, whether its person types. */
export type PanelHandle = { flush(): Promise<number | null>; gone(): boolean; typing(): boolean };

type State = {
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

export type CanvasDock = Omit<State, "conversationId"> & {
  list: CanvasList;
  handoffs: HandoffFailure[];
  showList(): Promise<void>;
  open(id: string, options?: { quiet?: boolean }): void;
  close(): Promise<void>;
  forceClose(): void;
  create(): Promise<void>;
  /** The Canvas button: opens the list, brings the canvas tab forward, or closes. */
  toggle(): Promise<void>;
  selectTab(tab: DockTab): void;
  /** Lends the dock the open panel's handle until the returned function is called. */
  bind(handle: PanelHandle): () => void;
  /** The open canvas's last save, or null when none lands within 5 seconds; waits for the saves
   *  of canvases left meanwhile as well, and gives up on those at the same time. */
  flush(): Promise<number | null>;
  /** Whether the person is typing in the open canvas, which a canvas opened now must not take from them. */
  typing(): boolean;
  /** What a message sent now says of the canvas: nothing until one is opened here. */
  messageCanvas(): MessageCanvas | undefined;
  /** A mark of the moves made so far, for `restore`. */
  ticket(): number;
  /** Opens the canvas an earlier answer named, quietly, unless the dock moved since `ticket` was read. */
  restore(id: string, ticket: number): void;
  dismissHandoff(id: string): void;
};

const closedFor = (conversationId: string | null): State => ({
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

export function useCanvasDock(conversationId: string | null, connected: boolean, wide: boolean): CanvasDock {
  const [state, setState] = useState(() => closedFor(conversationId));
  const [handoffs, setHandoffs] = useState<HandoffFailure[]>([]);
  const list = useCanvasList(conversationId, connected);
  const moves = useRef(0);
  const panel = useRef<PanelHandle | null>(null);
  // Canvases closed anyway: the person already knows their last save did not land.
  const kept = useRef(new Set<string>());
  const shown = state.conversationId === conversationId ? state : closedFor(conversationId);
  const latest = useRef(shown);
  latest.current = shown;

  useEffect(() => {
    moves.current++;
    setState((was) => (was.conversationId === conversationId ? was : closedFor(conversationId)));
  }, [conversationId]);

  useEffect(
    () =>
      onHandoffFailed((failure) => {
        if (kept.current.delete(failure.id)) return;
        setHandoffs((told) => [...told.filter((f) => f.id !== failure.id), failure]);
      }),
    [],
  );

  const flush = useCallback(async () => flushAll(DOCK_FLUSH_MS, panel.current?.flush() ?? null), []);
  const typing = useCallback(() => panel.current?.typing() ?? false, []);
  const messageCanvas = useCallback((): MessageCanvas | undefined => {
    const { focusId } = latest.current;
    if (focusId === undefined) return undefined;
    return focusId === null ? { artifact_id: null } : { artifact_id: focusId, selection: null };
  }, []);
  const readTicket = useCallback(() => moves.current, []);

  const actions = useMemo(() => {
    const move = (next: Partial<State>) => {
      moves.current++;
      setState((was) => ({ ...was, conversationId, stuck: false, creating: false, createFailed: false, quiet: false, ...next }));
    };
    const leave = async (next: Partial<State>) => {
      const ticket = ++moves.current;
      const handle = panel.current;
      if (handle && !handle.gone()) {
        const version = await within(DOCK_FLUSH_MS, handle.flush(), null);
        if (moves.current !== ticket) return;
        if (version === null && !handle.gone()) {
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
        if (open !== null) kept.current.add(open);
        move(closed);
      },
      create: async () => {
        if (conversationId === null) return;
        const ticket = ++moves.current;
        setState((was) => ({ ...was, creating: true, createFailed: false }));
        const body = { title: vi.canvas.untitled, kind: "markdown", content: "", conversation_id: conversationId } as const;
        try {
          const made = await artifactApi.create(body);
          if (moves.current === ticket) {
            move({ view: "canvas", artifactId: made.id, focusId: made.id, created: true, tab: "canvas" });
          }
        } catch {
          if (moves.current === ticket) setState((was) => ({ ...was, creating: false, createFailed: true }));
        }
      },
      toggle: async () => {
        const { view, tab } = latest.current;
        if (view === "closed") await leave(listed);
        else if (tab === "activity") setState((was) => ({ ...was, tab: "canvas" }));
        else await leave(closed);
      },
      selectTab: (tab: DockTab) => setState((was) => ({ ...was, tab })),
    };
  }, [conversationId, wide]);

  const bind = useCallback((handle: PanelHandle) => {
    panel.current = handle;
    return () => {
      if (panel.current === handle) panel.current = null;
    };
  }, []);
  const dismissHandoff = useCallback((id: string) => setHandoffs((told) => told.filter((f) => f.id !== id)), []);

  const { conversationId: _, ...view } = shown;
  return { ...view, list, handoffs, ...actions, bind, flush, typing, messageCanvas, ticket: readTicket, dismissHandoff };
}
