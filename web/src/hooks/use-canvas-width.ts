/**
 * How wide the canvas column beside a wide conversation is: what the person last chose by
 * dragging its edge or with the arrow keys, or half the room beside the sidebar. Either way the
 * canvas and the conversation each keep at least 360 px. A choice that no longer fits a narrower
 * window shrinks to fit there and comes back when the window widens again.
 */

import { useCallback, useEffect, useState } from "react";
import { readJson, writeJson } from "../lib/local-store";

export const CANVAS_MIN = 360;
/** How far one arrow key moves the canvas's edge. */
export const CANVAS_STEP = 16;
const KEY = "canvas-width";
const SIDEBAR_FALLBACK = 272;

/** The room beside the sidebar, whose width the stylesheet sets. */
function room(): number {
  const sidebar = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width"));
  return window.innerWidth - (sidebar > 0 ? sidebar : SIDEBAR_FALLBACK);
}

function kept(): number | null {
  const value = readJson(KEY);
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export type CanvasWidth = {
  width: number;
  min: number;
  max: number;
  /** Sets the width; `keep` also remembers it for later visits (a drag's end, an arrow key). */
  resize(next: number, keep?: boolean): void;
};

export function useCanvasWidth(): CanvasWidth {
  const [space, setSpace] = useState(room);
  const [chosen, setChosen] = useState(kept);

  useEffect(() => {
    const resized = () => setSpace(room());
    window.addEventListener("resize", resized);
    return () => window.removeEventListener("resize", resized);
  }, []);

  const max = Math.max(CANVAS_MIN, space - CANVAS_MIN);
  const fit = useCallback((value: number) => Math.min(max, Math.max(CANVAS_MIN, Math.round(value))), [max]);
  const resize = useCallback(
    (next: number, keep = false) => {
      const value = fit(next);
      setChosen(value);
      if (keep) writeJson(KEY, value);
    },
    [fit],
  );
  return { width: fit(chosen ?? space / 2), min: CANVAS_MIN, max, resize };
}
