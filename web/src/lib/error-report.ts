/**
 * The message that sends the errors a canvas page reported to the agent that wrote it. The page
 * wrote every word of the errors, so they go in a code fence the message says is data, never as
 * the message's own text, and under ceilings: the newest five, each cut at its own length, and the
 * whole message inside what the chat route takes.
 */

import { vi } from "../i18n/vi";
import { MESSAGE_MAX } from "./canvas-caps";
import { clip } from "./clip-text";
import { type FrameError, REPORT_MAX, where } from "./frame-messages";
import { showHiddenChars } from "./hidden-chars";

/** The most errors one message names: the newest, which the panel lists too. */
export const REPORT_ERRORS = 5;

const longestRun = (text: string): number =>
  (text.match(/`+/g) ?? []).reduce((most, run) => Math.max(most, run.length), 0);

/** `text` on one line as inline code, in ticks longer than any it holds. */
function inlineCode(text: string): string {
  const flat = showHiddenChars(text).replace(/\s+/g, " ").trim();
  const ticks = "`".repeat(longestRun(flat) + 1);
  const pad = flat.startsWith("`") || flat.endsWith("`") ? " " : "";
  return `${ticks}${pad}${flat}${pad}${ticks}`;
}

/** The message for the newest errors of the page of canvas `title`, mounted at `version`. */
export function errorReport(title: string, version: number, errors: FrameError[]): string {
  const { intro, outro } = vi.canvas.pageErrors.report;
  const head = intro(inlineCode(title), version);
  const listed = errors.slice(-REPORT_ERRORS).map((error, at) => {
    const place = where(error);
    return `${at + 1}. ${clip(error.message, REPORT_MAX)}${place ? `\n   at ${place}` : ""}`;
  });
  // Marks for hidden characters come last, so each error is cut by what the page wrote and not
  // by what the marks add; the fence is longer than any run of ticks the errors hold.
  const block = showHiddenChars(listed.join("\n"));
  const fence = "`".repeat(Math.max(3, longestRun(block) + 1));
  const room = MESSAGE_MAX - head.length - outro.length - 2 * fence.length - 6;
  return `${head}\n\n${fence}\n${clip(block, room)}\n${fence}\n\n${outro}`;
}
