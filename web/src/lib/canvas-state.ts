/**
 * What the canvas machine asks of its state, and the small changes every handler makes to it.
 * Handlers work on the copy `step` made, never on the caller's state, and push the effects they
 * cause; arrays are replaced, not changed in place, so an earlier state stays as it was.
 */

import type { ArtifactDetail, ArtifactSummary } from "../api/artifact-types";
import type { CanvasDraft } from "./canvas-draft";
import { type CanvasEffect, type CanvasState, type CanvasStatus, SIZE_CAP, type Version } from "./canvas-types";
import { diffLines } from "./diff-lines";
import { type LineEdit, editsFromHunks } from "./line-edits";

/** Canvas `id` before its first read, with the draft this device kept for it, if any. */
export function openState(id: string, draft: CanvasDraft | null): CanvasState {
  return {
    id,
    phase: "loading",
    draft: draft?.artifact_id === id ? draft : null,
    text: "",
    gen: 0,
    base: { version: 0, content: "", author: "" },
    summary: null,
    saving: null,
    pending: false,
    reading: { gen: 0 },
    readWanted: false,
    unsure: [],
    seen: 0,
    conflict: null,
    held: null,
    composing: false,
    hidden: false,
    stop: null,
    full: null,
    gone: false,
    failures: 0,
    retrying: false,
    undo: null,
    replaced: null,
    opened: null,
    waiters: [],
  };
}

/** The status line. `online` is `navigator.onLine`, which tells a lost device from a lost server. */
export function statusOf(state: CanvasState, online: boolean): CanvasStatus {
  if (state.phase === "loading") return "loading";
  if (state.phase === "failed") return "loadFailed";
  if (state.gone) return "gone";
  if (state.conflict) return "conflict";
  if (state.stop) return state.stop;
  if (state.failures > 0) return online ? "serverDown" : "offline";
  if (state.saving || state.held) return "saving";
  if (state.seen > state.base.version) return "newer";
  return isDirty(state) ? "unsaved" : "saved";
}

/** Something may be missing from the server: text the base lacks, or a save nobody heard back from. */
export function isDirty(state: CanvasState): boolean {
  return state.text !== state.base.content || state.unsure.length > 0;
}

/** Whether `text` is within the size cap. Three bytes per character is the most UTF-16 can need. */
export function fits(text: string): boolean {
  return text.length * 3 <= SIZE_CAP || new TextEncoder().encode(text).length <= SIZE_CAP;
}

/** The summary fields of a read. */
export function summaryOf(detail: ArtifactDetail): ArtifactSummary {
  const { head_author: _author, content: _content, conversation_ids: _links, ...summary } = detail;
  return summary;
}

/** Takes `summary` unless it is older than the one held, so a late event keeps a newer title. */
export function takeSummary(state: CanvasState, summary: ArtifactSummary): void {
  if (state.summary === null || summary.head_version >= state.summary.head_version) state.summary = summary;
}

/** Moves the base forward to `next`; a version the machine holds proves no lost save is pending. */
export function moveBase(state: CanvasState, next: Version): void {
  if (next.version < state.base.version) return;
  state.base = next;
  state.unsure = [];
}

/** The line edits from `before` to `after`, or null when they are too large to compare. */
export function editsBetween(before: string, after: string): LineEdit[] | null {
  const afterLines = after.split("\n");
  const hunks = diffLines(before.split("\n"), afterLines);
  return hunks === null ? null : editsFromHunks(hunks, afterLines);
}

/** Replaces the person's text with `next`, noting what it was for the editor's caret. */
export function replaceText(state: CanvasState, next: string, edits: LineEdit[] | null): void {
  if (next === state.text) return;
  state.replaced = { seq: (state.replaced?.seq ?? 0) + 1, before: state.text, edits };
  state.text = next;
  state.gen++;
  state.undo = null;
}

/** Asks for a read, or for one after the save, the held reply or the read now out. */
export function requestRead(state: CanvasState, effects: CanvasEffect[]): void {
  if (state.gone) return;
  if (state.reading || state.saving || state.held) {
    state.readWanted = true;
    return;
  }
  state.readWanted = false;
  state.reading = { gen: state.gen };
  effects.push({ type: "get" });
}

export function readIfWanted(state: CanvasState, effects: CanvasEffect[]): void {
  if (state.readWanted && !state.gone) requestRead(state, effects);
}

/** Answers every waiting `flush()` with `version`. */
export function settleAll(state: CanvasState, effects: CanvasEffect[], version: number | null): void {
  for (const { ticket } of state.waiters) effects.push({ type: "settle", ticket, version });
  if (state.waiters.length > 0) state.waiters = [];
}

/** Answers the `flush()` calls whose text a version at or after `gen` holds. */
export function settleUpTo(state: CanvasState, effects: CanvasEffect[], gen: number, version: number): void {
  const done = state.waiters.filter((waiter) => waiter.gen <= gen);
  if (done.length === 0) return;
  for (const { ticket } of done) effects.push({ type: "settle", ticket, version });
  state.waiters = state.waiters.filter((waiter) => waiter.gen > gen);
}

/** The canvas was deleted: the text stays for copying, and nothing is sent again. */
export function goGone(state: CanvasState, effects: CanvasEffect[]): void {
  state.gone = true;
  if (state.phase !== "ready") {
    state.phase = "ready";
    state.text = state.draft?.text ?? "";
  }
  state.saving = null;
  state.reading = null;
  state.readWanted = false;
  state.held = null;
  state.conflict = null;
  state.stop = null;
  state.full = null;
  state.failures = 0;
  state.retrying = false;
  state.pending = false;
  state.undo = null;
  settleAll(state, effects, null);
}
