/**
 * A canvas title as the server keeps it (`clean_title` in `my_agent_crew/artifacts/kinds.py`), so
 * a title shown before the server has answered reads the way it will once it has.
 */

/** The most characters a title may hold, counted by code point. */
export const TITLE_MAX = 200;

/** The format characters a title keeps: the joiners that hold an emoji sequence or a word in some
 *  scripts together. Every other one is invisible at best, and a bidi override reorders what follows. */
const JOINERS = new Set(["\u{200C}", "\u{200D}"]);

/** What Python's `str.isspace` counts as a space. That is not what `\s` counts: it leaves out the
 *  separators U+001C to U+001F and U+0085, and takes in U+FEFF, which the server drops instead. */
const SPACES = /[\t-\r\x1C-\x20\x85\xA0\u{1680}\u{2000}-\u{200A}\u{2028}\u{2029}\u{202F}\u{205F}\u{3000}]/gu;

/** Why a title cannot be kept. */
export type TitleProblem = { problem: string };

/** One line of visible text, or why there is none. */
export function cleanTitle(title: string): string | TitleProblem {
  const visible = [...title.replace(SPACES, " ")].filter((ch) => JOINERS.has(ch) || !/[\p{Cc}\p{Cf}]/u.test(ch));
  const text = visible.join("").normalize("NFC").split(" ").filter(Boolean).join(" ");
  const length = [...text].length;
  if (length === 0) return { problem: "a canvas needs a title" };
  return length > TITLE_MAX ? { problem: `a title of ${length} characters is over ${TITLE_MAX}` } : text;
}
