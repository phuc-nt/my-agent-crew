/**
 * What a chip that names a canvas holds, wherever the thread draws one: the canvas by name, then a
 * button that opens it, or the word that it was deleted and nothing to open.
 *
 * The id and the name come from text an agent wrote, which may be old or wrong. The name is drawn
 * as text with what nobody would see of it written out, and the thread's own name for the canvas
 * wins once it knows one. The canvas is asked about once, so one the server does not have says so.
 *
 * It draws the inside only. What stands around it, a row of a list or a block of a reply, is the
 * caller's, and carries the `canvas-chip` class the parts are laid out by.
 */

import { useEffect } from "react";
import { vi } from "../../i18n/vi";
import { showHiddenChars } from "../../lib/hidden-chars";
import { Icon } from "../ui/icon";
import type { CanvasLinks } from "./canvas-card";

type Props = {
  id: string;
  /** The name the text gave the canvas, used until the thread knows one. */
  named?: string;
  /** The version the text says the canvas was left at. */
  version?: number;
  canvas: CanvasLinks;
};

export function CanvasChip({ id, named, version, canvas }: Props) {
  const { card } = vi.canvas;
  const { titleOf, isGone, verify, open } = canvas;
  const there = !isGone(id);

  useEffect(() => {
    verify(id);
  }, [id, verify]);

  const title = showHiddenChars(titleOf(id) || named || card.untitled);
  return (
    <>
      <Icon name="document" className="tool-icon" />
      <span className="canvas-chip-title">{title}</span>
      {there ? (
        <>
          {version !== undefined && <span className="muted">v{version}</span>}
          <button type="button" className="ghost" aria-label={card.openLabel(title)} onClick={() => open(id)}>
            {card.open}
          </button>
        </>
      ) : (
        <span className="muted">{vi.canvas.gone}</span>
      )}
    </>
  );
}
