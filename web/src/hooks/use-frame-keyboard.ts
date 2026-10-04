import { type RefObject, useLayoutEffect, useState } from "react";
import { behindWatch } from "../lib/behind-watch";

/**
 * Whether the frame has the keyboard now: what the person types goes to the page, not to the app.
 * A style sheet cannot tell (`:focus` is not defined for a frame), so it is read from the document
 * each time the focus can have moved: the app's window loses it to the frame and gets it back, and
 * an element of the app takes or loses it. A window that is not in front is told of none of this,
 * so from the time it loses the focus the document is also read on a beat (`behind-watch.ts`),
 * until the browser says the keys go to the app's document or a frame in it again. `shown` tells
 * one frame from the next and is null while the page is stopped; a frame that was just put up has
 * taken nothing yet.
 */
export function useFrameKeyboard(frame: RefObject<HTMLIFrameElement | null>, shown: number | null): boolean {
  const [held, setHeld] = useState(false);
  // Not put up anew for each frame: the window stays behind while one frame replaces another.
  useLayoutEffect(() => {
    const look = () => setHeld(document.activeElement === frame.current);
    const behind = behindWatch(() => {
      look();
      if (document.hasFocus()) behind.stop();
    });
    const lost = () => {
      look();
      behind.start();
    };
    window.addEventListener("blur", lost);
    window.addEventListener("focus", look);
    document.addEventListener("focusin", look, true);
    document.addEventListener("focusout", look, true);
    return () => {
      behind.stop();
      window.removeEventListener("blur", lost);
      window.removeEventListener("focus", look);
      document.removeEventListener("focusin", look, true);
      document.removeEventListener("focusout", look, true);
    };
  }, [frame]);
  // `shown` is here to look again when the frame changes.
  useLayoutEffect(() => setHeld(document.activeElement === frame.current), [frame, shown]);
  return held;
}
