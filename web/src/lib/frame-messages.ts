/**
 * What a page running in the canvas frame tells the panel. The page can say anything: it is code an
 * agent wrote, in a frame of its own origin. So a message counts only when it came from this frame's
 * own window, which is an origin the browser writes as "null", and only the parts of it the panel
 * can show safely are kept, each with a ceiling.
 *
 * Two things are taken. A report of what went wrong. And the hello of the page's own reporter, which
 * hands over one end of a message channel: over that port, and nowhere else, the reporter says when
 * a person presses inside the page. Nothing here posts into the frame or over the port.
 *
 * How often a page speaks has a ceiling too, and the panel keeps it: the page's own reporter stops
 * at twenty, but a page can post without it.
 */

import { clip } from "./clip-text";

/** The most characters of one report kept; the page's own reporter cuts at the same length. */
export const REPORT_MAX = 2000;
/** The most characters kept of the file a report names. */
export const SOURCE_MAX = 300;
/** The most messages heard from one frame, reports or not; nothing of a later one is read. */
export const FRAME_REPORTS_MAX = 50;

export type FrameError = { message: string; source: string; line: number; column: number };

/** What one message of the frame comes to: a report, or the port its hello hands over. */
export type FrameMessage = { error: FrameError; port?: undefined } | { port: MessagePort; error?: undefined };

/** A position the page named: a count, its fraction cut off, or 0 for anything else. A number too
 *  large to count with is no position either, and would be shown as `1e+308`. */
function position(value: unknown): number {
  const whole = typeof value === "number" ? Math.floor(value) : 0;
  return Number.isSafeInteger(whole) && whole > 0 ? whole : 0;
}

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

/** Whether `event` came from `frame`'s own window, told without reading what it carries. */
export function isFromFrame(event: MessageEvent, frame: HTMLIFrameElement | null): frame is HTMLIFrameElement {
  const own = frame?.contentWindow;
  // A frame taken out of the page has no window, and a message from nowhere has no source: the two
  // must not be taken for each other.
  return !!own && event.source === own;
}

/**
 * What `event` comes to, if it came from `frame`'s window and is a report or a hello with a port;
 * otherwise null. What the message carries is read once. Whether a port may still be taken from
 * this frame is for the caller to say: only the first message of a frame hands one over.
 */
export function readFrameMessage(event: MessageEvent, frame: HTMLIFrameElement | null): FrameMessage | null {
  if (!isFromFrame(event, frame) || event.origin !== "null") return null;
  const data: unknown = event.data;
  if (typeof data !== "object" || data === null) return null;
  const { type, message, source, line, column } = data as Record<string, unknown>;
  if (type === "canvas-hello") {
    const port = event.ports[0];
    return port ? { port } : null;
  }
  if (type !== "canvas-error" || typeof message !== "string") return null;
  return {
    error: {
      message: clip(message, REPORT_MAX),
      source: typeof source === "string" ? clip(source, SOURCE_MAX) : "",
      line: position(line),
      column: position(column),
    },
  };
}

/** Whether what came over the port says a person pressed inside the page. */
export function isPress(data: unknown): boolean {
  return typeof data === "object" && data !== null && (data as Record<string, unknown>).type === "press";
}
