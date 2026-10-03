import type { Options } from "react-markdown";

type RehypePlugin = NonNullable<Options["rehypePlugins"]>[number];

/** The slice of a hast tree this plugin touches. */
export type HastNode = {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  position?: { start: { line: number }; end: { line: number } };
  children?: HastNode[];
};

// The blocks a selection can start or end in, each seen as a whole: what lies below them in the
// page (emphasis, links, cells) names no lines of its own.
const BLOCKS = new Set(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "table", "tr"]);

function label(node: HastNode, lines: NonNullable<HastNode["position"]>): void {
  node.properties = { ...node.properties, dataLineStart: lines.start.line, dataLineEnd: lines.end.line };
}

/**
 * Names on each block the first and last line of the markdown it was written on, as the
 * attributes `data-line-start` and `data-line-end`, so a selection in the rendered text can be
 * turned back into lines of the source. A fenced block is dropped to its `code` by the page
 * (see `MarkdownBody`), so the code takes the block's lines too. A node the parser did not make
 * from the source has no position and names nothing.
 *
 * There is no raw HTML in the tree (`rehype-raw` is absent), so nothing the text says can set
 * these attributes itself.
 */
export function markSourceLines(node: HastNode): void {
  const lines = node.position;
  if (node.type === "element" && node.tagName !== undefined && BLOCKS.has(node.tagName) && lines) {
    label(node, lines);
    if (node.tagName === "pre") {
      for (const child of node.children ?? []) if (child.type === "element" && child.tagName === "code") label(child, lines);
    }
  }
  for (const child of node.children ?? []) markSourceLines(child);
}

export const rehypeSourceLines: RehypePlugin = () => markSourceLines;
