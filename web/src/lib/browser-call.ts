// A browser call that waits for a person, said in one line: which page it opens, what it
// does to which element, or what it presses to bring a file down. The raw arguments stay
// under it; this is the line read first.
import { vi } from "../i18n/vi";
import { clip } from "./clip-text";
import { showHiddenChars } from "./hidden-chars";

/** The longest a single piece of the arguments is shown at. */
const PIECE_MAX = 80;

/**
 * One piece of the arguments as text for the line. It was written by a model, often copied
 * from a web page: line breaks and runs of blanks become one space, a character that changes
 * how a line reads without being seen is written as its code point, and a long piece is cut.
 * The marks a sentence here quotes a piece in are left out of it: a name a page chose that
 * closed them early could go on in words that read as the crew's. Anything that is not a
 * string or a number has no place in a sentence.
 */
export function piece(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return "";
  const flat = showHiddenChars(String(value).replace(/[«»]/g, "").replace(/\s+/g, " ").trim());
  return flat.length > PIECE_MAX ? `${clip(flat, PIECE_MAX)}…` : flat;
}

/** The host of an address, or "" for one that does not parse or names no host. */
function hostOf(address: string): string {
  try {
    return new URL(address).host;
  } catch {
    return "";
  }
}

function navigateLine(args: Record<string, unknown>): string | null {
  const address = typeof args.url === "string" ? args.url.trim() : "";
  if (!address) return null;
  return vi.browser.call.navigate(piece(hostOf(address) || address));
}

function actLine(args: Record<string, unknown>): string | null {
  const t = vi.browser.call;
  const name = piece(args.name);
  if (!name) return null;
  switch (args.kind) {
    case "click":
      return t.click(name);
    case "type":
      return t.type(piece(args.text), name);
    case "fill":
      return t.fill(piece(args.text), name);
    case "press": {
      const key = piece(args.key);
      return key ? t.press(key, name) : null;
    }
    case "select":
      return t.select(piece(args.value), name);
    case "hover":
      return t.hover(name);
    case "scroll":
      return t.scroll(name);
    case "upload": {
      const path = piece(args.path);
      return path ? t.upload(path, name) : null;
    }
    default:
      return null;
  }
}

/** A press that brings a file down: what is pressed, and the name the file is to be kept under
 *  where the call gives one. */
function downloadLine(args: Record<string, unknown>): string | null {
  const t = vi.browser.call;
  const name = piece(args.name);
  if (!name) return null;
  const file = piece(args.save_as);
  return file ? t.downloadAs(name, file) : t.download(name);
}

/**
 * What a waiting call does, in one line, or null for a call this cannot read: a tool that is
 * not the browser's, an action of a kind not known here, or one that names no element.
 * Arguments stored as one line by an older run are not a mapping and read as nothing.
 */
export function browserCallLine(name: string, args: unknown): string | null {
  if (typeof args !== "object" || args === null || Array.isArray(args)) return null;
  if (name === "browser_navigate") return navigateLine(args as Record<string, unknown>);
  if (name === "browser_act") return actLine(args as Record<string, unknown>);
  if (name === "browser_download") return downloadLine(args as Record<string, unknown>);
  return null;
}
