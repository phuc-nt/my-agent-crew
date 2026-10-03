/**
 * Saving a canvas: when a save goes out, and what each reply makes of the person's text.
 *
 * One save is in flight at a time and carries the whole text with the version it was edited
 * from. A reply that is lost leaves the server's state unknown, so the text it carried is kept as
 * "unsure" until a version shows whether it landed. A 409 is merged when the two sides changed
 * different lines and becomes a conflict for the person when they did not.
 */

import type { ArtifactConflict, ArtifactVersionMeta } from "../api/artifact-types";
import { capOf, fits } from "./canvas-caps";
import {
  clearStop,
  goGone,
  isDirty,
  moveBase,
  readIfWanted,
  replaceText,
  requestRead,
  settleAll,
  settleUpTo,
} from "./canvas-state";
import {
  type CanvasEffect,
  type CanvasInput,
  type CanvasState,
  RETRY_DELAYS_MS,
  type SaveReason,
  type Stop,
  UNSURE_KEEP,
} from "./canvas-types";
import { merge3 } from "./merge3";

type Sent = { gen: number; content: string };
type SaveFailure = Extract<CanvasInput, { type: "saveFailed" }>;

/** A save fell due for `reason`; it goes out unless something holds it back. */
export function saveDue(state: CanvasState, effects: CanvasEffect[], reason: SaveReason): void {
  if (state.phase !== "ready" || state.gone || state.conflict) return;
  if (state.stop) {
    // Only the person asking again lifts a stop; the timer would only be refused again.
    if (reason !== "manual") return;
    clearStop(state);
  }
  // While a retry waits, typing does not shorten the wait; the retry sends the newest text.
  if (state.retrying ? reason === "timer" || reason === "blur" : reason === "retry") return;
  if (state.saving || state.held) {
    state.pending = true;
    return;
  }
  if (!isDirty(state)) {
    settleAll(state, effects, state.base.version);
    state.failures = 0;
    state.retrying = false;
    if (state.seen > state.base.version) requestRead(state, effects);
    return;
  }
  send(state, effects);
}

/** Sends the text on its base, or stops when it is over the size cap of its kind. */
export function send(state: CanvasState, effects: CanvasEffect[]): void {
  const kind = state.summary?.kind;
  if (!fits(state.text, kind)) {
    stopSaving(state, effects, "tooLarge", capOf(kind));
    return;
  }
  state.saving = { gen: state.gen, content: state.text, baseVersion: state.base.version };
  state.pending = false;
  state.retrying = false;
  effects.push({ type: "put", content: state.text, baseVersion: state.base.version, hidden: state.hidden });
}

/** `flush()` was called: it settles once a version holds the text as it is now. */
export function flush(state: CanvasState, effects: CanvasEffect[], ticket: number): void {
  if (state.phase !== "ready") {
    effects.push({ type: "settle", ticket, version: state.base.version });
    return;
  }
  if (state.gone || state.conflict || state.stop) {
    effects.push({ type: "settle", ticket, version: null });
    return;
  }
  state.waiters = [...state.waiters, { ticket, gen: state.gen }];
  saveDue(state, effects, "flush");
}

export function saved(state: CanvasState, effects: CanvasEffect[], meta: ArtifactVersionMeta): void {
  const sent = state.saving;
  if (state.gone || !sent) return;
  state.saving = null;
  state.failures = 0;
  state.retrying = false;
  moveBase(state, { version: meta.version, content: sent.content, author: meta.author });
  state.seen = Math.max(state.seen, meta.version);
  effects.push({ type: "dropDraft", text: sent.content });
  if (isDirty(state)) settleUpTo(state, effects, sent.gen, meta.version);
  else settleAll(state, effects, state.base.version);
  if (state.seen > state.base.version) {
    // Someone wrote while the save was out: unsaved text goes on top of it through a 409, and
    // text with nothing unsaved reads it.
    if (isDirty(state)) send(state, effects);
    else state.readWanted = true;
  } else if (isDirty(state) && state.pending) send(state, effects);
  state.pending = false;
  readIfWanted(state, effects);
}

export function saveFailed(state: CanvasState, effects: CanvasEffect[], failure: SaveFailure): void {
  const { status, conflict, full, cap } = failure;
  const sent = state.saving;
  if (state.gone || !sent) return;
  state.saving = null;
  if (status === 409 && conflict) {
    state.failures = 0;
    state.retrying = false;
    // A merge would move the text under an IME composition; it waits for the composition to end.
    if (state.composing) {
      state.held = { conflict, sent };
      return;
    }
    apply409(state, effects, conflict, sent);
  } else if (status === 404) {
    goGone(state, effects);
  } else if (status === null || (status >= 500 && status !== 507)) {
    retryLater(state, effects, sent, false);
    return;
  } else if (status === 413) {
    stopSaving(state, effects, "tooLarge", cap ?? capOf(state.summary?.kind));
  } else if (status === 507) {
    stopSaving(state, effects, "full");
    state.full = full;
  } else {
    stopSaving(state, effects, "invalid");
  }
  state.pending = false;
  readIfWanted(state, effects);
}

/** The save was still unanswered at its deadline. The link is up but too slow for it, and the text
 *  may have landed: it is retried like a lost save, and said to be slow rather than offline. */
export function saveTimedOut(state: CanvasState, effects: CanvasEffect[]): void {
  const sent = state.saving;
  if (state.gone || !sent) return;
  state.saving = null;
  retryLater(state, effects, sent, true);
}

/** A save whose fate is unknown: its text stays as maybe on the server, and the save goes again
 *  after a wait that grows with each failure in a row. */
function retryLater(state: CanvasState, effects: CanvasEffect[], sent: Sent, slow: boolean): void {
  if (!state.unsure.includes(sent.content)) state.unsure = [...state.unsure, sent.content].slice(-UNSURE_KEEP);
  state.failures++;
  state.slow = slow;
  state.retrying = true;
  effects.push({ type: "retryIn", ms: RETRY_DELAYS_MS[Math.min(state.failures, RETRY_DELAYS_MS.length) - 1] });
  settleAll(state, effects, null);
  state.pending = false;
}

/** What a 409 makes of the text: the person's own lost write, a clean merge, or a conflict. */
export function apply409(state: CanvasState, effects: CanvasEffect[], conflict: ArtifactConflict, sent: Sent): void {
  state.pending = false;
  state.seen = Math.max(state.seen, conflict.head_version);
  const theirs = { version: conflict.head_version, content: conflict.content, author: conflict.author };
  const own = conflict.author === "user" && (conflict.content === sent.content || state.unsure.includes(conflict.content));
  if (own) {
    moveBase(state, theirs);
    if (conflict.content === sent.content) settleUpTo(state, effects, sent.gen, theirs.version);
    effects.push({ type: "dropDraft", text: conflict.content });
    if (isDirty(state)) send(state, effects);
    else settleAll(state, effects, state.base.version);
    return;
  }
  const merge = merge3(state.base.content, state.text, theirs.content);
  if (!merge.ok) {
    state.conflict = { theirs };
    settleAll(state, effects, null);
    return;
  }
  replaceText(state, merge.text, merge.edits);
  moveBase(state, theirs);
  if (isDirty(state)) {
    send(state, effects);
    return;
  }
  settleAll(state, effects, state.base.version);
  effects.push({ type: "dropDraft" });
}

/** Saving stops until the text changes or the person saves by hand; nobody waits on it. `cap` is the
 *  limit a "too large" stop was held to. */
function stopSaving(state: CanvasState, effects: CanvasEffect[], stop: Stop, cap: number | null = null): void {
  state.stop = stop;
  state.cap = cap;
  state.failures = 0;
  state.retrying = false;
  settleAll(state, effects, null);
}
