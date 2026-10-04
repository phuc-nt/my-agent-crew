/**
 * Looking at a frame on a beat while the app's window is not in front. A window that is behind is
 * told nothing of the focus a page in it takes: no `blur`, no `focusin`. And when the person comes
 * back to a window whose frame has the focus, it is the frame's window that is told it is in front
 * again, not the app's. Until an event says the person is back, only looking tells.
 */

/** How long between two looks. */
export const BEHIND_LOOK_MS = 200;

export type BehindWatch = {
  /** Looks every `BEHIND_LOOK_MS` from now on, on one beat however often it is started. */
  start(): void;
  /** No more looks. `look` may call it. */
  stop(): void;
};

export function behindWatch(look: () => void): BehindWatch {
  let due: ReturnType<typeof setTimeout> | undefined;
  const stop = () => clearTimeout(due);
  const start = () => {
    stop();
    due = setTimeout(() => {
      start();
      look();
    }, BEHIND_LOOK_MS);
  };
  return { start, stop };
}
