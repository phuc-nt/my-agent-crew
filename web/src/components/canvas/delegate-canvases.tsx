/**
 * The canvases a handed-off task wrote, under the line of its card that says how it went: each by
 * name, at the version the other agent left it, with a button that opens it.
 *
 * The names and ids come from the result, which is that agent's wording and may be an old result
 * read wrong: a name is drawn as text with what nobody would see of it written out, and every
 * canvas is asked about once, so one the server does not have says it was deleted and offers
 * nothing to open. The thread's own name for a canvas wins once it knows one.
 */

import { useEffect } from "react";
import { vi } from "../../i18n/vi";
import type { DelegateCanvas } from "../../lib/delegate-result";
import { showHiddenChars } from "../../lib/hidden-chars";
import { Icon } from "../ui/icon";
import type { CanvasLinks } from "./canvas-card";

type Props = { canvases: DelegateCanvas[]; canvas: CanvasLinks };

export function DelegateCanvases({ canvases, canvas }: Props) {
  if (canvases.length === 0) return null;
  return (
    <ul className="delegate-canvases" aria-label={vi.canvas.delegateCanvases}>
      {canvases.map((written, at) => (
        // A result may name one canvas twice, so its place in the list is part of what it is.
        <Chip key={`${at}:${written.id}`} written={written} canvas={canvas} />
      ))}
    </ul>
  );
}

function Chip({ written, canvas }: { written: DelegateCanvas; canvas: CanvasLinks }) {
  const { card } = vi.canvas;
  const { titleOf, isGone, verify, open } = canvas;
  const { id } = written;

  useEffect(() => verify(id), [id, verify]);

  const title = showHiddenChars(titleOf(id) || written.title || card.untitled);
  return (
    <li className="delegate-canvas" data-testid="delegate-canvas">
      <Icon name="document" className="tool-icon" />
      <span className="delegate-canvas-title">{title}</span>
      {isGone(id) ? (
        <span className="muted">{vi.canvas.gone}</span>
      ) : (
        <>
          <span className="muted">v{written.version}</span>
          <button type="button" className="ghost" aria-label={card.openLabel(title)} onClick={() => open(id)}>
            {card.open}
          </button>
        </>
      )}
    </li>
  );
}
