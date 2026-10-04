/**
 * Reading the open canvas's workspace file into it again, from its panel. What the person typed is
 * saved first, and the file is asked for on the version that holds it: a file that differs becomes
 * the next version, which the canvas then takes as it takes the stream's word of one.
 *
 * What is said afterwards is chosen here by the status code alone. The server's own words may quote
 * a path, and a 409 carries the newest text: neither shows.
 */

import { useState } from "react";
import { artifactApi } from "../api/artifact-client";
import { ApiError } from "../api/client";
import { vi } from "../i18n/vi";
import { announceDeletion } from "../lib/artifact-events";
import { canvasReason } from "../lib/canvas-reasons";
import type { CanvasController } from "./use-canvas";

/** What the last re-import came to: `info` when the file was read, `error` when it was not. */
export type ReimportNote = { tone: "info" | "error"; text: string };

/** Why the file was not read, where this route's refusal means something of its own. */
function refusal(status: number | null): string | null {
  const { source, reasons } = vi.canvas;
  if (status === 403) return source.outside;
  if (status === 409) return source.failed(reasons.conflict);
  if (status === 410) return source.missing;
  // A sentence here, the sizes on a refused save: the status alone says the file is too large.
  if (status === 413) return source.tooLarge;
  if (status === 422) return source.unfit;
  return null;
}

export function useCanvasReimport(
  artifactId: string,
  canvas: Pick<CanvasController, "imported" | "reload">,
  flush: () => Promise<number | null>,
) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<ReimportNote | null>(null);

  const reimport = async () => {
    const { source } = vi.canvas;
    setBusy(true);
    setNote(null);
    try {
      const base = await flush();
      if (base === null) {
        setNote({ tone: "error", text: source.unsaved });
        return;
      }
      const { changed, artifact } = await artifactApi.reimport(artifactId, base);
      // Told either way: a file that holds what the newest version does may still name a version
      // the canvas has not read.
      canvas.imported(artifact);
      setNote({ tone: "info", text: changed ? source.changed(artifact.head_version) : source.unchanged });
    } catch (error) {
      const status = error instanceof ApiError ? error.status : null;
      if (status === 404) {
        announceDeletion(artifactId);
        return;
      }
      // Something was saved since the version the request named: the canvas reads it.
      if (status === 409) canvas.reload();
      setNote({ tone: "error", text: refusal(status) ?? source.failed(canvasReason(error)) });
    } finally {
      setBusy(false);
    }
  };

  return { reimport, busy, note };
}
