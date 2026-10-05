/**
 * The arguments of a canvas write, read while the model is still writing them.
 *
 * The pieces arrive as the JSON text of an object that has not ended yet, so `JSON.parse` has
 * nothing to say about it. This reads the four texts a canvas write may carry at the top of
 * that object and nothing else: every other value is passed over, whatever it holds, and what
 * goes wrong ends the reading there, with what was read before it kept.
 */

/** `content` is there as soon as its text opens, as far as it has come. The other three are
 *  there only once closed: half a title names something else, and half an id names nothing. */
export type PartialArgs = { title?: string; kind?: string; id?: string; content?: string };

/** What stands in for half of a character whose other half is not there. */
const LOST = String.fromCharCode(0xfffd);

/** The escapes that stand for another character than the one written. */
const ESCAPES = new Map([
  ["n", "\n"],
  ["t", "\t"],
  ["r", "\r"],
  ["b", "\b"],
  ["f", "\f"],
]);

const PLAIN = /[^"\\]*/y;
const SPACE = /[ \t\n\r]*/y;
const BARE = /[^\s,:{}[\]"]+/y;
const HEX4 = /^[0-9a-fA-F]{4}$/;

const isHigh = (unit: number) => unit >= 0xd800 && unit <= 0xdbff;
const isLow = (unit: number) => unit >= 0xdc00 && unit <= 0xdfff;

function skipSpace(text: string, at: number): number {
  SPACE.lastIndex = at;
  SPACE.test(text);
  return SPACE.lastIndex;
}

/** The code unit the four characters at `at` spell: NaN when they are not four hex digits, and
 *  null when the text ends before there are four, since the rest may be on its way. */
function unitAt(text: string, at: number): number | null {
  if (at + 4 > text.length) return null;
  const hex = text.slice(at, at + 4);
  return HEX4.test(hex) ? Number.parseInt(hex, 16) : Number.NaN;
}

/** The second half of a character whose first half ends at `at`: -1 when something else stands
 *  there, and null when the text ends before it can be told. */
function lowHalfAt(text: string, at: number): number | null {
  if (at >= text.length) return null;
  if (text[at] !== "\\") return -1;
  if (at + 1 >= text.length) return null;
  if (text[at + 1] !== "u") return -1;
  const unit = unitAt(text, at + 2);
  if (unit === null) return null;
  return isLow(unit) ? unit : -1;
}

/**
 * The text of the string that opens just before `start`, and where it ends: the place after
 * its closing quote, or -1 when the text ends first.
 *
 * An escape the end of the text cuts short is left out, to be read when the rest of it comes.
 * One that is whole and wrong does not end the reading: the model wrote it, the server will
 * answer for it, and the text after it is still the canvas.
 */
function readString(text: string, start: number): { value: string; end: number } {
  const parts: string[] = [];
  let at = start;
  while (at < text.length) {
    PLAIN.lastIndex = at;
    PLAIN.test(text);
    parts.push(text.slice(at, PLAIN.lastIndex));
    at = PLAIN.lastIndex;
    if (text[at] === '"') return { value: parts.join(""), end: at + 1 };
    const escape = text[at + 1];
    if (escape === undefined) break;
    if (escape !== "u") {
      parts.push(ESCAPES.get(escape) ?? escape);
      at += 2;
      continue;
    }
    const unit = unitAt(text, at + 2);
    if (unit === null) break;
    if (Number.isNaN(unit)) {
      // The four that should be digits may hold the end of the string: only the escape goes.
      parts.push(LOST);
      at += 2;
      continue;
    }
    if (isHigh(unit)) {
      const low = lowHalfAt(text, at + 6);
      if (low === null) break;
      parts.push(low === -1 ? LOST : String.fromCharCode(unit, low));
      at += low === -1 ? 6 : 12;
      continue;
    }
    parts.push(isLow(unit) ? LOST : String.fromCharCode(unit));
    at += 6;
  }
  return { value: parts.join(""), end: -1 };
}

/** Where the value at `start` ends when it is not a text, or -1 when it has not ended, or is
 *  no value at all. Brackets are counted, and those written inside a text are not brackets. */
function skipValue(text: string, start: number): number {
  if (text[start] !== "{" && text[start] !== "[") {
    BARE.lastIndex = start;
    return BARE.test(text) ? BARE.lastIndex : -1;
  }
  let depth = 0;
  let quoted = false;
  for (let at = start; at < text.length; at++) {
    const ch = text[at];
    if (quoted) {
      if (ch === "\\") at += 1;
      else if (ch === '"') quoted = false;
    } else if (ch === '"') quoted = true;
    else if (ch === "{" || ch === "[") depth += 1;
    else if (ch === "}" || ch === "]") {
      depth -= 1;
      if (depth === 0) return at + 1;
    }
  }
  return -1;
}

/** A key given twice keeps its last text, as it will when the server reads the whole. */
function take(args: PartialArgs, key: string, value: string, closed: boolean): void {
  if (key === "content") args.content = value;
  else if (closed && (key === "title" || key === "kind" || key === "id")) args[key] = value;
}

export function readPartialArgs(text: string): PartialArgs {
  const args: PartialArgs = {};
  let at = skipSpace(text, 0);
  if (text[at] !== "{") return args;
  at = skipSpace(text, at + 1);
  while (text[at] === '"') {
    const key = readString(text, at + 1);
    if (key.end === -1) break;
    at = skipSpace(text, key.end);
    if (text[at] !== ":") break;
    at = skipSpace(text, at + 1);
    if (text[at] === '"') {
      const value = readString(text, at + 1);
      take(args, key.value, value.value, value.end !== -1);
      at = value.end;
    } else {
      at = skipValue(text, at);
    }
    if (at === -1) break;
    at = skipSpace(text, at);
    if (text[at] !== ",") break;
    at = skipSpace(text, at + 1);
  }
  return args;
}
