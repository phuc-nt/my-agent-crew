import { useCallback, useState } from "react";
import { REPORT_ERRORS } from "../lib/error-report";
import type { FrameError } from "../lib/frame-messages";

/**
 * What the page on show has reported since it was put up. `version` is the one it shows, `count`
 * how many reports it made, and `recent` the newest few, which is all there is room to keep. The
 * frame hears a page out on `FRAME_REPORTS_MAX` messages, reports or not, so `count` goes no higher
 * than that. `silenced` once the frame has heard the last of them: what the page says after that
 * is not read, so it may have reported more. `mount` tells one page from the next.
 */
export type PageReport = { mount: number; version: number; count: number; recent: FrameError[]; silenced: boolean };

export function usePageReport(version: number) {
  const [report, setReport] = useState<PageReport>({ mount: 0, version, count: 0, recent: [], silenced: false });
  const add = useCallback(
    (error: FrameError) =>
      setReport((was) => ({ ...was, count: was.count + 1, recent: [...was.recent, error].slice(-REPORT_ERRORS) })),
    [],
  );
  /** The frame heard the last message it hears the page on show out on. */
  const silence = useCallback(() => setReport((was) => ({ ...was, silenced: true })), []);
  /** A page of `version` went up, or the one on show was stopped: what the one before said is gone. */
  const reset = useCallback(
    (next: number) => setReport((was) => ({ mount: was.mount + 1, version: next, count: 0, recent: [], silenced: false })),
    [],
  );
  return { report, add, silence, reset };
}
