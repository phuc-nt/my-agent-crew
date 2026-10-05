/**
 * The canvases the agent is writing in the turn under way: a card for each in the thread, and at
 * most one of them filling in where the dock is.
 *
 * Nothing here is stored and nothing is asked of the server. Showing one leaves the dock as it
 * was, its open canvas and what a message would carry included: the dock only turns to its canvas
 * tab. What is shown is remembered with the place the dock stood in, and is forgotten the moment
 * the dock moves, the model starts over or the preview is turned off. It does not come back.
 *
 * A canvas comes up by itself once, at the piece that first brings text after the first piece, and
 * only where it is in nobody's way: on a wide screen, with nothing else shown, and not while the
 * person types in a canvas or has the keyboard anywhere in the dock. One written again comes up
 * only over the very canvas it rewrites. A person who put one away is left alone for the rest of
 * the turn; the card still shows any of them.
 *
 * When the call it became ends, the canvas the result names opens quietly in its place, unless the
 * dock is on it already or the canvas behind holds what the person typed meanwhile. The keyboard
 * being in what was shown holds nothing back: it was watching this canvas. A call that failed just
 * puts it away.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { parseArtifactTag } from "../lib/artifact-tag";
import type { DockView } from "../lib/canvas-dock-state";
import { describeWriting, type KnownCanvases, type WritingItem } from "../lib/canvas-writing";
import type { ThreadState } from "../state/thread-reducer";
import type { CanvasDock } from "./use-canvas-dock";

type Thread = { state: Pick<ThreadState, "previews" | "items" | "busy"> };
type Dock = Pick<CanvasDock, "view" | "artifactId" | "open" | "typing" | "editing" | "selectTab"> & { list: KnownCanvases };

/** The canvas on show, how it got there, and where the dock stood when it did. */
type Held = { key: number; asked: number | null; view: DockView; artifactId: string | null };

export type CanvasWriting = {
  /** The canvases being written whose call the answer has not named yet, for the thread's cards. */
  items: WritingItem[];
  /** The one the dock shows, if any. */
  shown: WritingItem | null;
  /** Counts the times the person asked for what is shown; null when it came up by itself. */
  asked: number | null;
  /** The call the shown one turned out to be, which this hook then sees to the end of. */
  callId: string | null;
  show(key: number): void;
  leave(): void;
};

export function useCanvasWriting(thread: Thread, dock: Dock, wide: boolean, enabled: boolean): CanvasWriting {
  const { previews, items: calls, busy } = thread.state;
  // Read once for each piece that arrives: what the tab learns of a canvas later waits for the next.
  const all = useMemo(() => previews.map((preview) => describeWriting(preview, dock.list)), [previews]);
  const items = useMemo(() => (enabled ? all.filter((item) => item.callId === null) : []), [all, enabled]);

  const [held, setHeld] = useState<Held | null>(null);
  const stands = held !== null && enabled && dock.view === held.view && dock.artifactId === held.artifactId;
  const shown = (stands && all.find((item) => item.key === held.key)) || null;
  const callId = shown?.callId ?? null;

  const latest = useRef({ dock, wide, enabled, busy, shown });
  latest.current = { dock, wide, enabled, busy, shown };
  // Each canvas once it has been judged, the person's requests so far, and whether they put one away this turn.
  const [judged] = useState(() => new Set<number>());
  const asks = useRef(0);
  const muted = useRef(false);

  useEffect(() => {
    if (held !== null && shown === null) setHeld((now) => (now === held ? null : now));
  }, [held, shown]);

  useEffect(() => {
    if (!busy) muted.current = false;
  }, [busy]);

  useEffect(() => {
    const { dock, wide, enabled, shown } = latest.current;
    let free = shown === null;
    for (const item of all) {
      if (item.updates < 2 || item.content === "" || judged.has(item.key)) continue;
      judged.add(item.key);
      if (!free || item.callId !== null || !enabled || !wide || muted.current || dock.typing()) continue;
      if (item.rewrite && (item.id === null || dock.view !== "canvas" || dock.artifactId !== item.id)) continue;
      free = false;
      setHeld({ key: item.key, asked: null, view: dock.view, artifactId: dock.artifactId });
      dock.selectTab("canvas");
    }
  }, [all, judged]);

  useEffect(() => {
    if (callId === null) return;
    const call = calls.find((item) => item.kind === "tool" && item.id === callId);
    if (call?.kind !== "tool" || call.status === "running" || call.status === "awaiting") return;
    const { dock } = latest.current;
    const tag = call.status === "done" ? parseArtifactTag(call.output) : null;
    setHeld(null);
    if (tag === null || dock.editing() || (dock.view === "canvas" && dock.artifactId === tag.id)) return;
    dock.open(tag.id, { quiet: true });
  }, [callId, calls]);

  const show = useCallback(
    (key: number) => {
      const { dock } = latest.current;
      // Asked for, it has been judged: it does not come up again by itself once the dock moves on.
      judged.add(key);
      asks.current += 1;
      setHeld({ key, asked: asks.current, view: dock.view, artifactId: dock.artifactId });
      dock.selectTab("canvas");
    },
    [judged],
  );

  const leave = useCallback(() => {
    setHeld(null);
    muted.current = latest.current.busy;
  }, []);

  return { items, shown, asked: stands && shown !== null ? held.asked : null, callId, show, leave };
}
