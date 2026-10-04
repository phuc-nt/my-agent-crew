/**
 * What the thread reads from the arguments of a canvas tool call. They are whatever the model
 * sent, and a call saved by an older version holds them as one line of text: anything but a
 * mapping has no arguments to read.
 */

import { isBlank } from "./canvas-title";

export const IMPORT = "artifact_import";

type Call = { name: string; arguments: unknown };

/** One argument of a call; undefined when the call has no mapping to read it from. */
export function argument(call: Pick<Call, "arguments">, key: string): unknown {
  const args = call.arguments;
  return typeof args === "object" && args !== null ? (args as Record<string, unknown>)[key] : undefined;
}

/** An import that names a canvas reads its file into that one; an import that names none makes a
 *  canvas. The server takes an `id` sent blank for one left out, so a blank one names none here. */
export function importsInto(call: Call): boolean {
  const id = argument(call, "id");
  return call.name === IMPORT && typeof id === "string" && !isBlank(id);
}

/** The name of the file an import reads, the last part of its path; null when the call names none.
 *  A path blank as a whole names none, and the server refuses it; a part made of spaces is a name. */
export function importedFile(call: Call): string | null {
  const path = argument(call, "path");
  if (call.name !== IMPORT || typeof path !== "string" || isBlank(path)) return null;
  return path.split("/").findLast((part) => part !== "") ?? null;
}
