/**
 * Opens the canvas an agent has just made beside the thread, so the person sees it grow without
 * asking. It opens quietly: the keyboard stays where it is and nothing is written to the server.
 *
 * Only a canvas this tab watched being made opens. The screen may be drawn with calls already in
 * the thread, and a conversation read from the server brings its calls with it: neither is news.
 * Each call is judged once, as it ends: when the person is typing in a canvas, or the screen is
 * too narrow to hold one beside the thread, that canvas never opens by itself, however things
 * change afterwards. Edits and rewrites never open one, for the canvas may not be the one the
 * person is reading; neither does a call that failed or was refused. The card in the thread still
 * opens any of them on request.
 *
 * A file read into a canvas makes one when the call names none, and that canvas opens as any made
 * does. Read into a canvas the call names it is a rewrite, and a file that left its canvas as it
 * was made nothing: neither opens.
 *
 * A task handed to another agent opens the first canvas its result says that agent wrote, made
 * or only changed: the result does not say which, and the person asked for the work either way.
 * Of two tasks handed off side by side, the one to finish last is the one left open.
 */

import { useEffect, useRef, useState } from "react";
import { parseArtifactTag } from "../lib/artifact-tag";
import { IMPORT, importsInto } from "../lib/canvas-import-call";
import { parseDelegateResult } from "../lib/delegate-result";
import type { ThreadItem } from "../state/thread-reducer";
import type { CanvasDock } from "./use-canvas-dock";

type Thread = {
  state: { items: ThreadItem[] };
  /** The conversation as the server last gave it, whose calls are history. */
  detail: { messages: { tool_calls: { id: string }[] }[] } | null;
};

type Tool = Extract<ThreadItem, { kind: "tool" }>;

const toolIds = (items: ThreadItem[]) => items.flatMap((item) => (item.kind === "tool" ? [item.id] : []));

/** The canvas a finished call leaves to show: the one it made, or the first a handed-off task wrote. */
function shows(item: Tool): string | null {
  if (item.name === "delegate") return (item.output ? parseDelegateResult(item.output) : null)?.canvases[0]?.id ?? null;
  const makes = item.name === "artifact_create" || (item.name === IMPORT && !importsInto(item));
  const tag = makes ? parseArtifactTag(item.output) : null;
  return tag === null || tag.unchanged ? null : tag.id;
}

export function useCanvasAutoOpen(thread: Thread, dock: Pick<CanvasDock, "open" | "typing">, wide: boolean): void {
  const { items } = thread.state;
  // The calls the screen was drawn with, then each call once it has been judged.
  const [judged] = useState(() => new Set(toolIds(items)));
  const latest = useRef({ dock, wide, detail: thread.detail });
  latest.current = { dock, wide, detail: thread.detail };

  useEffect(() => {
    const { dock, wide, detail } = latest.current;
    for (const item of items) {
      if (item.kind !== "tool" || judged.has(item.id)) continue;
      // A call that has not ended is judged when it does.
      if (item.status === "running" || item.status === "awaiting") continue;
      judged.add(item.id);
      const id = item.status === "done" ? shows(item) : null;
      const history = detail?.messages.some((message) => message.tool_calls.some((call) => call.id === item.id));
      if (id === null || !wide || history || dock.typing()) continue;
      dock.open(id, { quiet: true });
    }
  }, [items, judged]);
}
