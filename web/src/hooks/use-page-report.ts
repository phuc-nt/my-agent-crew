import { useCallback, useState } from "react";
import { REPORT_ERRORS } from "../lib/error-report";
import type { FrameError } from "../lib/frame-messages";

/**
 * What the page on show has reported since it was put up. `version` is the one it shows, `count`
 * how many reports it made, and `recent` the newest few, which is all there is room to keep: a
 * page can report as often as it likes. `mount` tells one page from the next.
 */
export type PageReport = { mount: number; version: number; count: number; recent: FrameError[] };

export function usePageReport(version: number) {
  const [report, setReport] = useState<PageReport>({ mount: 0, version, count: 0, recent: [] });
  const add = useCallback(
    (error: FrameError) =>
      setReport((was) => ({ ...was, count: was.count + 1, recent: [...was.recent, error].slice(-REPORT_ERRORS) })),
    [],
  );
  /** A page of `version` went up, or the one on show was stopped: what the one before said is gone. */
  const reset = useCallback(
    (next: number) => setReport((was) => ({ mount: was.mount + 1, version: next, count: 0, recent: [] })),
    [],
  );
  return { report, add, reset };
}
