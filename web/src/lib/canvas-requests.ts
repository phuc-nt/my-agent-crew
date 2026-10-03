/**
 * The two requests a canvas runner makes, each turning its reply into a machine input.
 *
 * A read with no reply in 30 seconds counts as lost and is retried instead of holding the canvas
 * forever. A save gets the same 30 seconds plus what its body needs at a slow link's pace, so a
 * large canvas on a poor connection is not cut off while it is still going out; one that outlasts
 * even that is reported as too slow, not as lost.
 */

import { artifactApi, conflictOf, saveBody, sizeCapOf, storageFullOf } from "../api/artifact-client";
import { ApiError } from "../api/client";
import { utf8Bytes } from "./canvas-caps";
import { withKeepalive } from "./canvas-handoff";
import type { CanvasInput } from "./canvas-types";

/** A read with no reply by then is taken as lost; a save is given this and more. */
export const REQUEST_TIMEOUT_MS = 30_000;
/** The pace a save is assumed to go out at: 50 KiB a second, so 4 MB gets 80 seconds on top. */
export const UPLOAD_BYTES_PER_S = 50 * 1024;

/** Where a reply goes: the runner's `send`. */
type Send = (input: CanvasInput) => void;

const httpStatus = (error: unknown) => (error instanceof ApiError ? error.status : null);

/** How long a save whose body is `bytes` long may stay unanswered. */
export function saveDeadlineMs(bytes: number): number {
  return REQUEST_TIMEOUT_MS + Math.ceil((bytes / UPLOAD_BYTES_PER_S) * 1000);
}

/** Saves `content` over `baseVersion` and sends how it went; the answer is how long the reply may
 *  take. A hidden page asks for `keepalive` so a closing page does not cut the request. */
export function requestSave(id: string, content: string, baseVersion: number, hidden: boolean, send: Send): number {
  const deadline = saveDeadlineMs(utf8Bytes(saveBody(content, baseVersion)));
  const abort = new AbortController();
  let expired = false;
  const timer = setTimeout(() => {
    expired = true;
    abort.abort();
  }, deadline);
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

/** Reads the canvas and sends what came back. The controller cancels the read. */
export function requestRead(id: string, send: Send): AbortController {
  const reading = new AbortController();
  const timer = setTimeout(() => reading.abort(), REQUEST_TIMEOUT_MS);
  const landed = (input: CanvasInput) => {
    clearTimeout(timer);
    send(input);
  };
  artifactApi.get(id, reading.signal).then(
    (detail) => landed({ type: "read", detail }),
    (error: unknown) => landed({ type: "readFailed", status: httpStatus(error) }),
  );
  return reading;
}
