/**
 * The shapes the canvas machine works on: its state, what it is told, and what it asks for.
 *
 * The machine (canvas-machine.ts) is pure: it takes the state and one input and returns the next
 * state and the effects to run, so every order of keystrokes, replies and stream events can be
 * tested without a browser. `CanvasRunner` turns the effects into requests, timers and drafts.
 */

import type {
  ArtifactConflict,
  ArtifactDetail,
  ArtifactSummary,
  ArtifactVersionMeta,
  StorageFull,
} from "../api/artifact-types";
import type { CanvasDraft } from "./canvas-draft";
import type { LineEdit } from "./line-edits";

/** Waits between retries of a lost save: 2, 5, 15 and 30 seconds, then every minute. */
export const RETRY_DELAYS_MS = [2000, 5000, 15000, 30000, 60000];
/** Lost saves remembered as maybe on the server; a read or a 409 that holds one is the person's own. */
export const UNSURE_KEEP = 8;

/** A version as the machine needs it: its number, its text and who wrote it. */
export type Version = { version: number; content: string; author: string };

export type Stop = "tooLarge" | "full" | "invalid";

export type CanvasState = {
  id: string;
  phase: "loading" | "failed" | "ready";
  /** The draft found on this device at opening, until the first read uses it. */
  draft: CanvasDraft | null;
  text: string;
  /** Rises with every change of `text`, so a reply knows whether the person typed since. */
  gen: number;
  /** The version `text` was edited from: what the next save names as its base. */
  base: Version;
  summary: ArtifactSummary | null;
  /** The save in flight: the text it carries, from which `gen`, on which base. */
  saving: { gen: number; content: string; baseVersion: number } | null;
  /** A save fell due while one was in flight. */
  pending: boolean;
  /** The read now out: the `gen` it was asked at, and the newest version heard of by then, which
   *  its reply holds or goes past. */
  reading: { gen: number; seen: number } | null;
  /** A read was asked for while a save or a read was out. */
  readWanted: boolean;
  /** Texts of saves whose reply never came. */
  unsure: string[];
  /** The newest version the stream or a reply has named. */
  seen: number;
  conflict: { theirs: Version } | null;
  /** A 409 that came back during IME composition, settled once composition ends. */
  held: { conflict: ArtifactConflict; sent: { gen: number; content: string } } | null;
  composing: boolean;
  hidden: boolean;
  stop: Stop | null;
  full: StorageFull | null;
  /** The cap a "too large" stop was held to, in bytes: the server's own figure when it refused. */
  cap: number | null;
  gone: boolean;
  /** Lost saves in a row; the retry waits longer with each. */
  failures: number;
  /** The last of them was a save still unanswered at its deadline, not one that failed outright. */
  slow: boolean;
  retrying: boolean;
  /** The person's text "Nạp bản mới" replaced, until they type. */
  undo: string | null;
  /** The last time the machine replaced the person's text, for the editor to keep the caret. */
  replaced: { seq: number; before: string; edits: LineEdit[] | null } | null;
  opened: "fresh" | "draft" | "merged" | "conflict" | null;
  /** `flush()` calls waiting for a save: each settles once a version holds the text at `gen`. */
  waiters: { ticket: number; gen: number }[];
};

export type SaveReason = "timer" | "blur" | "hidden" | "manual" | "retry" | "flush";

export type CanvasInput =
  | { type: "edit"; text: string }
  | { type: "saveDue"; reason: Exclude<SaveReason, "flush"> }
  | { type: "flush"; ticket: number }
  | { type: "saved"; meta: ArtifactVersionMeta }
  /** `status` is null when no reply came; `conflict`, `full` and `cap` carry what a 409, a 507 and a
   *  413 said. */
  | {
      type: "saveFailed";
      status: number | null;
      conflict: ArtifactConflict | null;
      full: StorageFull | null;
      cap?: number | null;
    }
  /** The save was still unanswered when its deadline came: the connection is up, but too slow for it. */
  | { type: "saveTimedOut" }
  | { type: "event"; artifact: ArtifactSummary | { id: string; deleted: true } }
  | { type: "read"; detail: ArtifactDetail }
  | { type: "readFailed"; status: number | null }
  | { type: "resync" }
  | { type: "keepMine" }
  | { type: "loadTheirs" }
  | { type: "undo" }
  | { type: "restored"; version: number; content: string }
  | { type: "composition"; composing: boolean }
  | { type: "visibility"; hidden: boolean }
  | { type: "renamed"; summary: ArtifactSummary };

/** What the hook runs for the machine. `dropDraft` with `text` drops the draft only while it
 *  still holds that text; without, it drops it whatever it holds. */
export type CanvasEffect =
  | { type: "put"; content: string; baseVersion: number; hidden: boolean }
  | { type: "get" }
  | { type: "retryIn"; ms: number }
  | { type: "dropDraft"; text?: string }
  | { type: "settle"; ticket: number; version: number | null };

export type CanvasStatus =
  | "loading"
  | "loadFailed"
  | "gone"
  | "conflict"
  | Stop
  | "offline"
  | "serverDown"
  | "slow"
  | "saving"
  | "newer"
  | "unsaved"
  | "saved";
