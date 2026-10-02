// Bidi controls reorder a line, so code can read other than it runs; zero-width characters
// hide inside a word. A canvas may hold text an agent copied from a web page, so the code
// view and the diff show these as visible marks. Copy and download keep the text as it is.
const HIDDEN = "[\\u061C\\u200B-\\u200F\\u202A-\\u202E\\u2060\\u2066-\\u2069\\uFEFF]";

/** Whether the text holds a character that changes how it reads without being seen. */
export function hasHiddenChars(text: string): boolean {
  return new RegExp(HIDDEN).test(text);
}

/** The text with each such character written as its code point: "a‮b" is "a[U+202E]b". */
export function showHiddenChars(text: string): string {
  return text.replace(new RegExp(HIDDEN, "g"), (char) => {
    const code = char.codePointAt(0) ?? 0;
    return `[U+${code.toString(16).toUpperCase().padStart(4, "0")}]`;
  });
}

/** The slice of a markdown tree the plugin below touches. */
type MdNode = { type: string; value?: string; children?: MdNode[] };

function mark(node: MdNode): void {
  if (typeof node.value === "string") node.value = showHiddenChars(node.value);
  node.children?.forEach(mark);
}

/** A remark plugin writing each such character as its mark in the parsed tree, prose and code
 *  alike. Marked in the source instead, a mark's brackets could join the text after it into a link. */
export function remarkHiddenChars() {
  return (tree: MdNode) => mark(tree);
}
