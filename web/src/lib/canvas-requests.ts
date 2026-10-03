/**
 * The two requests a canvas runner makes, each turning its reply into a machine input.
 *
 * Every request gives up after 30 seconds, so a reply that never comes counts as lost and is
 * retried instead of holding the save forever.
 */

import { artifactApi, conflictOf, storageFullOf } from "../api/artifact-client";
import { ApiError } from "../api/client";
import { withKeepalive } from "./canvas-handoff";
import type { CanvasInput } from "./canvas-types";

/** A request with no reply by then is taken as lost. */
export const REQUEST_TIMEOUT_MS = 30_000;

/** Where a reply goes: the runner's `send`. */
type Send = (input: CanvasInput) => void;

const httpStatus = (error: unknown) => (error instanceof ApiError ? error.status : null);

/** Saves `content` over `baseVersion` and sends how it went. A hidden page asks for `keepalive`
 *  so a closing page does not cut the request. */
export function requestSave(id: string, content: string, baseVersion: number, hidden: boolean, send: Send): void {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), REQUEST_TIMEOUT_MS);
  withKeepalive(hidden, content, baseVersion, (keepalive) =>
    artifactApi.save(id, content, baseVersion, { signal: abort.signal, keepalive }),
  ).then(
    (meta) => {
      clearTimeout(timer);
      send({ type: "saved", meta });
    },
    (error: unknown) => {
      clearTimeout(timer);
      const conflict = conflictOf(error);
      send({ type: "saveFailed", status: httpStatus(error), conflict, full: storageFullOf(error) });
    },
  );
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
