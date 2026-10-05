/**
 * A line of a reply that sends a canvas (`FILE: artifact:<id>`), drawn in the reply as the canvas
 * it names, with a button that opens it. The same line makes the chat send the canvas as a file;
 * here a link to download it would point at a file the workspace does not have.
 *
 * Where the thread is given nothing to open a canvas with, the line stays the text it was.
 */

import type { CanvasLinks } from "./canvas-card";
import { CanvasChip } from "./canvas-chip";

type Props = {
  /** The canvas the line names; "" when it names none the server could have made. */
  id: string;
  /** The line as the reply has it. */
  line: string;
  canvas?: CanvasLinks;
};

export function CanvasRefChip({ id, line, canvas }: Props) {
  if (!canvas) return <p>{line}</p>;
  return (
    <div className="canvas-chip canvas-ref" data-testid="canvas-ref">
      <CanvasChip id={id} canvas={canvas} />
    </div>
  );
}
