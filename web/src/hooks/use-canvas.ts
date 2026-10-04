/**
 * One open canvas: its text, its status and what the panel can do with it. The machine runs in a
 * `CanvasRunner` outside React, so a keystroke, a timer and a reply all meet the newest state.
 *
 * Leaving a canvas — the panel closing, another canvas or conversation opening — writes its draft
 * at once and hands its runner to `saveInBackground`, which lets the save in flight land and sends
 * what was typed after it. The next canvas shows at once and loads on its own.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { ArtifactSummary } from "../api/artifact-types";
import { onArtifactEvent } from "../lib/artifact-events";
import { saveInBackground } from "../lib/canvas-handoff";
import { type CanvasInput, type CanvasState, type CanvasStatus, openState, statusOf } from "../lib/canvas-machine";
import { CanvasRunner } from "../lib/canvas-runner";
import { isDirty } from "../lib/canvas-state";
import { guardUnload } from "../lib/unload-guard";
import { useOnline } from "./use-online";
import { useReloadOnReconnect } from "./use-reload-on-reconnect";

export type CanvasController = {
  state: CanvasState;
  status: CanvasStatus;
  /** This device could not keep the last draft. */
  draftFailed: boolean;
  edit(text: string): void;
  /** Cmd/Ctrl+S. */
  save(): void;
  blur(): void;
  composition(composing: boolean): void;
  /** Saves the text as it is now; the version that holds it, or null when none will. */
  flush(): Promise<number | null>;
  /** How long the save in flight may still go unanswered, in ms; 0 when none is out. With `first`,
   *  by the deadline it was first given, which is all a message waits. */
  waitMs(first?: boolean): number;
  keepMine(): void;
  loadTheirs(): void;
  undo(): void;
  /** Version `version`, holding `content`, was restored as the newest; an image has no text. */
  restored(version: number, content: string | null): void;
  renamed(summary: ArtifactSummary): void;
  /** The canvas as a re-import left it: taken as the stream's own word of the change would be. */
  imported(summary: ArtifactSummary): void;
  /** Loads again after a failed first read; otherwise retries or reads, whichever is due. */
  reload(): void;
};

type View = { id: string; state: CanvasState; draftFailed: boolean };

/** Canvas `id`, read again each time the activity stream comes back (`connected`) after a drop. */
export function useCanvas(id: string, connected: boolean): CanvasController {
  const [view, setView] = useState<View>(() => ({ id, state: openState(id, null), draftFailed: false }));
  const runner = useRef<CanvasRunner | null>(null);

  useEffect(() => {
    const current: CanvasRunner = new CanvasRunner(id, () =>
      setView({ id, state: current.state, draftFailed: current.draftFailed }),
    );
    runner.current = current;
    current.start();
    const unsubscribe = onArtifactEvent((event) => current.send({ type: "event", artifact: event.artifact }));
    const visibility = () => current.visibility(document.visibilityState === "hidden");
    const pagehide = () => current.keepDraft();
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", pagehide);
    return () => {
      unsubscribe();
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", pagehide);
      runner.current = null;
      current.detach();
      if (current.needsSave()) void saveInBackground(current);
    };
  }, [id]);

  useReloadOnReconnect(connected, () => runner.current?.send({ type: "resync" }));
  const online = useOnline();
  // Until the new canvas's runner speaks, the panel shows it loading rather than the last one's text.
  const blank = useMemo(() => openState(id, null), [id]);
  const actions = useMemo(() => {
    const send = (input: CanvasInput) => runner.current?.send(input);
    return {
      edit: (text: string) => runner.current?.edit(text),
      save: () => send({ type: "saveDue", reason: "manual" }),
      blur: () => send({ type: "saveDue", reason: "blur" }),
      composition: (composing: boolean) => send({ type: "composition", composing }),
      flush: () => runner.current?.flush() ?? Promise.resolve(null),
      waitMs: (first?: boolean) => runner.current?.waitMs(first) ?? 0,
      keepMine: () => send({ type: "keepMine" }),
      loadTheirs: () => send({ type: "loadTheirs" }),
      undo: () => runner.current?.undo(),
      restored: (version: number, content: string | null) => send({ type: "restored", version, content: content ?? "" }),
      renamed: (summary: ArtifactSummary) => send({ type: "renamed", summary }),
      imported: (summary: ArtifactSummary) => send({ type: "event", artifact: summary }),
      reload: () => send({ type: "resync" }),
    };
  }, []);
  const shown = view.id === id;
  const state = shown ? view.state : blank;
  // Text that is neither saved nor kept on this device is lost with the page: the browser asks first.
  const atRisk = shown && view.draftFailed && isDirty(view.state);
  useEffect(() => (atRisk ? guardUnload() : undefined), [atRisk]);
  return { state, status: statusOf(state, online), draftFailed: shown && view.draftFailed, ...actions };
}
