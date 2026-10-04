/**
 * Renaming the open canvas from its panel. The server's answer goes to the canvas; a canvas that is
 * gone is told to everything that shows it, and any other refusal is kept as the reason to show.
 */

import { useState } from "react";
import { artifactApi } from "../api/artifact-client";
import { ApiError } from "../api/client";
import { vi } from "../i18n/vi";
import { announceDeletion } from "../lib/artifact-events";
import { canvasReason } from "../lib/canvas-reasons";
import type { CanvasController } from "./use-canvas";

export function useCanvasRename(artifactId: string, canvas: CanvasController) {
  const [renameError, setRenameError] = useState<string | null>(null);

  const rename = async (title: string) => {
    setRenameError(null);
    try {
      canvas.renamed(await artifactApi.rename(artifactId, title));
    } catch (error) {
      const status = error instanceof ApiError ? error.status : null;
      if (status === 404) announceDeletion(artifactId);
      else setRenameError(status === 422 ? vi.canvas.reasons.title : canvasReason(error));
    }
  };

  return { rename, renameError };
}
