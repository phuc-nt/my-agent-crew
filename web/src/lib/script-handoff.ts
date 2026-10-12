/**
 * The message a script job opens a turn with (`handed_on` in
 * my_agent_crew/scheduler/script_job.py): the schedule's prompt, an empty line, a sentence
 * naming two marker lines, and between those two lines what the script printed. The markers
 * carry a number made for that one message, after the script ended.
 *
 * That shape is for the model. The thread shows the message as its two parts instead: the
 * prompt, which is the person's, and what the script printed, which is whatever its tools
 * handed it. The stored text is not touched: this only reads it.
 */
export interface ScriptHandoff {
  /** The schedule's prompt, as the message opens. */
  prompt: string;
  /** What the script printed, exactly as it stands between the two marker lines. */
  printed: string;
}

/** The line that closes the message, and the number it carries. */
const CLOSING = /^SCRIPT_IN_RA ([0-9a-f]{16})>>>$/;

/** A printed text reads at a glance up to either measure; past one it would bury the thread. */
const LONG_LINES = 12;
const LONG_CHARS = 800;

/**
 * The two parts of a message a script job handed on, or null for any other message.
 *
 * Read strictly, since a marker a person typed or quoted is their sentence and stays one.
 * All of this has to hold: the last line is the closing marker; a line above it is the
 * opening marker with the same number; the line right over that names both markers, as the
 * server's sentence does; an empty line parts that sentence from a prompt that says
 * something; and at least one line stands between the markers.
 */
export function splitScriptHandoff(text: string): ScriptHandoff | null {
  const lines = text.split("\n");
  const closing = lines[lines.length - 1];
  const nonce = CLOSING.exec(closing)?.[1];
  if (nonce === undefined) return null;
  const opening = `<<<SCRIPT_IN_RA ${nonce}`;
  // The first such line. The number is made after the script ended, so neither the prompt
  // nor what was printed can hold it, and the server's own is the only one there is.
  const at = lines.indexOf(opening);
  if (at < 3 || at > lines.length - 3) return null;
  const sentence = lines[at - 1];
  const named = sentence.indexOf(`\`${opening}\``);
  if (named < 0 || sentence.indexOf(`\`${closing}\``, named) < 0) return null;
  if (lines[at - 2] !== "") return null;
  const prompt = lines.slice(0, at - 2).join("\n");
  if (prompt.trim() === "") return null;
  return { prompt, printed: lines.slice(at + 1, -1).join("\n") };
}

/** How many lines a printed text runs to, not counting the empty ones it ends on. */
export function printedLines(printed: string): number {
  return printed.replace(/\n+$/, "").split("\n").length;
}

/** Whether a printed text is long enough to stay folded until it is asked for. */
export function isLongPrinted(printed: string): boolean {
  return printedLines(printed) > LONG_LINES || printed.length > LONG_CHARS;
}
