/**
 * What a page running in the canvas frame tells the panel. The page can say anything: it is code an
 * agent wrote, in a frame of its own origin. So a report counts only when it came from this frame's
 * own window, which is an origin the browser writes as "null", and only the parts of it the panel
 * can show safely are kept, each with a ceiling. Nothing here posts into the frame.
 */

import { clip } from "./clip-text";

/** The most characters of one report kept; the page's own reporter cuts at the same length. */
export const REPORT_MAX = 2000;
/** The most characters kept of the file a report names. */
export const SOURCE_MAX = 300;

export type FrameError = { message: string; source: string; line: number; column: number };

/** A position the page named: a count, or 0 for anything else. */
const position = (value: unknown): number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.floor(value) : 0;

/** Whether the report says a file the page asked for did not arrive: its own reporter words those
 *  with no line, where a script's error names the line it was thrown on. */
export const isLoadFailure = ({ message, line }: FrameError): boolean => line === 0 && message.startsWith("failed to load ");

/** Where the page says the error is, as far as it said: `source:line:column`. */
export function where({ source, line, column }: FrameError): string {
  const parts: Array<string | number> = source === "" ? [] : [source];
  if (line > 0) parts.push(line);
  if (line > 0 && column > 0) parts.push(column);
  return parts.join(":");
}

/** The report `event` carries, if it is one and came from `frame`'s window; otherwise null. */
export function parseFrameMessage(event: MessageEvent, frame: HTMLIFrameElement | null): FrameError | null {
  const own = frame?.contentWindow;
  // A frame taken out of the page has no window, and a message from nowhere has no source: the two
  // must not be taken for each other.
  if (!own || event.source !== own || event.origin !== "null") return null;
  const data: unknown = event.data;
  if (typeof data !== "object" || data === null) return null;
  const { type, message, source, line, column } = data as Record<string, unknown>;
  if (type !== "canvas-error" || typeof message !== "string") return null;
  return {
    message: clip(message, REPORT_MAX),
    source: typeof source === "string" ? clip(source, SOURCE_MAX) : "",
    line: position(line),
    column: position(column),
  };
}
