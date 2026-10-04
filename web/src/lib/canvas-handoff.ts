/**
 * Saves that outlive the moment: one sent as the page may be going away, and the last save of a
 * canvas the person left without waiting for it, which a message sent soon after waits for.
 *
 * A browser caps the bodies of the `keepalive` requests in flight at 64 KiB and refuses a new one
 * that would go over, so a save is kept alive only while the page is hidden, only up to 60 KiB and
 * only while no other kept-alive save is out. Any other save goes as a plain request, which a
 * closing page may cut; the draft written as the page hid still holds its text.
 */

import { saveBody } from "../api/artifact-client";
import { utf8Bytes } from "./canvas-caps";
import { clearDraft, readDraft } from "./canvas-draft";
import type { CanvasState } from "./canvas-types";
import { guardUnload } from "./unload-guard";

/** The largest save body sent with `keepalive`, leaving room under the browser's 64 KiB. */
export const KEEPALIVE_MAX = 60 * 1024;

/** A canvas whose last save failed after its panel went away; `draft` is whether this device kept
 *  its text, which is otherwise held by this tab alone. */
export type HandoffFailure = { id: string; title: string | null; draft: boolean };

/** What `saveInBackground` needs of a canvas runner. */
type Leaving = {
  readonly id: string;
  readonly state: CanvasState;
  /** The last draft this device could not keep. */
  readonly draftFailed: boolean;
  flush(): Promise<number | null>;
  /** How long the save in flight may still go unanswered, in ms; with `first`, by the deadline it
   *  had before saves with no reply in time gave it longer. */
  waitMs(first?: boolean): number;
};

let keepaliveOut = false;
const listeners = new Set<{ listener: (failure: HandoffFailure) => void }>();
const savedListeners = new Set<{ listener: (id: string) => void }>();
/** The handoffs not yet settled, each dropped as it settles. */
const handoffs = new Map<Promise<void>, Leaving>();

function fitsKeepalive(content: string, baseVersion: number): boolean {
  const body = saveBody(content, baseVersion);
  // A UTF-16 unit is one to three UTF-8 bytes; measure only when the length cannot tell.
  if (body.length > KEEPALIVE_MAX) return false;
  return body.length * 3 <= KEEPALIVE_MAX || utf8Bytes(body) <= KEEPALIVE_MAX;
}

/** Runs `send`, asking it to keep the request alive when the page is `hidden`, the save's body
 *  fits and no other kept-alive save is out. */
export async function withKeepalive<T>(
  hidden: boolean,
  content: string,
  baseVersion: number,
  send: (keepalive: boolean) => Promise<T>,
): Promise<T> {
  if (!hidden || keepaliveOut || !fitsKeepalive(content, baseVersion)) return send(false);
  keepaliveOut = true;
  try {
    return await send(true);
  } finally {
    keepaliveOut = false;
  }
}

/** Hears each canvas whose last save failed after its panel went away. */
export function onHandoffFailed(listener: (failure: HandoffFailure) => void): () => void {
  const subscription = { listener };
  listeners.add(subscription);
  return () => void listeners.delete(subscription);
}

/** Hears each canvas that has nothing left unsaved: what was said of a save of its that failed
 *  holds no longer. */
export function onCanvasSaved(listener: (id: string) => void): () => void {
  const subscription = { listener };
  savedListeners.add(subscription);
  return () => void savedListeners.delete(subscription);
}

/** A version holds all of canvas `id`'s text: said by its open panel's runner, or by its handoff. */
export function canvasSaved(id: string): void {
  for (const { listener } of [...savedListeners]) listener(id);
}

/**
 * Saves what the person left in a canvas, after the save in flight if one is. The draft written as
 * the panel went away goes once a version holds its text, merged with someone else's or not; when
 * no version can, it stays and the listeners hear of it. A draft this device could not keep is held
 * by this tab, which asks before it closes for as long as it holds one; a runner that says it kept
 * none has the page ask until its save settles.
 */
export function saveInBackground(runner: Leaving): Promise<void> {
  const handoff = handOff(runner);
  handoffs.set(handoff, runner);
  const release = runner.draftFailed ? guardUnload() : null;
  const settled = () => {
    handoffs.delete(handoff);
    release?.();
  };
  handoff.then(settled, settled);
  return handoff;
}

async function handOff(runner: Leaving): Promise<void> {
  const left = runner.state.text;
  if ((await runner.flush()) !== null) {
    clearDraft(runner.id, left);
    // A draft that outlives this save holds words typed since: the canvas still has text unsaved.
    if (readDraft(runner.id) === null) canvasSaved(runner.id);
    return;
  }
  const failure = { id: runner.id, title: runner.state.summary?.title ?? null, draft: !runner.draftFailed };
  for (const { listener } of [...listeners]) listener(failure);
}

/** Resolves once every handoff now in flight has settled, those that failed included. */
export async function handoffsSettled(): Promise<void> {
  await Promise.allSettled([...handoffs.keys()]);
}

/** Whether the last save of canvas `id`, left behind, is still out. */
export function handoffOut(id: string): boolean {
  return [...handoffs.values()].some((runner) => runner.id === id);
}

/** The longest any handoff's save in flight has left of the deadline it was first given, in ms. */
function handoffWaitMs(): number {
  return Math.max(0, ...[...handoffs.values()].map((runner) => runner.waitMs(true)));
}

/** What `work` resolves to, or `late` when it has not settled within `ms`. */
export async function within<T, L>(ms: number, work: Promise<T>, late: L): Promise<T | L> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<L>((resolve) => {
    timer = setTimeout(() => resolve(late), ms);
  });
  try {
    return await Promise.race([work, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Waits for the open panel's last save (when there is a panel) and for every handoff, together, at
 * most `ms` after the longest save already in flight has had the deadline it was first given: a slow
 * link is not a stuck one, but what waits here is a person, and the longer deadline a save gets
 * after others went unanswered is minutes. The answer is the version the panel's save landed, or
 * null when it had not landed in time or failed; a handoff still out at the end does not take that
 * answer away.
 */
export async function flushAll(
  ms: number,
  panelSave: Promise<number | null> | null,
  panelWaitMs = 0,
): Promise<number | null> {
  const saved: { version: number | null } = { version: null };
  const landed = panelSave
    ? panelSave.then(
        (version) => void (saved.version = version),
        () => undefined,
      )
    : Promise.resolve();
  await within(ms + Math.max(panelWaitMs, handoffWaitMs()), Promise.all([landed, handoffsSettled()]), null);
  return saved.version;
}
