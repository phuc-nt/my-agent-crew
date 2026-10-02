import { useId, useState } from "react";
import { vi } from "../../i18n/vi";
import { showHiddenChars } from "../../lib/hidden-chars";
import { CopyButton } from "../copy-button";

/**
 * The note that went to the agent with a message: the passage of the canvas the person had
 * selected, or what they changed in it since the agent last saw it. A chip under the message,
 * closed until it is pressed, because the note quotes a document and would bury the thread.
 *
 * The note is text the person did not type, and a canvas may hold what an agent copied from a
 * web page. So it is shown as text, with the characters that change how it reads written out
 * as marks, and Copy hands over the note exactly as the agent read it.
 */
export function CanvasNoteChip({ note }: { note: string }) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  return (
    <div className="canvas-note" data-testid="canvas-note">
      <button
        type="button"
        className="chip canvas-note-toggle"
        aria-expanded={open}
        aria-controls={open ? bodyId : undefined}
        onClick={() => setOpen((was) => !was)}
      >
        {vi.canvas.noteChip}
      </button>
      {open && (
        <div className="canvas-note-body" id={bodyId} data-testid="canvas-note-body">
          <pre className="canvas-note-text">{showHiddenChars(note)}</pre>
          <CopyButton text={note} label={vi.canvas.noteCopy} />
        </div>
      )}
    </div>
  );
}
