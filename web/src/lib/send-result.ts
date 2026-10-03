import { ApiError } from "../api/client";
import type { AgentEvent } from "../api/types";
import { vi } from "../i18n/vi";

/**
 * How a send went, for whoever typed the words, known as soon as the server says anything.
 *
 * `sent`: the server took the message and a turn runs for it, or the send was cut off on
 * purpose (Stop, leaving the conversation) — either way the words are not the caller's to
 * give back. `queued`: the server holds the message behind a turn already running, and a
 * chip stands for it. `failed`: the server never took it; `error` says why, in our words.
 */
export type SendResult = { status: "sent" } | { status: "queued" } | { status: "failed"; error: string };

export interface Settlement {
  readonly promise: Promise<SendResult>;
  /** True once the server has said anything, or the send has failed or been cut off. */
  readonly done: boolean;
  /** An event came in: `queued` for a queued message, `sent` for anything else. */
  heard(event: AgentEvent): void;
  /** The request failed. Counts only while nothing has been heard. */
  failed(error: unknown): void;
  /** The request is over. Counts only while nothing has been heard: a stream that was
   *  aborted, or that closed having said nothing, took the message all the same. */
  ended(): void;
}

/** A send's answer. It settles once, on whichever of the three comes first. `withCanvas` says
 *  the message carried the tab's canvas, which changes what a 422 means. */
export function settlement(withCanvas = false): Settlement {
  let settle: (result: SendResult) => void = () => {};
  const promise = new Promise<SendResult>((resolve) => {
    settle = resolve;
  });
  let done = false;
  // A promise keeps the first result it is given and ignores the rest, so a later answer only
  // sets `done` again.
  const set = (result: SendResult) => {
    done = true;
    settle(result);
  };
  return {
    promise,
    get done() {
      return done;
    },
    heard: (event) => set({ status: event.type === "queued" ? "queued" : "sent" }),
    failed: (error) => set({ status: "failed", error: sendErrorText(error, withCanvas) }),
    ended: () => set({ status: "sent" }),
  };
}

/**
 * The sentence for a send that failed, chosen by what went wrong rather than copied from the
 * server: 409 is a conversation waiting on a decision, 429 a full queue, 422 — for a message
 * that carried the canvas — a selection the canvas no longer holds, a bare `TypeError` a
 * connection that never opened, and anything else one general sentence.
 */
export function sendErrorText(error: unknown, withCanvas = false): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return vi.busyConflict;
    if (error.status === 429) return vi.sendFailed.tooFast;
    if (error.status === 422 && withCanvas) return vi.sendFailed.selection;
  } else if (error instanceof TypeError) {
    return vi.requestErrors.network;
  }
  return vi.sendFailed.other;
}
