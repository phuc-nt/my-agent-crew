import { type RefObject, useLayoutEffect, useState } from "react";

/**
 * Whether the frame has the keyboard now: what the person types goes to the page, not to the app.
 * A style sheet cannot tell (`:focus` is not defined for a frame), so it is read from the document
 * each time the focus can have moved: the app's window loses it to the frame and gets it back, and
 * an element of the app takes or loses it. `shown` tells one frame from the next and is null while
 * the page is stopped; a frame that was just put up has taken nothing yet.
 */
export function useFrameKeyboard(frame: RefObject<HTMLIFrameElement | null>, shown: number | null): boolean {
  const [held, setHeld] = useState(false);
  useLayoutEffect(() => {
    const look = () => setHeld(document.activeElement === frame.current);
    look();
    window.addEventListener("blur", look);
    window.addEventListener("focus", look);
    document.addEventListener("focusin", look, true);
    document.addEventListener("focusout", look, true);
    return () => {
      window.removeEventListener("blur", look);
      window.removeEventListener("focus", look);
      document.removeEventListener("focusin", look, true);
      document.removeEventListener("focusout", look, true);
    };
    // `shown` is here to look again when the frame changes.
  }, [frame, shown]);
  return held;
}
