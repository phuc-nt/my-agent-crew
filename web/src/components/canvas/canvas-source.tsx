/**
 * Where the open canvas came from, at the head of its body: the workspace file it was read from,
 * with a button that reads the file into it again, or a link to the page it was taken from. A
 * canvas made here has no source and shows no line.
 *
 * The source is text the server stored for an agent. It is read again here before anything is
 * drawn from it: only an http or https address becomes a link, named by the host it really leads
 * to, and a path shows the characters that hide or reorder text as marks.
 */

import type { CanvasController } from "../../hooks/use-canvas";
import { useCanvasReimport } from "../../hooks/use-canvas-reimport";
import { vi } from "../../i18n/vi";
import { parseSource } from "../../lib/canvas-source";
import { showHiddenChars } from "../../lib/hidden-chars";

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
        <a href={source.href} target="_blank" rel="noopener noreferrer">
          {text.open(source.host)}
        </a>
      </div>
    );
  }
  // The folder gives way on a narrow panel; the name of the file is the part that tells files apart.
  const path = showHiddenChars(`${agentName(source.agentId)}/${source.path}`);
  const cut = path.lastIndexOf("/") + 1;
  return (
    <>
      <div className="canvas-source">
        <span className="canvas-source-label">{text.label}</span>
        <span className="canvas-source-path" title={path}>
          <span className="canvas-source-dir">{path.slice(0, cut)}</span>
          <span className="canvas-source-file">{path.slice(cut)}</span>
        </span>
        <button type="button" className="ghost" disabled={busy || canvas.state.gone} onClick={() => void reimport()}>
          {busy ? text.reimporting : text.reimport}
        </button>
      </div>
      {note && (
        <div className={`notice ${note.tone} canvas-notice`} role={note.tone === "error" ? "alert" : "status"}>
          {note.text}
        </div>
      )}
    </>
  );
}
