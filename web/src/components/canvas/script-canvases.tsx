/**
 * The canvases a script wrote, each drawn under the script's card as a write the agent made itself
 * is drawn: the canvas by name, what was done to it and to which version, and a button that opens it.
 *
 * A script's calls are listed folded inside its card, and on a narrow screen no canvas opens by
 * itself, so without these a canvas a script made could be reached only through the list of the
 * conversation's canvases. Which calls get a card is asked of each as it is asked of a direct call
 * (`isCanvasWrite`): a write that failed gets none and stays a row of the list, which says why.
 *
 * A script's call is heard of only once it has ended, so none of these is ever still writing; and
 * a script that failed after it wrote keeps the cards of what it wrote, since those canvases exist.
 */

import type { ThreadItem } from "../../state/thread-reducer";
import { CanvasCard, type CanvasLinks, isCanvasWrite } from "./canvas-card";

type ToolItem = Extract<ThreadItem, { kind: "tool" }>;

/** The calls a script made, each as the thread holds a call the agent made itself. A script may
 *  make the very same call twice, so a call's place among them is part of what it is. */
function nestedItems(script: ToolItem): ToolItem[] {
  return (script.calls ?? []).map((call, index) => ({
    kind: "tool",
    id: `${script.id}:${index}`,
    name: call.name,
    arguments: call.arguments,
    output: call.output,
    status: call.ok ? "done" : "failed",
  }));
}

export function ScriptCanvases({ item, canvas }: { item: ToolItem; canvas: CanvasLinks }) {
  return (
    <>
      {nestedItems(item)
        .filter(isCanvasWrite)
        .map((write) => (
          <CanvasCard key={write.id} item={write} canvas={canvas} />
        ))}
    </>
  );
}
