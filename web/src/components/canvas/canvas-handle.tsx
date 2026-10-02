/**
 * The edge between the conversation and the canvas column, dragged with the pointer or moved
 * 16 px at a time with the arrow keys. The canvas sits on the right, so moving the edge left
 * widens it. Where a drag ends, or an arrow key leaves it, is the width remembered for later
 * visits; the widths a drag passes through are only shown.
 */

import { type KeyboardEvent, type PointerEvent, useEffect, useRef } from "react";
import { CANVAS_STEP, type CanvasWidth } from "../../hooks/use-canvas-width";
import { vi } from "../../i18n/vi";

export function CanvasHandle({ width, min, max, resize }: CanvasWidth) {
  // The window narrowing mid-drag changes the bounds `resize` keeps to.
  const latest = useRef(resize);
  latest.current = resize;
  const release = useRef<(() => void) | null>(null);
  useEffect(() => () => release.current?.(), []);

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    // No text selection follows the pointer across the chat while the edge moves.
    event.preventDefault();
    release.current?.();
    const start = event.clientX;
    const from = width;
    let last = from;
    const move = (next: globalThis.PointerEvent) => {
      last = from + start - next.clientX;
      latest.current(last);
    };
    const end = (next: globalThis.PointerEvent) => {
      if (next.type === "pointerup") last = from + start - next.clientX;
      latest.current(last, true);
      stop();
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      release.current = null;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    release.current = stop;
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowLeft" ? CANVAS_STEP : event.key === "ArrowRight" ? -CANVAS_STEP : 0;
    if (step === 0) return;
    event.preventDefault();
    resize(width + step, true);
  };

  // A focusable separator is the window-splitter pattern; an <hr> takes no keys.
  return (
    <div
      className="canvas-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label={vi.canvas.resize}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
    />
  );
}
