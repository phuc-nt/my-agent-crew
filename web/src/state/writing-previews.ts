import type { AgentEvent, ToolCall } from "../api/types";

export type ToolCallDelta = Extract<AgentEvent, { type: "tool_call_delta" }>;

/**
 * The arguments of one canvas write as far as the model has written them.
 *
 * `key` is its own in the tab and never used twice, so what shows it can tell one from the
 * next. `index` is where the call stands in the model's answer. `callId` is null until the
 * step's answer names the call, and from then on the preview belongs to that call.
 */
export type WritingPreview = {
  key: number;
  index: number;
  name: string;
  text: string;
  attempt: number;
  callId: string | null;
  updates: number;
};

/**
 * The previews after one more piece of a call, and the last key given out.
 *
 * A piece from another try than the one a preview was written in means the model started its
 * answer over: what it had written is not coming back, so every preview still without a call
 * goes. A step counts its tries from nothing again, so the try tells two answers of one step
 * apart and never two steps: a preview that has its call is another step's, and stays.
 * An event that names no tool only says the answer was started over.
 */
export function applyDelta(
  previews: WritingPreview[],
  seq: number,
  event: ToolCallDelta,
): { previews: WritingPreview[]; seq: number } {
  const stale = previews.some((p) => p.callId === null && p.attempt !== event.attempt);
  const kept = stale ? previews.filter((p) => p.callId !== null) : previews;
  if (event.name === "") return { previews: kept, seq };
  const at = kept.findIndex((p) => p.callId === null && p.index === event.index);
  if (at === -1) {
    const started: WritingPreview = {
      key: seq + 1,
      index: event.index,
      name: event.name,
      text: event.chunk,
      attempt: event.attempt,
      callId: null,
      updates: 1,
    };
    return { previews: [...kept, started], seq: seq + 1 };
  }
  const was = kept[at];
  const next = [...kept];
  next[at] = { ...was, name: event.name, text: was.text + event.chunk, updates: was.updates + 1 };
  return { previews: next, seq };
}

/**
 * The previews once a step's answer is in, each given the call it was a preview of.
 *
 * The pieces carry where a call stands and what the model named it while writing; the answer
 * says what the call is. A preview stays only when the call standing in its place is the same
 * tool: one whose call turned out to be another tool was never a canvas, and what it had read
 * of that call's arguments goes with it. Previews that already had a call are the step
 * before's, and that step has been answered.
 */
export function bindCalls(previews: WritingPreview[], toolCalls: ToolCall[]): WritingPreview[] {
  if (previews.length === 0) return previews;
  const bound: WritingPreview[] = [];
  for (const preview of previews) {
    if (preview.callId !== null) continue;
    const call = toolCalls[preview.index];
    if (call?.name === preview.name) bound.push({ ...preview, callId: call.id });
  }
  return bound;
}
