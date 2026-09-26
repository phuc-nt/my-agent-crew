/**
 * `[[Links]]` between wiki pages, resolved exactly the way the server resolves them.
 *
 * The server files a page under the slug of its title and turns every `[[Name]]` into the
 * slug of that name. If the browser slugged differently, a link would point at a page the
 * vault does not have, and the reader would be told a page is missing that is sitting
 * right there. So `normalize` and `slugify` below are line-for-line ports of
 * `memory/search.py` and `memory/wiki_slug.py`, and their tests use the server's cases.
 */

/** Where a `[[link]]` points once rendered; the page view intercepts it, nothing navigates. */
export const WIKI_HREF = "#wiki/";

const LINK_PATTERN = /\[\[([^[\]]+)\]\]/g;
const MANAGED_BLOCK = /<!-- wiki:related -->[\s\S]*?<!-- \/wiki:related -->/;
const UNTITLED = "khong-ten";

/** Lowercase, `đ` as `d`, and marks dropped only from a Latin base (so a dakuten stays). */
export function normalize(text: string): string {
  let out = "";
  let latinBase = false;
  for (const ch of text.toLowerCase().replace(/đ/g, "d").normalize("NFD")) {
    if (/\p{M}/u.test(ch)) {
      if (!latinBase) out += ch;
      continue;
    }
    latinBase = ch.codePointAt(0)! < 0x80;
    out += ch;
  }
  return out.normalize("NFC");
}

/** Every letter and digit of any script is kept; everything else becomes one dash. */
export function slugify(title: string): string {
  let kept = "";
  for (const ch of normalize(title)) kept += /[\p{L}\p{N}]/u.test(ch) ? ch : "-";
  return kept.replace(/-+/g, "-").replace(/^-|-$/g, "") || UNTITLED;
}

/**
 * A page body split into what its author wrote and the slugs of the machine's
 * "Liên quan" block. The block is markup the server regenerates on every edit; shown as
 * prose it would print its HTML comment markers, so it is drawn as chips instead.
 */
export function splitRelated(body: string): { authored: string; related: string[] } {
  const match = MANAGED_BLOCK.exec(body);
  if (!match) return { authored: body.trim(), related: [] };
  const authored = (body.slice(0, match.index) + body.slice(match.index + match[0].length)).trim();
  const related: string[] = [];
  for (const [, name] of match[0].matchAll(LINK_PATTERN)) {
    const slug = slugify(name.trim());
    if (!related.includes(slug)) related.push(slug);
  }
  return { authored, related };
}

/** The slug a rendered wiki link points at, or null for any other href. */
export function wikiSlugFromHref(href: string | undefined): string | null {
  if (!href?.startsWith(WIKI_HREF)) return null;
  try {
    return decodeURIComponent(href.slice(WIKI_HREF.length));
  } catch {
    return href.slice(WIKI_HREF.length);
  }
}

/** The small slice of a markdown tree this plugin touches. */
interface MdNode {
  type: string;
  value?: string;
  url?: string;
  children?: MdNode[];
}

function linkNodes(value: string): MdNode[] {
  const out: MdNode[] = [];
  let last = 0;
  for (const match of value.matchAll(LINK_PATTERN)) {
    const name = match[1].trim();
    if (match.index > last) out.push({ type: "text", value: value.slice(last, match.index) });
    out.push({ type: "link", url: WIKI_HREF + slugify(name), children: [{ type: "text", value: name }] });
    last = match.index + match[0].length;
  }
  if (last < value.length) out.push({ type: "text", value: value.slice(last) });
  return out;
}

function walk(node: MdNode): void {
  if (!node.children) return;
  node.children = node.children.flatMap((child) => {
    if (child.type === "text" && child.value?.includes("[[")) return linkNodes(child.value);
    // Code keeps its brackets (it is not a text node), and a link cannot hold a link.
    if (child.type !== "link" && child.type !== "linkReference") walk(child);
    return [child];
  });
}

/**
 * A remark plugin turning `[[Name]]` in prose into a link to `#wiki/<slug>`. Working on
 * the parsed tree rather than the source text means code spans and fenced blocks, which
 * are not text nodes, keep their brackets untouched.
 */
export function remarkWikiLinks() {
  return (tree: MdNode) => walk(tree);
}
