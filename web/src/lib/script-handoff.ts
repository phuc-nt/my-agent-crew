/**
 * The message a script job opens a turn with (`handed_on` in
 * my_agent_crew/scheduler/script_job.py): the schedule's prompt, an empty line, a sentence
 * naming two marker lines, and between those two lines what the script printed. The markers
 * carry a number made for that one message, after the script ended.
 *
 * That shape is for the model. The thread shows the message as its two parts instead: the
 * prompt, which is the person's, and what the script printed, which is whatever its tools
 * handed it. The stored text is not touched: this only reads it.
 *
 * The server writes the two markers and the sentence, and nothing at runtime reads both
 * sides: `tests/test_script_handoff_words.py` holds the two constants below and
 * `vi.scriptHandoff.fence` to the server's own (`my_agent_crew/texts_script_job.py`).
 */
import { vi } from "../i18n/vi";

export interface ScriptHandoff {
  /** The schedule's prompt, as the message opens. */
  prompt: string;
  /** What the script printed, exactly as it stands between the two marker lines. */
  printed: string;
}

// Each a one-line constant, as the Python test reads them.
const OPENING = "<<<SCRIPT_IN_RA {nonce}";
const CLOSING = "SCRIPT_IN_RA {nonce}>>>";
/** The number a marker carries: sixteen lowercase hex digits. */
const NONCE = /^[0-9a-f]{16}$/;

/** The number the closing marker `line` carries, when it is one. */
function closingNonce(line: string): string | undefined {
  const [before, after] = CLOSING.split("{nonce}");
  if (!line.startsWith(before) || !line.endsWith(after)) return undefined;
  const nonce = line.slice(before.length, line.length - after.length);
  return NONCE.test(nonce) ? nonce : undefined;
}

/** A printed text reads at a glance up to either measure; past one it would bury the thread. */
const LONG_LINES = 12;
const LONG_CHARS = 800;

/**
 * The two parts of a message a script job handed on, or null for any other message.
 *
 * Read strictly, since a marker a person typed or quoted is their sentence and stays one.
 * All of this has to hold: the last line is the closing marker; a line above it is the
 * opening marker with the same number; the line right over that is the server's sentence,
 * whole and with nothing added, naming those two markers; an empty line parts that sentence
 * from a prompt that says something; and at least one line stands between the markers.
 *
 * The sentence is not drawn, so it has to be the one known here to the letter: a line that
 * says anything else would have its words shown nowhere, and stays in the message instead.
 */
export function splitScriptHandoff(text: string): ScriptHandoff | null {
  const lines = text.split("\n");
  const closing = lines[lines.length - 1];
  const nonce = closingNonce(closing);
  if (nonce === undefined) return null;
  const opening = OPENING.replace("{nonce}", nonce);
  // The first such line. The number is made after the script ended, so neither the prompt
  // nor what was printed can hold it, and the server's own is the only one there is.
  const at = lines.indexOf(opening);
  if (at < 3 || at > lines.length - 3) return null;
  const sentence = vi.scriptHandoff.fence.replace("{opening}", opening).replace("{closing}", closing);
  if (lines[at - 1] !== sentence) return null;
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
