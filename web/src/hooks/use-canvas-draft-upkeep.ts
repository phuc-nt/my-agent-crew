import { useEffect } from "react";
import { onArtifactEvent } from "../lib/artifact-events";
import { clearDraft, pruneDrafts } from "../lib/canvas-draft";

/** Keeps this device's canvas drafts from outliving what they were drafts of. */
export function useCanvasDraftUpkeep(): void {
  // Canvas drafts are otherwise thinned only as a new one is written; a month-old draft of a
  // canvas nobody reopened would stay on the device for good.
  useEffect(() => pruneDrafts(Date.now()), []);
  // A deleted canvas has no version left to save into: its draft goes, and with it the question the
  // page asks before closing over a draft only this tab holds.
  useEffect(
    () =>
      onArtifactEvent(({ artifact }) => {
        if ("deleted" in artifact) clearDraft(artifact.id);
      }),
    [],
  );
}
