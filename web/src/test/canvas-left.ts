import type { saveInBackground } from "../lib/canvas-handoff";
import { openState } from "../lib/canvas-machine";

/** What `saveInBackground` takes of a canvas left behind. */
export type LeftCanvas = Parameters<typeof saveInBackground>[0];

/** Canvas `id` as its runner leaves it: no summary, this device kept its draft and no save is in
 *  flight, unless `over` says otherwise. */
export function leftCanvas(id: string, flush: LeftCanvas["flush"], over: Partial<LeftCanvas> = {}): LeftCanvas {
  return { id, state: openState(id, null), flush, draftFailed: false, waitMs: () => 0, ...over };
}
