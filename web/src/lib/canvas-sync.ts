/**
 * Keeping a canvas up with the server: the first read and the draft it meets, later reads, and
 * the stream's events.
 *
 * A newer version replaces the person's text only when nothing they typed is unsaved and they
 * have not typed since the read went out; otherwise the panel says a newer version exists and the
 * next save merges with it through a 409.
 */

import type { ArtifactDetail, ArtifactSummary } from "../api/artifact-types";
import { type CanvasDraft, textKey } from "./canvas-draft";
import { saveDue, send } from "./canvas-save";
import {
  editsBetween,
  goGone,
  isDirty,
  moveBase,
  readIfWanted,
  readingNow,
  replaceText,
  requestRead,
  settleAll,
  summaryOf,
  takeSummary,
} from "./canvas-state";
import type { CanvasEffect, CanvasState, Version } from "./canvas-types";
import { merge3 } from "./merge3";

export function read(state: CanvasState, effects: CanvasEffect[], detail: ArtifactDetail): void {
  if (state.gone) return;
  // An image has no text. It reads as an empty one that nothing edits, so it is never dirty and a
  // newer version only moves its base.
  const head: Version = { version: detail.head_version, content: detail.content ?? "", author: detail.head_author };
  takeSummary(state, summaryOf(detail));
  state.seen = Math.max(state.seen, head.version);
  if (state.phase !== "ready") {
    firstRead(state, effects, head);
    return;
  }
  const askedAt = state.reading?.gen;
  state.reading = null;
  if (head.author === "user" && state.unsure.includes(head.content)) {
    // A save whose reply was lost did land.
    moveBase(state, head);
    if (!isDirty(state)) {
      state.failures = 0;
      state.retrying = false;
      settleAll(state, effects, state.base.version);
    } else if (!state.stop && !state.saving && !state.held) send(state, effects);
  } else if (state.conflict) {
    if (head.version > state.conflict.theirs.version) state.conflict = { theirs: head };
  } else if (
    // A stop never outlives unsaved text, so text with nothing unsaved has no stop either.
    !state.saving &&
    !state.held &&
    !state.composing &&
    askedAt === state.gen &&
    !isDirty(state) &&
    head.version > state.base.version
  ) {
    replaceText(state, head.content, editsBetween(state.text, head.content));
    moveBase(state, head);
  }
  readIfWanted(state, effects);
}

/** The first read: the newest version, and the draft this device kept, if any, merged into it. */
function firstRead(state: CanvasState, effects: CanvasEffect[], head: Version): void {
  const draft = state.draft;
  state.phase = "ready";
  state.reading = null;
  state.draft = null;
  state.base = head;
  state.text = head.content;
  state.opened = "fresh";
  if (draft && draft.text === head.content) {
    effects.push({ type: "dropDraft" });
  } else if (draft && (standsOn(draft, head) || ownSave(draft, head))) {
    takeDraft(state, draft.text, "draft");
  } else if (draft) {
    const merge = merge3(draft.base, draft.text, head.content);
    if (!merge.ok) {
      takeDraft(state, draft.text, "conflict");
      state.base = { version: draft.base_version, content: draft.base, author: "user" };
      state.conflict = { theirs: head };
    } else if (merge.text === head.content) {
      effects.push({ type: "dropDraft" });
    } else {
      takeDraft(state, merge.text, "merged");
    }
  }
  if (state.seen > head.version) requestRead(state, effects);
}

/** The draft was edited from `head` itself. */
function standsOn(draft: CanvasDraft, head: Version): boolean {
  return draft.base_version === head.version && draft.base === head.content;
}

/** `head` is a save the draft sent before the page went away: the draft's text came after it. */
function ownSave(draft: CanvasDraft, head: Version): boolean {
  return head.author === "user" && draft.sent.includes(textKey(head.content));
}

function takeDraft(state: CanvasState, text: string, opened: "draft" | "merged" | "conflict"): void {
  state.text = text;
  state.gen++;
  state.opened = opened;
}

export function readFailed(state: CanvasState, effects: CanvasEffect[], status: number | null): void {
  if (state.gone) return;
  if (status === 404) {
    goGone(state, effects);
    return;
  }
  state.reading = null;
  if (state.phase === "ready") state.readWanted = false;
  else state.phase = "failed";
}

export function event(
  state: CanvasState,
  effects: CanvasEffect[],
  artifact: ArtifactSummary | { id: string; deleted: true },
): void {
  if (artifact.id !== state.id || state.gone) return;
  if ("deleted" in artifact) {
    goGone(state, effects);
    return;
  }
  takeSummary(state, artifact);
  state.seen = Math.max(state.seen, artifact.head_version);
  // A save in flight or a composition settles first; the version is read after it if needed.
  if (state.phase !== "ready" || state.saving || state.held || state.composing) return;
  if (artifact.head_version <= state.base.version) return;
  // Heard of twice, by the stream and by the reply to what made it: the read that went out after
  // the first word of this version brings it, and another would only read the same again.
  if (state.reading && artifact.head_version <= state.reading.seen) return;
  if (state.conflict) {
    if (artifact.head_version > state.conflict.theirs.version) requestRead(state, effects);
    return;
  }
  if (!isDirty(state)) requestRead(state, effects);
}

/** The stream came back or the tab showed: load, retry or read, whichever is due. */
export function resync(state: CanvasState, effects: CanvasEffect[]): void {
  if (state.phase === "failed") {
    state.phase = "loading";
    state.reading = readingNow(state);
    effects.push({ type: "get" });
    return;
  }
  if (state.phase === "loading" || state.gone) return;
  if (state.retrying) saveDue(state, effects, "retry");
  else requestRead(state, effects);
}
