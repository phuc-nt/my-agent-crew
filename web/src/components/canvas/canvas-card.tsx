import { useEffect } from "react";
import { vi } from "../../i18n/vi";
import { type ArtifactTag, isArtifactId, parseArtifactTag } from "../../lib/artifact-tag";
import { cleanTitle } from "../../lib/canvas-title";
import { showHiddenChars } from "../../lib/hidden-chars";
import type { ThreadItem } from "../../state/thread-reducer";
import { Icon } from "../ui/icon";

type ToolItem = Extract<ThreadItem, { kind: "tool" }>;

/** What the thread knows of the canvases of its conversation, for the cards it draws of writes to them. */
export type CanvasLinks = {
  /** The canvas's title, or null while the thread does not know it. */
  titleOf(id: string): string | null;
  isGone(id: string): boolean;
  /** Asks the server, once, whether a canvas a card names is still there. */
  verify(id: string): void;
  open(id: string): void;
};

const CREATE = "artifact_create";
const EDIT = "artifact_edit";
const WRITES = [CREATE, EDIT, "artifact_rewrite"];

/** A write is drawn as a canvas card while it runs and once it is done. One that failed, was refused,
 *  was cut short or waits to be allowed keeps the plain tool card, which shows why. */
export function isCanvasWrite(item: ToolItem): boolean {
  return WRITES.includes(item.name) && (item.status === "running" || item.status === "done");
}

/** One argument of a call. They are whatever the model sent, and a call saved by an older version
 *  holds them as one line of text: anything but a mapping has no arguments to read. */
function argument(item: ToolItem, key: string): unknown {
  const args: unknown = item.arguments;
  return typeof args === "object" && args !== null ? (args as Record<string, unknown>)[key] : undefined;
}

/** The id an edit or a rewrite was given, when it is one the server makes. A create names none:
 *  it makes its canvas, and only the tag in its result says which. */
function givenId(item: ToolItem): string | null {
  const id = argument(item, "id");
  return item.name !== CREATE && typeof id === "string" && isArtifactId(id) ? id : null;
}

/** The title a create under way was given, as the server will keep it. Only a call still running
 *  is titled this way: once it is done the thread knows the canvas by the title it was kept under. */
function givenTitle(item: ToolItem): string | null {
  const title = argument(item, "title");
  if (item.name !== CREATE || item.status !== "running" || typeof title !== "string") return null;
  const clean = cleanTitle(title);
  return typeof clean === "string" ? clean : null;
}

/** What a finished write did to its canvas, and to which version when its tag says. */
function outcome(name: string, tag: ArtifactTag | null): string {
  const { card } = vi.canvas;
  const what = tag?.unchanged ? card.unchanged : name === CREATE ? card.created : name === EDIT ? card.edited : card.rewritten;
  return tag ? card.version(what, tag.version) : what;
}

/**
 * A canvas write in the thread, drawn as the canvas it made or changed rather than as a tool call:
 * its title, what was done and to which version, and a button that opens it. It never shows the
 * arguments or the text of the result, which are the canvas's content and not the thread's.
 *
 * The canvas is the one the tag at the start of the result names; an edit or a rewrite whose result
 * has no tag falls back to the id it was given, when that is one the server makes. A card still
 * running has nothing to open yet, and asks the server nothing.
 */
export function CanvasCard({ item, canvas }: { item: ToolItem; canvas: CanvasLinks }) {
  const { card } = vi.canvas;
  const { titleOf, isGone, verify, open } = canvas;
  const running = item.status === "running";
  const done = item.status === "done";
  const tag = parseArtifactTag(item.output);
  const id = tag?.id ?? givenId(item);
  const gone = id !== null && isGone(id);

  useEffect(() => {
    if (done && id !== null) verify(id);
  }, [done, id, verify]);

  const title = showHiddenChars((id === null ? null : titleOf(id)) || givenTitle(item) || card.untitled);
  return (
    <div className={`tool-card canvas-card ${item.status}`} data-testid="canvas-card" data-tool={item.name}>
      <Icon name="document" className="tool-icon" />
      <div className="canvas-card-text">
        <span className="canvas-card-title">{title}</span>
        <span className={`canvas-card-line tool-status ${item.status}`}>
          {running && <Icon name="spinner" />}
          {running ? card.writing : gone ? vi.canvas.gone : outcome(item.name, tag)}
        </span>
      </div>
      {done && id !== null && !gone && (
        <button type="button" className="ghost canvas-card-open" aria-label={card.openLabel(title)} onClick={() => open(id)}>
          {card.open}
        </button>
      )}
    </div>
  );
}
