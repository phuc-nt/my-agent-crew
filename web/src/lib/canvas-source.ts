/**
 * Where a canvas says it came from, as the server writes it
 * (`my_agent_crew/tools/artifact_source_ref.py`): `workspace:<agent id>/<path>` for a file in an
 * agent's workspace, or a plain link to the page it was taken from. Anything else is no source: a
 * canvas made here has none, and what is stored is read again here rather than trusted. A link is
 * one only when its host can be named in a label, it carries no login and it leads off this app.
 */

export type CanvasSource =
  | { kind: "workspace"; agentId: string; path: string }
  /** `href` is the address as the browser reads it; `host` is where it leads. */
  | { kind: "url"; href: string; host: string };

/** Cut at the first slash: an agent id holds none, a path may hold any. */
const WORKSPACE = /^workspace:([^/]+)\/(.+)$/;
const WEB = ["http:", "https:"];
/** A name or an address in brackets, then a port. The browser's parser takes more in a host (a
 *  bracket, a comma, a quote), and the label draws the host inside words and brackets of its own. */
const HOST = /^(?:[a-z0-9._-]+|\[[0-9a-f:.]+\])(?::\d+)?$/;

export function parseSource(source: string): CanvasSource | null {
  const file = WORKSPACE.exec(source);
  if (file) return { kind: "workspace", agentId: file[1], path: file[2] };
  let url: URL;
  try {
    url = new URL(source);
  } catch {
    return null;
  }
  if (!WEB.includes(url.protocol) || !HOST.test(url.host)) return null;
  // Who logs in there would lead the address a browser shows, and a password would sit in the page.
  if (url.username !== "" || url.password !== "") return null;
  // The app's own address: a page an agent wrote would open in a tab that reads as the app.
  if (url.origin === window.location.origin) return null;
  return { kind: "url", href: url.href, host: url.host };
}
