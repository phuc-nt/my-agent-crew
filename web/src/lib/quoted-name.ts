// A name put into a sentence: a key a script chose, a title a person typed, a namespace as
// it is stored. Any of them may hold a quote, a line break or spaces at its end, and would
// then reshape the sentence around it: most of all in the browser's own question box, which
// draws its text as it comes, line breaks and all.
import { showHiddenChars } from "./hidden-chars";

/** The most of a name a sentence takes, in characters. */
export const QUOTED_NAME_CHARS = 80;

// JSON leaves these as they are, and each still ends a line or draws as nothing: DEL, the
// C1 controls (the next-line character among them), the line and paragraph separators.
const UNESCAPED = /[\u007F-\u009F\u2028\u2029]/g;
const escaped = (char: string) => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`;

/**
 * The name between double quotes, written as JSON writes a string: a quote and a backslash
 * escaped, a line break and every other control character as its escape. The name is then
 * one run on one line, and it ends where its closing quote stands, spaces and all.
 *
 * A name longer than {@link QUOTED_NAME_CHARS} characters is cut there, with "…" before the
 * closing quote. It is cut as it is stored and escaped after, so no escape is cut in two.
 * The characters nobody would see are written out as their code points, as elsewhere.
 */
export function quotedName(name: string): string {
  const chars = Array.from(name);
  const kept = chars.length > QUOTED_NAME_CHARS ? `${chars.slice(0, QUOTED_NAME_CHARS).join("")}…` : name;
  return showHiddenChars(JSON.stringify(kept).replace(UNESCAPED, escaped));
}
