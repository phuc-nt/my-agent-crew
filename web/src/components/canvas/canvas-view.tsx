/**
 * A canvas read rather than edited. Markdown goes through `MarkdownBody`, which shows raw HTML as
 * text, opens links away from the app and loads an outside image only when asked; code keeps its
 * spacing. Both write characters that change how text reads without being seen as marks.
 */

import { showHiddenChars } from "../../lib/hidden-chars";
import { MarkdownBody } from "../markdown-body";

export function CanvasView({ text, kind }: { text: string; kind: string }) {
  if (kind === "code") {
    return (
      <pre className="canvas-view canvas-code">
        <code>{showHiddenChars(text)}</code>
      </pre>
    );
  }
  return (
    <div className="canvas-view">
      <MarkdownBody text={text} showHidden />
    </div>
  );
}
