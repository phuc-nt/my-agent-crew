/**
 * How large one version of a canvas may be, by kind, and how long a chat message may be.
 *
 * The table is the server's (`artifacts/kinds.py`), copied so a save that cannot fit stops before
 * it is sent. `tests/test_web_caps.py` fails when one side changes without the other.
 */

const KB = 1024;
const MB = 1024 * KB;

/** The most one version of each kind may hold, in bytes of UTF-8 text or of raw data. */
export const CAPS: Readonly<Record<string, number>> = {
  markdown: 512 * KB,
  code: 512 * KB,
  html: 4 * MB,
  svg: 2 * MB,
  mermaid: 512 * KB,
  image: 2 * MB,
};

/** The longest message the chat route takes (`ChatBody.text`), in characters. */
export const MESSAGE_MAX = 20000;

/** What a kind this build does not know, or a canvas not read yet, is held to. */
export const SMALLEST_CAP = Math.min(...Object.values(CAPS));

export function capOf(kind: string | null | undefined): number {
  return typeof kind === "string" && Object.hasOwn(CAPS, kind) ? CAPS[kind] : SMALLEST_CAP;
}

const encoder = new TextEncoder();

/** The length of `text` in UTF-8 bytes. */
export function utf8Bytes(text: string): number {
  return encoder.encode(text).length;
}

/** Whether `text` is within the cap of `kind`. Three bytes per UTF-16 unit is the most it can need. */
export function fits(text: string, kind: string | null | undefined): boolean {
  const cap = capOf(kind);
  return text.length * 3 <= cap || utf8Bytes(text) <= cap;
}
