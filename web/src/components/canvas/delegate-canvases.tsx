/**
 * The canvases a handed-off task wrote, under the line of its card that says how it went: each by
 * name, at the version the other agent left it, with a button that opens it.
 *
 * The names and ids come from the result, which is that agent's wording and may be an old result
 * read wrong. Each is drawn by `CanvasChip`, which is where a name is made safe to show and a
 * canvas the server does not have is said to be deleted.
 */

import { vi } from "../../i18n/vi";
import type { DelegateCanvas } from "../../lib/delegate-result";
import type { CanvasLinks } from "./canvas-card";
import { CanvasChip } from "./canvas-chip";

type Props = { canvases: DelegateCanvas[]; canvas: CanvasLinks };

export function DelegateCanvases({ canvases, canvas }: Props) {
  if (canvases.length === 0) return null;
  return (
    <ul className="delegate-canvases" aria-label={vi.canvas.delegateCanvases}>
      {canvases.map((written, at) => (
        // A result may name one canvas twice, so its place in the list is part of what it is.
        <li key={`${at}:${written.id}`} className="canvas-chip delegate-canvas" data-testid="delegate-canvas">
          <CanvasChip id={written.id} named={written.title} version={written.version} canvas={canvas} />
        </li>
      ))}
    </ul>
  );
}
