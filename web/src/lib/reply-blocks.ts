/**
 * A reply cut into what the thread draws of it: its prose, and each line that sends something.
 */

import { artifactRef } from "./artifact-ref";

const MEDIA_PREFIX = "MEDIA:";
const FILE_PREFIX = "FILE:";

/**
 * A `canvas` block keeps its line as the reply has it. That is what the thread shows where it
 * draws no canvas: an `id` of "" is a line that meant a canvas and did not write one canvas's id.
 */
export type ReplyBlock = { kind: "text" | "media" | "file"; value: string } | { kind: "canvas"; id: string; line: string };

/** What a line that sends something sends: the canvas its path names, or else the file at that path. */
function sent(kind: "media" | "file", line: string, path: string): ReplyBlock {
  const id = artifactRef(path);
  return id === null ? { kind, value: path } : { kind: "canvas", id, line };
}

/**
 * Splits a reply into text blocks, `MEDIA:<path>` lines, which become inline images, and
 * `FILE:<path>` lines, which become download links. Either line names a canvas when its path is
 * `artifact:<id>`, and becomes that canvas.
 *
 * Both prefixes are handled here rather than only on the Telegram side, because the same
 * reply text is what the web shows. Leaving `FILE:` unparsed would print the raw line in
 * the chat, so the person on the web would read a path where the person on Telegram got
 * the file itself.
 */
export function splitMedia(text: string): ReplyBlock[] {
  const blocks: ReplyBlock[] = [];
  const pending: string[] = [];
  const flush = () => {
    if (pending.length > 0) blocks.push({ kind: "text", value: pending.join("\n") });
    pending.length = 0;
  };
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    // A bare prefix with nothing after it is not a path, so it stays prose rather than
    // becoming a link to the workspace root.
    if (trimmed.startsWith(MEDIA_PREFIX) && trimmed.length > MEDIA_PREFIX.length) {
      flush();
      blocks.push(sent("media", trimmed, trimmed.slice(MEDIA_PREFIX.length).trim()));
    } else if (trimmed.startsWith(FILE_PREFIX) && trimmed.length > FILE_PREFIX.length) {
      flush();
      blocks.push(sent("file", trimmed, trimmed.slice(FILE_PREFIX.length).trim()));
    } else {
      pending.push(line);
    }
  }
  flush();
  return blocks;
}
