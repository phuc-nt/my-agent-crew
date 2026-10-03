/**
 * Runs the canvas machine for one canvas: turns its effects into requests, timers and drafts, and
 * feeds the replies back in. `use-canvas` owns one per open panel; `saveInBackground` keeps one
 * going after its panel went away, until the last save lands.
 *
 * A detached runner reads nothing and retries nothing: it only finishes the save it was asked for.
 * The requests themselves, and the deadlines after which a silent one counts as lost, are in
 * `canvas-requests`.
 */

import { clearDraft, readDraft, textKey, writeDraft } from "./canvas-draft";
import { type CanvasEffect, type CanvasInput, type CanvasState, openState, step } from "./canvas-machine";
import { requestRead, requestSave } from "./canvas-requests";
import { isDirty } from "./canvas-state";

/** A save goes this long after the last keystroke. */
export const SAVE_DELAY_MS = 1500;
/** The draft is written this long after the last keystroke, and at once when the page may go. */
export const DRAFT_DELAY_MS = 300;

type Timer = ReturnType<typeof setTimeout> | undefined;

export class CanvasRunner {
  state: CanvasState;
  /** The last draft this device could not keep. */
  draftFailed = false;
  private detached = false;
  private saveTimer: Timer;
  private draftTimer: Timer;
  private retryTimer: Timer;
  private reading: AbortController | null = null;
  private tickets = 0;
  /** When the save in flight reaches its deadline. */
  private putEndsAt = 0;
  private readonly settles = new Map<number, (version: number | null) => void>();

  constructor(
    readonly id: string,
    private readonly onChange: () => void,
  ) {
    this.state = openState(id, readDraft(id));
  }

  /** Starts the first read. */
  start(): void {
    this.get();
  }

  /** Steps the machine and runs what it asks for. Inputs that need no timer or draft come here
   *  straight from the panel. */
  send(input: CanvasInput): void {
    const { state, effects } = step(this.state, input);
    this.state = state;
    for (const effect of effects) this.run(effect);
    this.changed();
  }

  edit(text: string): void {
    this.typed({ type: "edit", text });
  }

  undo(): void {
    this.typed({ type: "undo" });
  }

  /** Saves the text as it is now; the version that holds it, or null when none will. */
  flush(): Promise<number | null> {
    const ticket = ++this.tickets;
    return new Promise((resolve) => {
      this.settles.set(ticket, resolve);
      this.send({ type: "flush", ticket });
    });
  }

  /** Writes the draft now: the text, its base and the saves that may have landed unheard. */
  keepDraft(): void {
    this.draftTimer = stop(this.draftTimer);
    const { phase, gone, text, base, unsure, saving } = this.state;
    if (phase !== "ready" || gone) return;
    const sent = [...new Set([...unsure, ...(saving ? [saving.content] : [])].map(textKey))];
    const kept = writeDraft({
      artifact_id: this.id,
      base_version: base.version,
      base: base.content,
      text,
      saved_at: Date.now(),
      sent,
    });
    if (this.draftFailed === !kept) return;
    this.draftFailed = !kept;
    this.changed();
  }

  visibility(hidden: boolean): void {
    if (!hidden) {
      this.send({ type: "visibility", hidden: false });
      this.send({ type: "resync" });
      return;
    }
    this.keepDraft();
    this.send({ type: "visibility", hidden: true });
    this.send({ type: "saveDue", reason: "hidden" });
  }

  /** The panel went away: the draft is written, and only a save already asked for still runs. */
  detach(): void {
    this.saveTimer = stop(this.saveTimer);
    this.draftTimer = stop(this.draftTimer);
    this.retryTimer = stop(this.retryTimer);
    const reading = this.reading;
    this.reading = null;
    reading?.abort();
    this.detached = true;
    if (this.state.gone) clearDraft(this.id);
    else this.keepDraft();
    // The page may be closing: the save that follows goes as one kept alive when it fits.
    this.send({ type: "visibility", hidden: true });
  }

  /** How long the save in flight may still go unanswered, in ms; 0 when none is out. */
  waitMs(): number {
    return this.state.saving ? Math.max(0, this.putEndsAt - Date.now()) : 0;
  }

  /** Whether text may still be missing from the server. */
  needsSave(): boolean {
    const { phase, gone, saving, held } = this.state;
    return phase === "ready" && !gone && (isDirty(this.state) || saving !== null || held !== null);
  }

  /** A panel shows only its own runner: one it let go of may still hear a reply. */
  private changed(): void {
    if (!this.detached) this.onChange();
  }

  private typed(input: CanvasInput): void {
    const gen = this.state.gen;
    this.send(input);
    if (this.state.gen === gen) return;
    stop(this.saveTimer);
    this.saveTimer = setTimeout(() => {
      this.saveTimer = undefined;
      this.send({ type: "saveDue", reason: "timer" });
    }, SAVE_DELAY_MS);
    stop(this.draftTimer);
    this.draftTimer = setTimeout(() => this.keepDraft(), DRAFT_DELAY_MS);
  }

  private run(effect: CanvasEffect): void {
    switch (effect.type) {
      case "put":
        return this.put(effect.content, effect.baseVersion, effect.hidden);
      case "get":
        return this.get();
      case "retryIn":
        if (this.detached) return;
        stop(this.retryTimer);
        this.retryTimer = setTimeout(() => {
          this.retryTimer = undefined;
          this.send({ type: "saveDue", reason: "retry" });
        }, effect.ms);
        return;
      case "dropDraft":
        return clearDraft(this.id, effect.text);
      case "settle": {
        const resolve = this.settles.get(effect.ticket);
        this.settles.delete(effect.ticket);
        return resolve?.(effect.version);
      }
    }
  }

  private put(content: string, baseVersion: number, hidden: boolean): void {
    this.putEndsAt = Date.now() + requestSave(this.id, content, baseVersion, hidden, (input) => this.send(input));
  }

  private get(): void {
    if (this.detached) return;
    this.reading = requestRead(this.id, (input) => {
      this.reading = null;
      this.send(input);
    });
  }
}

function stop(timer: Timer): undefined {
  if (timer !== undefined) clearTimeout(timer);
  return undefined;
}
