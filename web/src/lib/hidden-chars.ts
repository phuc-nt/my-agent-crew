// Bidi controls reorder a line, so code can read other than it runs; zero-width characters
// hide inside a word. A canvas may hold text an agent copied from a web page, so the code
// view and the diff show these as visible marks. Copy and download keep the text as it is.
const HIDDEN = "[\\u061C\\u200B-\\u200F\\u202A-\\u202E\\u2060\\u2066-\\u2069\\uFEFF]";

/** Whether the text holds a character that changes how it reads without being seen. */
export function hasHiddenChars(text: string): boolean {
  return new RegExp(HIDDEN).test(text);
}

/** A character written as its code point: a right-to-left override is "[U+202E]". */
export function asCode(char: string): string {
  const code = char.codePointAt(0) ?? 0;
  return `[U+${code.toString(16).toUpperCase().padStart(4, "0")}]`;
}

/** The text with each such character written as its code point: "a‮b" is "a[U+202E]b". */
export function showHiddenChars(text: string): string {
  return text.replace(new RegExp(HIDDEN, "g"), asCode);
}

// The control characters but tab and the two line breaks. None of them draws, and each one
// reaches an application as a key: a backspace in the middle of a word makes the word a person
// read another. Wherever a person approves a call, each is written as its code point. Kept apart
// from the set above, which the code view and the diff show and these do not need.
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g;

/** The text with each control character but tab, line feed and carriage return written as its
 *  code point: "sudx\bo" is "sudx[U+0008]o". */
export function showControlChars(text: string): string {
  return text.replace(CONTROL, asCode);
}

// A path names the file that is read, and the server stores more of one than a person can see
// (`check_path` in `my_agent_crew/tools/artifact_source_ref.py` refuses only control and format
// characters): what draws as nothing by default, a code point that means what a font says it
// does, the blank a braille cell draws, and every space that is not the ordinary one.
const BLANK = /[\p{Default_Ignorable_Code_Point}\p{Co}\u2800]|(?! )\p{Zs}/gu;
/** The spaces a part of a path opens or ends with: beside a slash nobody sees those either. */
const EDGE = /^ +| +$/g;

/** The text with each of those written as its code point: a no-break space is "[U+00A0]". */
export function showBlankChars(text: string): string {
  return text.replace(BLANK, asCode);
}

/** A path with each character nobody would see in it written as its code point, so two files
 *  whose names draw alike read apart: "notes/plan.md " is "notes/plan.md[U+0020]". */
export function showPathChars(path: string): string {
  const shown = (part: string) => showBlankChars(part.replace(EDGE, (spaces) => asCode(" ").repeat(spaces.length)));
  return path.split("/").map(shown).join("/");
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
