/**
 * Where the open canvas came from, at the head of its body: the workspace file it was read from,
 * with a button that reads the file into it again, or a link to the page it was taken from. A
 * canvas made here has no source and shows no line.
 *
 * The source is text the server stored for an agent. It is read again here before anything is
 * drawn from it: only an http or https address that leads off this app becomes a link, named by
 * the host it leads to and by the tab it opens in, with the whole address on hover; and a path
 * shows as marks the characters nobody would see in it.
 *
 * The button is held off, never locked, while the file is read, on a canvas not read yet and on
 * one that is gone: a locked button drops the keyboard that pressed it onto the page. What the
 * read came to is said under the line, news in a place that is there before it has any, for a
 * screen reader announces what changes inside a region it already knows.
 */

import type { CanvasController } from "../../hooks/use-canvas";
import { useCanvasReimport } from "../../hooks/use-canvas-reimport";
import { vi } from "../../i18n/vi";
import { parseSource } from "../../lib/canvas-source";
import { showHiddenChars, showPathChars } from "../../lib/hidden-chars";

type Props = {
  canvas: CanvasController;
  artifactId: string;
  agentName(id: string): string;
  /** The dock's flush: the typing is saved before the file is read again. */
  flush(): Promise<number | null>;
};

export function CanvasSource({ canvas, artifactId, agentName, flush }: Props) {
  const text = vi.canvas.source;
  const { reimport, busy, note } = useCanvasReimport(artifactId, canvas, flush);
  const source = parseSource(canvas.state.summary?.source ?? "");
  if (source === null) return null;
  if (source.kind === "url") {
    return (
      <div className="canvas-source">
        <a href={source.href} title={source.href} aria-label={text.openLabel(source.host)} target="_blank" rel="noopener noreferrer">
          {text.open(source.host)}
        </a>
      </div>
    );
  }
  // The folder gives way on a narrow panel; the name of the file is the part that tells files apart.
  const path = `${showHiddenChars(agentName(source.agentId))}/${showPathChars(source.path)}`;
  const cut = path.lastIndexOf("/") + 1;
  // A canvas still loading stands on no version to read the file over.
  const off = busy || canvas.state.gone || canvas.state.phase !== "ready";
  const news = note?.tone === "info";
  return (
    <>
      <div className="canvas-source">
        <span className="canvas-source-label">{text.label}</span>
        <span className="canvas-source-path" title={path}>
          <span className="canvas-source-dir">{path.slice(0, cut)}</span>
          <span className="canvas-source-file">{path.slice(cut)}</span>
        </span>
        <button
          type="button"
          className="ghost"
          aria-disabled={off}
          onClick={() => {
            if (!off) void reimport();
          }}
        >
          {busy ? text.reimporting : text.reimport}
        </button>
      </div>
      <div className={news ? "notice info canvas-notice" : "canvas-source-news"} role="status">
        {news && note.text}
      </div>
      {note?.tone === "error" && (
        <div className="notice error canvas-notice" role="alert">
          {note.text}
        </div>
      )}
    </>
  );
}
