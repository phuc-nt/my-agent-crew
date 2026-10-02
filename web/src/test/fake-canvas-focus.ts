import type { CanvasFocus, FocusSelection } from "../api/artifact-types";
import { type FakeReply, invalid, ok, refused } from "./fake-canvas-faults";

/** As long as the longest message the chat takes, the server's `SELECTION_MAX`. */
const SELECTION_MAX = 20000;

/** What the focus needs to know of the canvases around it. */
export type Shelf = {
  /** The newest version of a canvas; undefined when there is none such. */
  head: (id: string) => number | undefined;
  /** Shares the canvas with a conversation, which opening it there does. */
  link: (id: string, conversationId: string) => void;
};

type Checked = { refusal: FakeReply } | { id: string | null; selection: FocusSelection | null; present: boolean };

function isSelection(value: unknown): value is FocusSelection {
  if (typeof value !== "object" || value === null) return false;
  const { version, text, line_start, line_end } = value as Record<string, unknown>;
  return [version, line_start, line_end].every((n) => Number.isInteger(n)) && typeof text === "string";
}

/** What the server's `valid_pick` and the focus route let through: a version that can exist,
 *  text with something in it, lines in order, and no more text than a message holds. */
function quotable({ version, text, line_start, line_end }: FocusSelection, head: number): boolean {
  return (
    version >= 1 && version <= head && text.trim() !== "" && line_end >= line_start && [...text].length <= SELECTION_MAX
  );
}

/**
 * The canvas each conversation has open, kept as the server keeps it: a `PUT` or a message that
 * carries a canvas sets it, a canvas made in a conversation opens there, and a canvas that goes
 * takes its focus with it. A message that carries nothing leaves it as it is.
 */
export class FocusBook {
  private rows = new Map<string, CanvasFocus>();

  constructor(private shelf: Shelf) {}

  /** What `GET` reads: the canvas open in the conversation, or null. */
  of(conversationId: string): CanvasFocus | null {
    const row = this.rows.get(conversationId);
    return row ? { artifact_id: row.artifact_id, selection: row.selection && { ...row.selection } } : null;
  }

  /** The canvas opens in the conversation and is shared with it, as if a tab had asked. */
  open(conversationId: string, id: string, selection: FocusSelection | null = null): void {
    this.shelf.link(id, conversationId);
    this.rows.set(conversationId, { artifact_id: id, selection });
  }

  /** A canvas deleted is open nowhere. */
  forget(id: string): void {
    for (const [conversationId, row] of this.rows) if (row.artifact_id === id) this.rows.delete(conversationId);
  }

  /** `PUT`: what `check_focus` lets through opens, a close closes, and a canvas that is not
   *  there is a 404 (a message with the same canvas still goes, and closes the focus). */
  put(conversationId: string, body: Record<string, unknown>): FakeReply {
    const checked = this.check(body);
    if ("refusal" in checked) return checked.refusal;
    if (checked.id !== null && !checked.present) return refused(404, "artifact not found");
    this.apply(conversationId, checked);
    return ok(this.of(conversationId));
  }

  /** A message's `canvas`: null once it is applied, or the 422 that stops the message with
   *  nothing stored. Absent or null leaves the focus as it is. */
  message(conversationId: string, canvas: unknown): FakeReply | null {
    if (canvas === undefined || canvas === null) return null;
    const checked = this.check(typeof canvas === "object" ? (canvas as Record<string, unknown>) : {});
    if ("refusal" in checked) return checked.refusal;
    this.apply(conversationId, checked);
    return null;
  }

  private check(body: Record<string, unknown>): Checked {
    const { artifact_id: id, selection = null } = body;
    if (id !== null && typeof id !== "string") return { refusal: invalid("artifact_id") };
    if (selection !== null && !isSelection(selection)) return { refusal: invalid("selection") };
    if (id === null) {
      if (selection === null) return { id, selection, present: false };
      return { refusal: refused(422, "a selection needs the canvas it was made in") };
    }
    const head = this.shelf.head(id);
    if (head === undefined) return { id, selection, present: false };
    if (selection !== null && !quotable(selection, head)) {
      return { refusal: refused(422, `the selection does not fit the canvas at version ${head}`) };
    }
    return { id, selection, present: true };
  }

  private apply(conversationId: string, { id, selection, present }: Extract<Checked, { present: boolean }>): void {
    if (!present || id === null) this.rows.delete(conversationId);
    else this.open(conversationId, id, selection);
  }
}
