/** What the canvas dock shows outside its own column: the button that opens it, and what its
 *  canvases have to say above the thread or the canvas section. */

import type { RefObject } from "react";
import type { CanvasDock } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import { Icon } from "../ui/icon";

/** The way to the conversation's canvases, counted on the way; focus comes back here on closing. */
export function CanvasButton({ dock, ref }: { dock: CanvasDock; ref: RefObject<HTMLButtonElement | null> }) {
  const count = dock.list.items?.length ?? 0;
  return (
    <button
      type="button"
      className="pill canvas-button"
      ref={ref}
      aria-label={vi.canvas.buttonLabel(count)}
      aria-expanded={dock.view !== "closed"}
      onClick={() => void dock.toggle()}
    >
      <Icon name="document" />
      {vi.canvas.button}
      {count > 0 && <span className="badge"> {count}</span>}
    </button>
  );
}

/** What the canvases have to say in the chat: the saves handed off as the person moved on that
 *  did not land, and that the last message went before the canvas it names was saved. */
export function CanvasChatNotices({ dock }: { dock: CanvasDock }) {
  return (
    <>
      {dock.handoffs.map((failure) => (
        <div key={failure.id} className="notice error canvas-notice" role="alert">
          <Icon name="alert" />
          <span>{vi.canvas.handoffFailed(failure.title || vi.canvas.untitled, failure.draft)}</span>
          <button type="button" className="link-button" onClick={() => dock.dismissHandoff(failure.id)}>
            {vi.canvas.dismiss}
          </button>
        </div>
      ))}
      {dock.sentUnsaved && (
        <div className="notice warn canvas-notice" role="status">
          <Icon name="info" />
          <span>{vi.canvas.sentUnsaved}</span>
          <button type="button" className="link-button" onClick={() => dock.noteSentUnsaved(false)}>
            {vi.canvas.dismiss}
          </button>
        </div>
      )}
    </>
  );
}
