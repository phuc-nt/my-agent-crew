/**
 * What the canvas dock beside the conversation shows — nothing, the conversation's canvases, or
 * one canvas — and the moves between them.
 *
 * Leaving a canvas by hand (closing it, going back to the list, Escape) waits for its last save,
 * at most 5 seconds. When no version holds the text by then, the panel stays and says why, and the
 * person may close it anyway, keeping the draft on this device. A deleted canvas closes at once.
 *
 * Opening another conversation does not wait: the dock shows nothing in that very render, and the
 * panel going away hands its last save to `saveInBackground`, whose failure becomes a notice here.
 * Any move made while a "Canvas mới" request is out means its reply opens nothing.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { artifactApi } from "../api/artifact-client";
import { vi } from "../i18n/vi";
import { type HandoffFailure, onHandoffFailed } from "../lib/canvas-handoff";
import { type CanvasList, useCanvasList } from "./use-canvas-list";

/** How long leaving a canvas waits for its last save. */
export const DOCK_FLUSH_MS = 5000;

export type DockView = "closed" | "list" | "canvas";
export type DockTab = "activity" | "canvas";
/** What the open panel lends the dock: its last save, and whether its canvas is gone. */
export type PanelHandle = { flush(): Promise<number | null>; gone(): boolean };

type State = {
  conversationId: string | null;
  view: DockView;
  artifactId: string | null;
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
  open(id: string): void;
  close(): Promise<void>;
  forceClose(): void;
  create(): Promise<void>;
  /** The Canvas button: opens the list, brings the canvas tab forward, or closes. */
  toggle(): Promise<void>;
  selectTab(tab: DockTab): void;
  /** Lends the dock the open panel's handle until the returned function is called. */
  bind(handle: PanelHandle): () => void;
  /** The open canvas's last save, or null when none lands within 5 seconds. */
  flush(): Promise<number | null>;
  dismissHandoff(id: string): void;
};

const closedFor = (conversationId: string | null): State => ({
  conversationId,
  view: "closed",
  artifactId: null,
  created: false,
  stuck: false,
  tab: "canvas",
  creating: false,
  createFailed: false,
});

export function useCanvasDock(conversationId: string | null, connected: boolean): CanvasDock {
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

  const flush = useCallback(async (): Promise<number | null> => {
    const handle = panel.current;
    if (!handle) return null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const late = new Promise<null>((resolve) => {
      timer = setTimeout(() => resolve(null), DOCK_FLUSH_MS);
    });
    try {
      return await Promise.race([handle.flush(), late]);
    } finally {
      clearTimeout(timer);
    }
  }, []);

  const actions = useMemo(() => {
    const move = (next: Partial<State>) => {
      moves.current++;
      setState((was) => ({ ...was, conversationId, stuck: false, creating: false, createFailed: false, ...next }));
    };
    const leave = async (next: Partial<State>) => {
      const ticket = ++moves.current;
      const handle = panel.current;
      if (handle && !handle.gone()) {
        const version = await flush();
        if (moves.current !== ticket) return;
        if (version === null && !handle.gone()) {
          setState((was) => ({ ...was, stuck: true }));
          return;
        }
      }
      move(next);
    };
    const closed = { view: "closed", artifactId: null, created: false } as const;
    const listed = { view: "list", artifactId: null, created: false, tab: "canvas" } as const;
    return {
      showList: () => leave(listed),
      open: (id: string) => {
        kept.current.delete(id);
        move({ view: "canvas", artifactId: id, created: false, tab: "canvas" });
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
          if (moves.current === ticket) move({ view: "canvas", artifactId: made.id, created: true, tab: "canvas" });
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
  }, [conversationId, flush]);

  const bind = useCallback((handle: PanelHandle) => {
    panel.current = handle;
    return () => {
      if (panel.current === handle) panel.current = null;
    };
  }, []);
  const dismissHandoff = useCallback((id: string) => setHandoffs((told) => told.filter((f) => f.id !== id)), []);

  const { conversationId: _, ...view } = shown;
  return { ...view, list, handoffs, ...actions, bind, flush, dismissHandoff };
}
