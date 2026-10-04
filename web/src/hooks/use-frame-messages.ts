/**
 * Hears the page in a canvas frame out, and never answers it. A page can post what it likes as
 * often as it likes, so whose message it is and whether the page may still speak are settled before
 * any of it is read: fifty messages of one frame are heard, reports or not, and nothing of a later
 * one is read. The panel is told when the fiftieth is heard, so it can say the page may have said more.
 *
 * The first of the fifty is the hello of the page's own reporter, which ran before any of the page's
 * code. It hands over one end of a message channel, and only that message may: a port in any later
 * message is the page's own and is left alone. What the reporter says over the port is that a
 * person pressed a pointer inside the page, which the page cannot say for it, having no hold on
 * either end. The same words posted to the window are just one more message that is no report. What
 * comes over the port is neither a report nor one of the fifty, and the port is closed when its
 * frame is replaced, stopped or gone.
 */

import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";
import { FRAME_REPORTS_MAX, type FrameError, isFromFrame, isLoadFailure, isPress, readFrameMessage } from "../lib/frame-messages";
import { useOnline } from "./use-online";

type Heard = {
  /** The page reported something that went wrong. */
  onError(error: FrameError): void;
  /** The last message the frame on show is heard out on was just heard. */
  onSilenced(): void;
  /** The reporter of the page on show told of a pointer a person pressed inside it. */
  onPress(): void;
};

/**
 * Listens to the page in `frame`. `shown` tells one frame from the next and is null while the page
 * is stopped: when it changes, the port of the frame before is closed.
 */
export function useFrameMessages(frame: RefObject<HTMLIFrameElement | null>, shown: number | null, heard: Heard): void {
  const online = useOnline();
  const latest = useRef({ ...heard, online });
  latest.current = { ...heard, online };
  // How many messages each frame was heard out on. A frame that replaces another starts from none.
  const [heardOf] = useState(() => new WeakMap<HTMLIFrameElement, number>());
  const port = useRef<MessagePort | null>(null);

  useEffect(() => {
    const listen = (event: MessageEvent) => {
      const from = frame.current;
      // A message that is no report counts too, or a page could be read without end.
      if (!isFromFrame(event, from)) return;
      const before = heardOf.get(from) ?? 0;
      if (before >= FRAME_REPORTS_MAX) return;
      heardOf.set(from, before + 1);
      if (before + 1 === FRAME_REPORTS_MAX) latest.current.onSilenced();
      const told = readFrameMessage(event, from);
      if (told === null) return;
      if (told.port) {
        if (before > 0) return;
        port.current = told.port;
        // Giving the port a listener is what starts it; nothing is ever sent over it from here.
        told.port.onmessage = (press) => {
          if (frame.current === from && isPress(press.data)) latest.current.onPress();
        };
        return;
      }
      // With no network at all, the files a page asks for cannot arrive and there is nothing to tell.
      if (!latest.current.online && isLoadFailure(told.error)) return;
      latest.current.onError(told.error);
    };
    window.addEventListener("message", listen);
    return () => window.removeEventListener("message", listen);
  }, [frame, heardOf]);

  // A layout effect, so the port of a frame is closed before the frame after it can say anything.
  useLayoutEffect(
    () => () => {
      const open = port.current;
      port.current = null;
      if (open === null) return;
      open.onmessage = null;
      open.close();
    },
    // `shown` is what says the frame changed.
    [shown],
  );
}
