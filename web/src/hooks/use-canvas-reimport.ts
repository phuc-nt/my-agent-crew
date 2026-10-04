/**
 * Reading the open canvas's workspace file into it again, from its panel. What the person typed is
 * saved first, and the file is asked for on the version that holds it: a file that differs becomes
 * the next version, which the canvas then takes as it takes the stream's word of one. The request
 * is given as long as a read of the canvas is, then given up.
 *
 * What is said afterwards is chosen here by the status code alone. The server's own words may quote
 * a path, and a 409 carries the newest text: neither shows. It is said of the canvas as it was
 * then, so it is taken back once the canvas hears of a newer version.
 */

import { useState } from "react";
import { artifactApi, conflictHeadOf } from "../api/artifact-client";
import { ApiError } from "../api/client";
import { vi } from "../i18n/vi";
import { announceDeletion } from "../lib/artifact-events";
import { canvasReason } from "../lib/canvas-reasons";
import { REQUEST_TIMEOUT_MS } from "../lib/canvas-requests";
import type { CanvasState } from "../lib/canvas-types";
import type { CanvasController } from "./use-canvas";

/** What the last re-import came to: `info` when the file was read, `error` when it was not. */
export type ReimportNote = { tone: "info" | "error"; text: string };

/**
 * A note, the newest version its reply told of, and `upTo`, the newest version it still stands
 * for: null until the note is first drawn.
 */
type Said = { note: ReimportNote; named: number; upTo: number | null };

type Canvas = Pick<CanvasController, "imported" | "reload"> & { state: Pick<CanvasState, "seen"> };

/** Why the file was not read, where this route's refusal means something of its own. */
function refusal(error: unknown): string | null {
  const { source, reasons } = vi.canvas;
  // Given up on its deadline: nothing came back, which is not to say the connection was lost.
  if (error instanceof DOMException && error.name === "TimeoutError") return source.failed(reasons.server);
  const status = error instanceof ApiError ? error.status : null;
  if (status === 403) return source.outside;
  if (status === 409) return source.failed(reasons.conflict);
  if (status === 410) return source.missing;
  // A sentence here, the sizes on a refused save: the status alone says the file is too large.
  if (status === 413) return source.tooLarge;
  // The file cannot be read, is no plain file, or is not what a canvas of this kind holds.
  if (status === 422) return source.unfit;
  return null;
}

export function useCanvasReimport(artifactId: string, canvas: Canvas, flush: () => Promise<number | null>) {
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<Said | null>(null);
  const { seen } = canvas.state;
  // Fixed at the first draw, which knows every version the canvas heard of while the request was
  // out: the save before it, the version the file became, the one a failed save ran into.
  if (said !== null && said.upTo === null) setSaid({ ...said, upTo: Math.max(said.named, seen) });

  const reimport = async () => {
    const { source } = vi.canvas;
    const say = (tone: ReimportNote["tone"], text: string, named = 0) =>
      setSaid({ note: { tone, text }, named, upTo: null });
    setBusy(true);
    setSaid(null);
    try {
      const base = await flush();
      // A canvas that was never read stands on no version, and there is none to ask on.
      if (base === null || base < 1) {
        say("error", source.unsaved);
        return;
      }
      const { changed, artifact } = await artifactApi.reimport(artifactId, base, AbortSignal.timeout(REQUEST_TIMEOUT_MS));
      // Told either way: a file that holds what the newest version does may still name a version
      // the canvas has not read.
      canvas.imported(artifact);
      say("info", changed ? source.changed(artifact.head_version) : source.unchanged);
    } catch (error) {
      const status = error instanceof ApiError ? error.status : null;
      if (status === 404) {
        announceDeletion(artifactId);
        return;
      }
      // Something was saved since the version the request named: the canvas reads it, and what
      // is said here is said of that one.
      if (status === 409) canvas.reload();
      say("error", refusal(error) ?? source.failed(canvasReason(error)), conflictHeadOf(error) ?? 0);
    } finally {
      setBusy(false);
    }
  };

  const stands = said !== null && (said.upTo === null || seen <= said.upTo);
  return { reimport, busy, note: stands ? said.note : null };
}
