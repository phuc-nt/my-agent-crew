/**
 * A line of a reply that sends a canvas (`FILE: artifact:<id>`), drawn in the reply as the canvas
 * it names, with a button that opens it. The same line makes the chat send the canvas as a file;
 * here a link to download it would point at a file the workspace does not have.
 *
 * Where the thread is given nothing to open a canvas with, the line stays the text it was. So does
 * a line whose id is not one canvas's id (`artifact:<id>.md`, an id with a full stop after it): the
 * canvas it meant may well be there, so it is not drawn as one that was deleted, and no canvas is
 * guessed from it.
 */

import type { CanvasLinks } from "./canvas-card";
import { CanvasChip } from "./canvas-chip";

type Props = {
  /** The canvas the line names; "" when what it names is not one canvas's id. */
  id: string;
  /** The line as the reply has it. */
  line: string;
  canvas?: CanvasLinks;
};

export function CanvasRefChip({ id, line, canvas }: Props) {
  if (!canvas || id === "") return <p>{line}</p>;
  return (
    <div className="canvas-chip canvas-ref" data-testid="canvas-ref">
      <CanvasChip id={id} canvas={canvas} />
    </div>
  );
}
