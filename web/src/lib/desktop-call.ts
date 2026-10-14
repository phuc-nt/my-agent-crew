// A `computer_act` call that waits for a person, said in one line: what it does, where on the
// frame's picture or to which element, and in which application. The raw arguments stay under
// it; this is the line read first. Nothing here judges the call: one that can only be refused
// never reaches a card.
import { vi } from "../i18n/vi";
import { piece } from "./browser-call";

export const ACT_TOOL = "computer_act";

type Args = Record<string, unknown>;

const CLICKS = vi.desktop.call.click;

/** A coordinate as the server's reasons write it: to the hundredth, whole when it is whole.
 *  "" for anything that is not a number. */
export function coordinate(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

/** A point of the frame's picture as "(x, y)", or null when either half is not a number. */
function point(x: unknown, y: unknown): string | null {
  const across = coordinate(x);
  const down = coordinate(y);
  return across && down ? `(${across}, ${down})` : null;
}

/** A count of lines to scroll: none said is none scrolled that way. */
function lines(value: unknown): string {
  return value === undefined ? "0" : coordinate(value);
}

function clickLine(verb: string, args: Args, app: string): string | null {
  const t = vi.desktop.call;
  const ref = piece(args.ref);
  if (ref) {
    const name = piece(args.name);
    return name ? t.byRef(verb, name, ref, app) : t.byRefUnnamed(verb, ref, app);
  }
  const at = point(args.x, args.y);
  return at ? t.byPoint(verb, at, app) : null;
}

function kindLine(args: Args, app: string): string | null {
  const t = vi.desktop.call;
  const kind = args.kind;
  if (kind === "click" || kind === "double_click" || kind === "right_click") return clickLine(CLICKS[kind], args, app);
  switch (kind) {
    case "drag": {
      const from = point(args.x, args.y);
      const to = point(args.to_x, args.to_y);
      return from && to ? t.drag(from, to, app) : null;
    }
    case "scroll": {
      const at = point(args.x, args.y);
      const dx = lines(args.dx);
      const dy = lines(args.dy);
      return at && dx && dy ? t.scroll(dx, dy, at, app) : null;
    }
    case "type":
      return t.type(piece(args.text), app);
    case "set_value": {
      const ref = piece(args.ref);
      return ref ? t.setValue(piece(args.text), ref, app) : null;
    }
    case "key": {
      const keys = piece(args.keys);
      return keys ? t.key(keys, app) : null;
    }
    case "focus_app":
      return t.focusApp(app);
    default:
      return null;
  }
}

/**
 * What a waiting desktop action does, in one line, or null for a call this cannot read: a
 * tool that is not `computer_act`, a kind not known here, or one that names no application
 * or misses what its kind needs. Arguments stored as one line by an older run are not a
 * mapping and read as nothing.
 */
export function desktopCallLine(name: string, args: unknown): string | null {
  if (name !== ACT_TOOL || typeof args !== "object" || args === null || Array.isArray(args)) return null;
  const app = piece((args as Args).app);
  return app ? kindLine(args as Args, app) : null;
}
