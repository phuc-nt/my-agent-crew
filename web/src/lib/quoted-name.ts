// A name put where a person reads it or a screen reader says it: a key a script chose, a
// title a person typed, a namespace as it is stored. Any of them may hold a quote, a line
// break, a tab, or spaces in a row or at its end. A page folds those away, so two names would
// draw alike; a sentence is reshaped by them, most of all in the browser's own question box,
// which draws its text as it comes. So a name is written out one way everywhere.
import { asCode, showBlankChars } from "./hidden-chars";

/** The most of a name a sentence takes, in characters. */
export const QUOTED_NAME_CHARS = 80;

// JSON leaves these as they are, and each still ends a line or draws as nothing: DEL, the
// C1 controls (the next-line character among them), the line and paragraph separators.
const UNESCAPED = /[\u007F-\u009F\u2028\u2029]/g;
const escaped = (char: string) => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`;

/** One character as JSON writes it inside a string, with what JSON leaves unseen written too. */
const spelled = (char: string) => showBlankChars(JSON.stringify(char).slice(1, -1).replace(UNESCAPED, escaped));

/** The name character by character, each as it is written: an entry is never half an escape. */
function writing(name: string): string[] {
  const chars = Array.from(name);
  // A space reads as one only between two characters that are not spaces: a page drops the
  // ones a text opens or ends with and draws a run of them as one, and so does a screen reader.
  const folds = (at: number) => at === 0 || at === chars.length - 1 || chars[at - 1] === " " || chars[at + 1] === " ";
  return chars.map((char, at) => (char !== " " ? spelled(char) : folds(at) ? asCode(char) : char));
}

/**
 * The whole name on one line, so that two names never draw or sound alike for a character
 * nobody would see: a quote and a backslash escaped and every control character as its
 * escape, the way JSON writes a string (a line break is "\n"); a character that draws as
 * nothing, or as a space that is not the ordinary one, as its code point ("[U+200B]"); and a
 * space the name opens or ends with, or one of several in a row, as "[U+0020]".
 */
export function writtenName(name: string): string {
  return writing(name).join("");
}

/**
 * The name written the same way between double quotes, for a sentence: it ends where its
 * closing quote stands. A name longer than {@link QUOTED_NAME_CHARS} characters is cut there,
 * with "…" before the closing quote; each character is written as the whole name has it, and
 * the cut falls between two of them.
 */
export function quotedName(name: string): string {
  const chars = writing(name);
  const kept = chars.length > QUOTED_NAME_CHARS ? `${chars.slice(0, QUOTED_NAME_CHARS).join("")}…` : chars.join("");
  return `"${kept}"`;
}
