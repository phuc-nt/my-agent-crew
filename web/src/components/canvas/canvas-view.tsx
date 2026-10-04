/**
 * A canvas read rather than edited. Markdown goes through `MarkdownBody`, which shows raw HTML as
 * text, opens links away from the app and loads an outside image only when asked; code keeps its
 * spacing. Both write characters that change how text reads without being seen as marks. The kinds
 * shown as a page or a picture do not come here (`canvas-saved-view.tsx`).
 *
 * Each block, and each line of code, names the lines of the canvas it shows, so what a person
 * selects can be asked about by its lines (`lib/canvas-selection.ts`).
 */

import { Fragment, memo, type RefObject, useEffect, useRef } from "react";
import { type CanvasSelection, fromRendered } from "../../lib/canvas-selection";
import { showHiddenChars } from "../../lib/hidden-chars";
import { MarkdownBody } from "../markdown-body";

type Props = {
  text: string;
  kind: string;
  /** Told what is selected in the view whenever the selection changes there: null once it is
   *  gone, or no longer a passage. A selection made elsewhere on the page is none of its business. */
  onSelection?: (selection: CanvasSelection | null) => void;
};

function useSelectionReader(root: RefObject<HTMLElement | null>, text: string, onSelection: Props["onSelection"]) {
  useEffect(() => {
    if (!onSelection) return;
    const read = () => {
      const element = root.current;
      const selection = document.getSelection();
      if (!element || !selection || selection.rangeCount === 0) return;
      const range = selection.getRangeAt(0);
      if (!element.contains(range.startContainer) && !element.contains(range.endContainer)) return;
      onSelection(fromRendered(selection, element, text));
    };
    document.addEventListener("selectionchange", read);
    return () => document.removeEventListener("selectionchange", read);
  }, [root, text, onSelection]);
}

/** One span per line, the line ends between them as text, so the code reads and copies as it was.
 *  A line has no identity but its place, which is its key. */
function CodeLines({ text }: { text: string }) {
  return text.split("\n").map((line, at) => (
    <Fragment key={at}>
      {at > 0 ? "\n" : null}
      <span data-line-start={at + 1} data-line-end={at + 1}>
        {showHiddenChars(line)}
      </span>
    </Fragment>
  ));
}

function CodeView({ text, onSelection }: Omit<Props, "kind">) {
  const root = useRef<HTMLPreElement>(null);
  useSelectionReader(root, text, onSelection);
  return (
    <pre className="canvas-view canvas-code" ref={root}>
      <code>
        <CodeLines text={text} />
      </code>
    </pre>
  );
}

function MarkdownView({ text, onSelection }: Omit<Props, "kind">) {
  const root = useRef<HTMLDivElement>(null);
  useSelectionReader(root, text, onSelection);
  return (
    <div className="canvas-view" ref={root}>
      <MarkdownBody text={text} showHidden sourceLines />
    </div>
  );
}

/** Memoized so that what the panel does around it, such as typing a question, does not draw a
 *  long text again. Only markdown is read as markdown: any other kind, one the web does not know
 *  included, keeps its spacing as code does. */
export const CanvasView = memo(function CanvasView({ kind, ...rest }: Props) {
  return kind === "markdown" ? <MarkdownView {...rest} /> : <CodeView {...rest} />;
});
