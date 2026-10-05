import { vi } from "../i18n/vi";
import type { WritingPreview } from "../state/writing-previews";
import { isArtifactId } from "./artifact-tag";
import { cleanTitle } from "./canvas-title";
import { showHiddenChars } from "./hidden-chars";
import { readPartialArgs } from "./partial-json-content";

/**
 * A canvas the model is still writing, as the thread and the dock show it.
 *
 * All of it is what the model has written so far and none of it is stored: the title, the
 * kind and the id are held to what the server would accept before anything is made of them.
 */
export type WritingItem = {
  key: number;
  /** The call this turned out to be, once the step's answer has named it. */
  callId: string | null;
  updates: number;
  /** Whether the model is writing an existing canvas again, not making one. */
  rewrite: boolean;
  /** The canvas being written again: null for a new one, and until the id is whole and well formed. */
  id: string | null;
  title: string | null;
  kind: string | null;
  content: string;
  /** The size of `content` as it will be stored. */
  bytes: number;
};

/** What the tab already knows of a canvas by its id. */
export type KnownCanvases = {
  titleOf(id: string): string | null;
  kindOf(id: string): string | null;
};

const REWRITE_TOOL = "artifact_rewrite";
const encoder = new TextEncoder();

/** A kind a canvas can be, or null. Asked of the names themselves: `constructor` is no kind. */
const kindOrNull = (kind: string | null | undefined): string | null =>
  typeof kind === "string" && Object.hasOwn(vi.canvas.kinds, kind) ? kind : null;

/** The title as the server will keep it, or null when it would refuse it. */
function titleOrNull(title: string | undefined): string | null {
  if (title === undefined) return null;
  const clean = cleanTitle(title);
  return typeof clean === "string" ? clean : null;
}

/**
 * What a preview says of its canvas so far.
 *
 * A canvas being written again has its kind already, and a title too: both are asked of the
 * canvas the id names, and the title the call gives stands only where the tab knows none.
 * A canvas being made names none, whatever its arguments say.
 */
export function describeWriting(preview: WritingPreview, known: KnownCanvases): WritingItem {
  const args = readPartialArgs(preview.text);
  const rewrite = preview.name === REWRITE_TOOL;
  const id = rewrite && args.id !== undefined && isArtifactId(args.id) ? args.id : null;
  const content = args.content ?? "";
  return {
    key: preview.key,
    callId: preview.callId,
    updates: preview.updates,
    rewrite,
    id,
    title: (id === null ? null : known.titleOf(id)) ?? titleOrNull(args.title),
    kind: kindOrNull(rewrite ? (id === null ? null : known.kindOf(id)) : args.kind),
    content,
    bytes: encoder.encode(content).length,
  };
}

/** What a canvas being written goes by on the screen: its title with what hides in it written out,
 *  or a plain word until it has one. */
export function writingTitle(item: WritingItem): string {
  const { untitled, untitledNew } = vi.canvas.writing;
  return showHiddenChars(item.title ?? (item.rewrite ? untitled : untitledNew));
}

/** The kinds a stored canvas shows as a page or a drawing. One being written shows as its source. */
const DRAWN = ["html", "svg", "mermaid"];

/** Whether the canvas will look different once stored than the source shown while it is written. */
export const writtenAsSource = (item: WritingItem): boolean => item.kind !== null && DRAWN.includes(item.kind);
