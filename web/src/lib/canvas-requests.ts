/**
 * The two requests a canvas runner makes, each turning its reply into a machine input.
 *
 * A read with no reply in 30 seconds counts as lost and is retried instead of holding the canvas
 * forever. A save gets the same 30 seconds plus what its body needs at a slow link's pace, so a
 * large canvas on a poor connection is not cut off while it is still going out; one that outlasts
 * even that is reported as too slow, not as lost, and the save sent in its place is given twice
 * the time for its body: a link slower than the pace assumed would otherwise never carry it.
 * `SaveClock` counts those for one canvas, and knows how long its save in flight has left.
 */

import { artifactApi, conflictOf, saveBody, sizeCapOf, storageFullOf } from "../api/artifact-client";
import { ApiError } from "../api/client";
import { utf8Bytes } from "./canvas-caps";
import { withKeepalive } from "./canvas-handoff";
import type { CanvasInput } from "./canvas-types";

/** A read with no reply by then is taken as lost; a save is given this and more. */
export const REQUEST_TIMEOUT_MS = 30_000;
/** The pace a save is first assumed to go out at: 50 KiB a second, so 4 MB gets 80 seconds on top. */
export const UPLOAD_BYTES_PER_S = 50 * 1024;
/**
 * The most the time for a body grows by. A save that times out is sent whole again, so each one
 * doubles it: the tries cut short then cost less together than the one that gets through. At 8 the
 * pace is 6 KiB a second, a poor 2G link, and the largest canvas, 4 MB, has eleven and a half
 * minutes. Past that a silent request is more likely lost than slow, and waiting longer would only
 * put off saying so.
 */
export const MAX_STRETCH = 8;

/** Where a reply goes: the runner's `send`. */
type Send = (input: CanvasInput) => void;

/** How long a save may go unanswered: `ms`, and `firstMs`, what the same body is given when no
 *  save before it went unanswered. A message waits on a save no longer than that. */
export type SaveDeadline = { ms: number; firstMs: number };

const httpStatus = (error: unknown) => (error instanceof ApiError ? error.status : null);

/** How long a save whose body is `bytes` long may stay unanswered, when the `timeouts` saves
 *  before it, in a row, had no reply in time. Only the time for the body grows with them. */
export function saveDeadlineMs(bytes: number, timeouts = 0): number {
  const stretch = Math.min(2 ** timeouts, MAX_STRETCH);
  return REQUEST_TIMEOUT_MS + Math.ceil((bytes / UPLOAD_BYTES_PER_S) * 1000 * stretch);
}

/** Saves `content` over `baseVersion` and sends how it went; the answer is how long the reply may
 *  take, which `timeouts` stretches as `saveDeadlineMs` says, beside how long it would have had
 *  with none. A hidden page asks for `keepalive` so a closing page does not cut the request. */
export function requestSave(
  id: string,
  content: string,
  baseVersion: number,
  hidden: boolean,
  send: Send,
  timeouts = 0,
): SaveDeadline {
  const bytes = utf8Bytes(saveBody(content, baseVersion));
  const deadline = { ms: saveDeadlineMs(bytes, timeouts), firstMs: saveDeadlineMs(bytes) };
  const abort = new AbortController();
  let expired = false;
  const timer = setTimeout(() => {
    expired = true;
    abort.abort();
  }, deadline.ms);
  withKeepalive(hidden, content, baseVersion, (keepalive) =>
    artifactApi.save(id, content, baseVersion, { signal: abort.signal, keepalive }),
  ).then(
    (meta) => {
      clearTimeout(timer);
      send({ type: "saved", meta });
    },
    (error: unknown) => {
      clearTimeout(timer);
      if (expired) {
        send({ type: "saveTimedOut" });
        return;
      }
      const conflict = conflictOf(error);
      send({
        type: "saveFailed",
        status: httpStatus(error),
        conflict,
        full: storageFullOf(error),
        cap: sizeCapOf(error),
      });
    },
  );
  return deadline;
}

/** The saves of one canvas, one after the other: how many in a row had no reply in time, which
 *  gives the next one longer, and how long the last one sent may still go unanswered. */
export class SaveClock {
  private timeouts = 0;
  private sentAt = 0;
  private deadline: SaveDeadline = { ms: 0, firstMs: 0 };

  /** `requestSave`, given longer by the saves before it that had no reply in time. */
  send(id: string, content: string, baseVersion: number, hidden: boolean, send: Send): void {
    const heard = (input: CanvasInput) => {
      // Only a save that lands says the link carries one in time again.
      if (input.type === "saveTimedOut") this.timeouts++;
      else if (input.type === "saved") this.timeouts = 0;
      send(input);
    };
    this.sentAt = Date.now();
    this.deadline = requestSave(id, content, baseVersion, hidden, heard, this.timeouts);
  }

  /** What is left, in ms, of the last save's deadline: its own, or with `first` the one it would
   *  have had if no save before it had gone unanswered. Both run from when it went out. */
  leftMs(first: boolean): number {
    const { ms, firstMs } = this.deadline;
    return Math.max(0, this.sentAt + (first ? firstMs : ms) - Date.now());
  }
}

/** Reads the canvas and sends what came back. The controller cancels the read. */
export function requestRead(id: string, send: Send): AbortController {
  const reading = new AbortController();
  const timer = setTimeout(() => reading.abort(), REQUEST_TIMEOUT_MS);
  const landed = (input: CanvasInput) => {
    clearTimeout(timer);
    try {
      send(input);
    } catch (error) {
      // A reply the machine cannot take in leaves the canvas loading for good: it says it could
      // not be read, and offers to try again. Why is said in the console, the only place it shows.
      console.error("a canvas reply could not be taken in", error);
      send({ type: "readFailed", status: null });
    }
  };
  artifactApi.get(id, reading.signal).then(
    (detail) => landed({ type: "read", detail }),
    (error: unknown) => landed({ type: "readFailed", status: httpStatus(error) }),
  );
  return reading;
}
