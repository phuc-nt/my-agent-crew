/**
 * The open canvas's autosave and sync, as a pure function of its state and one input.
 *
 * `CanvasRunner` feeds it keystrokes, timers, replies and stream events, and runs the effects it
 * returns: a save, a read, a retry timer, a draft to drop, a `flush()` to answer. Nothing the
 * person typed is lost on the way: a save that cannot go out leaves the text unsaved and says why,
 * and a newer version never replaces text that is not on the server.
 */

import { fits } from "./canvas-caps";
import { apply409, flush, saveDue, saved, saveFailed, saveTimedOut, send } from "./canvas-save";
import {
  clearStop,
  editsBetween,
  isDirty,
  moveBase,
  readIfWanted,
  replaceText,
  requestRead,
  settleAll,
  takeSummary,
} from "./canvas-state";
import { event, read, readFailed, resync } from "./canvas-sync";
import type { CanvasEffect, CanvasInput, CanvasState } from "./canvas-types";

export { openState, statusOf } from "./canvas-state";
export type { CanvasEffect, CanvasInput, CanvasState, CanvasStatus } from "./canvas-types";

export function step(previous: CanvasState, input: CanvasInput): { state: CanvasState; effects: CanvasEffect[] } {
  const state = { ...previous };
  const effects: CanvasEffect[] = [];
  apply(state, effects, input);
  // A stop is about text that could not be saved; once nothing is unsaved there is nothing to stop.
  if (state.stop && !isDirty(state)) clearStop(state);
  return { state, effects };
}

function apply(state: CanvasState, effects: CanvasEffect[], input: CanvasInput): void {
  switch (input.type) {
    case "edit":
      return edit(state, input.text);
    case "saveDue":
      return saveDue(state, effects, input.reason);
    case "flush":
      return flush(state, effects, input.ticket);
    case "saved":
      return saved(state, effects, input.meta);
    case "saveFailed":
      return saveFailed(state, effects, input);
    case "saveTimedOut":
      return saveTimedOut(state, effects);
    case "event":
      return event(state, effects, input.artifact);
    case "read":
      return read(state, effects, input.detail);
    case "readFailed":
      return readFailed(state, effects, input.status);
    case "resync":
      return resync(state, effects);
    case "keepMine":
      return keepMine(state, effects);
    case "loadTheirs":
      return loadTheirs(state, effects);
    case "undo":
      if (state.undo !== null) edit(state, state.undo);
      return;
    case "restored":
      return restored(state, effects, input.version, input.content);
    case "composition":
      return composition(state, effects, input.composing);
    case "visibility":
      state.hidden = input.hidden;
      return;
    case "renamed":
      if (input.summary.id === state.id) takeSummary(state, input.summary);
      return;
  }
}

function edit(state: CanvasState, text: string): void {
  if (state.phase !== "ready" || state.gone || text === state.text) return;
  state.text = text;
  state.gen++;
  state.undo = null;
  if (state.stop === "tooLarge" && fits(text, state.summary?.kind)) clearStop(state);
}

/** "Giữ bản của tôi": the person's text goes on top of the newer version. */
function keepMine(state: CanvasState, effects: CanvasEffect[]): void {
  const conflict = state.conflict;
  if (!conflict) return;
  moveBase(state, conflict.theirs);
  state.conflict = null;
  if (isDirty(state)) send(state, effects);
}

/** "Nạp bản mới": the newer version replaces the person's text, which "Hoàn tác" can bring back. */
function loadTheirs(state: CanvasState, effects: CanvasEffect[]): void {
  const conflict = state.conflict;
  if (!conflict) return;
  const mine = state.text;
  replaceText(state, conflict.theirs.content, editsBetween(mine, conflict.theirs.content));
  moveBase(state, conflict.theirs);
  state.conflict = null;
  state.undo = mine;
  effects.push({ type: "dropDraft" });
}

/** A restore went through: its version is the text and the base, without waiting for the stream. */
function restored(state: CanvasState, effects: CanvasEffect[], version: number, content: string): void {
  if (state.phase !== "ready" || state.gone || version < state.base.version) return;
  replaceText(state, content, editsBetween(state.text, content));
  state.base = { version, content, author: "user" };
  state.unsure = [];
  state.conflict = null;
  state.held = null;
  clearStop(state);
  state.seen = Math.max(state.seen, version);
  effects.push({ type: "dropDraft" });
  settleAll(state, effects, version);
}

function composition(state: CanvasState, effects: CanvasEffect[], composing: boolean): void {
  state.composing = composing;
  if (composing) return;
  const held = state.held;
  if (held) {
    state.held = null;
    apply409(state, effects, held.conflict, held.sent);
    readIfWanted(state, effects);
  } else if (state.phase === "ready" && !state.conflict && !isDirty(state) && state.seen > state.base.version) {
    requestRead(state, effects);
  }
}
