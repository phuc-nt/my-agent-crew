/**
 * Two versions that could not be merged. The person's text stays in the editor, and the bar offers
 * keeping it over the server's or loading the server's, with the difference on request. After
 * "Nạp bản mới" the person's text can be taken back until they type. A 409's content shows nowhere
 * but here.
 */

import { useMemo, useState } from "react";
import type { CanvasController } from "../../hooks/use-canvas";
import { vi } from "../../i18n/vi";
import { authorLabel } from "../../lib/canvas-author";
import { canvasDiff } from "../../lib/canvas-diff";
import { CanvasDiffView } from "../diff-view";

type Props = { canvas: CanvasController; agentName(id: string): string };

export function CanvasConflict({ canvas, agentName }: Props) {
  const { conflict, undo, text } = canvas.state;
  const [showing, setShowing] = useState(false);
  const theirs = conflict?.theirs ?? null;
  const lines = useMemo(() => (showing && theirs ? canvasDiff(theirs.content, text) : null), [showing, theirs, text]);

  if (theirs) {
    return (
      <div className="notice warn canvas-conflict" role="alert">
        <p>{vi.canvas.conflictBy(authorLabel(theirs.author, agentName), theirs.version)}</p>
        <div className="canvas-conflict-actions">
          <button type="button" className="primary" onClick={canvas.keepMine}>
            {vi.canvas.keepMine}
          </button>
          <button type="button" onClick={canvas.loadTheirs}>
            {vi.canvas.loadTheirs}
          </button>
          <button type="button" className="link-button" aria-expanded={showing} onClick={() => setShowing(!showing)}>
            {showing ? vi.canvas.hideDiff : vi.canvas.showDiff}
          </button>
        </div>
        {showing && <CanvasDiffView lines={lines} />}
      </div>
    );
  }
  if (undo !== null) {
    return (
      <div className="notice canvas-notice info" role="status">
        <span>{vi.canvas.undoHint}</span>
        <button type="button" className="link-button" onClick={canvas.undo}>
          {vi.canvas.undoLoad}
        </button>
      </div>
    );
  }
  return null;
}
