// What of an event's text a run's step keeps while the run is heard live: the client's twin
// of the server's `activity/step_previews.py`. A live row is drawn from the event and then
// replaced by the server's copy when the run settles, so a cut made differently here would
// change the row under its reader at that moment.

const PREVIEW_CHARS = 160;
/** A failed tool step keeps its reason whole up to this long. */
const FAILED_CHARS = 600;
/** Of a longer one: this much of its start and this much of its end, with "…" between. */
const FAILED_HEAD_CHARS = 200;
const FAILED_TAIL_CHARS = 400;

/** The longest text a failed step is ever kept at: a reason this long is read whole. */
export const FAILED_KEPT_CHARS = FAILED_HEAD_CHARS + 1 + FAILED_TAIL_CHARS;

export function preview(text: string): string {
  return text.length > PREVIEW_CHARS ? `${text.slice(0, PREVIEW_CHARS)}…` : text;
}

/**
 * What a tool step keeps of what the tool handed back.
 *
 * A call that went through keeps a glimpse: the row already says it worked. A call that
 * failed keeps its reason, because the reason is what the row is for, and a refusal ends
 * with what to do instead: the end is kept ahead of the middle. The server measures a
 * reason after setting its whitespace to single spaces, and counts characters rather than
 * UTF-16 units, so both are done here for the cut to fall in the same place.
 */
export function toolOutputPreview(text: string, ok: boolean): string {
  if (ok) return preview(text);
  const flat = text.split(/\s+/).filter((word) => word !== "").join(" ");
  const chars = Array.from(flat);
  if (chars.length <= FAILED_CHARS) return flat;
  return `${chars.slice(0, FAILED_HEAD_CHARS).join("")}…${chars.slice(-FAILED_TAIL_CHARS).join("")}`;
}
